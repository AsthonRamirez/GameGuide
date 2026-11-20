"""Recuperación híbrida: documentos en vivo + conocimiento guardado, fragmentados y rankeados JUNTOS.

Corrige el problema original: antes, la búsqueda semántica se hacía solo sobre lo ya guardado y, si
devolvía cualquier cosa (no había umbral), se descartaban los documentos recién descargados.
Ahora todo entra al mismo ranking:  semántico (coseno, con umbral)  +  BM25  ->  fusión RRF.
"""
from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..core import config as cfg
from . import embeddings, persistence, sources
from .intent import classify_category, understand_query
from .textutils import bm25_scores, chunk_text, rrf, tokenize

log = logging.getLogger("gameguide.retrieval")


@dataclass
class RetrievalResult:
    chunks: list[dict] = field(default_factory=list)
    category: str = "general"
    errors: list[str] = field(default_factory=list)
    reused: bool = False
    debug: str = ""
    live_docs: list[dict] = field(default_factory=list)   # para guardar en segundo plano
    live_chunks: list[dict] = field(default_factory=list)  # con embedding si ya se calculó


# ------------------------------------------------------------------ chunking de documentos
def doc_to_chunks(doc: dict) -> list[dict]:
    """Un documento -> fragmentos con la metadata necesaria para citar y guardar."""
    if doc.get("source_type") == "modrinth":
        pieces = [doc["content"][: cfg.CHUNK_SIZE * 4]]  # una ficha de mod es corta: no se parte
    else:
        pieces = chunk_text(doc["content"], cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP)[:60]
    return [{
        "source_id": doc["source_id"], "chunk_index": i, "content": piece,
        "title": doc["title"], "url": doc["url"], "source_name": doc["source_name"],
        "source_type": doc["source_type"], "category": doc.get("category"),
        "game_version": doc.get("game_version"), "retrieved_at": doc.get("retrieved_at"),
        "live": True, "sim": None, "bm25": 0.0, "embedding": None,
    } for i, piece in enumerate(pieces)]


# ------------------------------------------------------------------ obtención en vivo
def gather_live_documents(question: str, intent: dict, edition: str, game_version: str, attempt: int):
    """Descarga fuentes en paralelo. attempt=1 es el reintento con una consulta distinta."""
    errors: list[str] = []
    docs: list[dict] = []
    keywords = sources.wiki_keywords(question)
    is_mod = intent["mod"]

    def run_modrinth():
        d, err = sources.search_modrinth(
            question, game_version, search_terms=intent["terms"],
            project_type=intent["project_type"], loader=intent["loader"])
        if err:
            errors.append(err)
        return d

    if is_mod:
        docs.extend(run_modrinth())
        if any(x in question.lower() for x in ["vanilla", "sin mods", "minecraft normal", "juego base"]):
            docs.extend(sources.search_minecraft_wiki(keywords, question, 3))
        return docs, errors

    tasks = {"wiki": lambda: sources.search_minecraft_wiki(keywords, question if attempt else "", 3)}
    if sources.needs_help_center(question):
        tasks["help"] = lambda: sources.search_official_help_center(question, 3)
    if sources.needs_official_pages(question):
        tasks["official"] = lambda: sources.search_official_minecraft_pages(question)
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {name: pool.submit(fn) for name, fn in tasks.items()}
        for name, fut in futures.items():
            try:
                docs.extend(fut.result())
            except Exception as exc:
                errors.append(f"{name}: {str(exc)[:120]}")

    docs.extend(sources.curated_documents(question))
    if not docs:
        # Red de seguridad: si Vanilla no encontró nada, puede ser el nombre de un mod.
        mod_docs = run_modrinth()
        docs.extend(mod_docs)
    return docs, errors


# ------------------------------------------------------------------ ranking
def rank_chunks(question: str, keywords: str, pool: list[dict], query_vec) -> tuple[list[dict], str]:
    """Híbrido semántico + BM25 con fusión RRF, umbral de similitud y diversidad por documento."""
    if not pool:
        return [], "sin candidatos"
    q_tokens = tokenize(keywords + " " + question)
    doc_tokens = [tokenize(c["title"] + " " + c["content"]) for c in pool]
    for c, s in zip(pool, bm25_scores(q_tokens, doc_tokens)):
        c["bm25"] = s

    # Embebe solo los fragmentos en vivo más prometedores (los guardados ya traen su similitud).
    semantic_ok = query_vec is not None
    if semantic_ok:
        live = [c for c in pool if c["live"]]
        order = sorted(live, key=lambda c: (-c["bm25"], c["chunk_index"]))
        chosen = order[: cfg.MAX_LIVE_CHUNKS_EMBEDDED]
        ids = {id(c) for c in chosen}
        for c in live:  # el primer fragmento (introducción) suele responder "qué es X"
            if c["chunk_index"] == 0 and id(c) not in ids:
                chosen.append(c)
        try:
            vecs = embeddings.embed_texts([f'{c["title"]}. {c["content"]}' for c in chosen])
            for c, v in zip(chosen, vecs):
                c["embedding"] = v
                c["sim"] = embeddings.cosine(query_vec, v)
        except Exception as exc:
            log.warning("Embeddings no disponibles; se usa solo BM25: %s", str(exc)[:150])
            semantic_ok = False

    sem_rank = sorted((c for c in pool if c["sim"] is not None and c["sim"] >= cfg.SEMANTIC_MIN_SIMILARITY),
                      key=lambda c: -c["sim"])
    bm_rank = sorted((c for c in pool if c["bm25"] > 0), key=lambda c: -c["bm25"])
    fused = rrf([[id(c) for c in sem_rank], [id(c) for c in bm_rank]], cfg.RRF_K)

    q_set = set(q_tokens)
    by_id = {id(c): c for c in pool}
    for cid in list(fused):
        c = by_id[cid]
        title_tokens = set(tokenize(c["title"]))
        if title_tokens and title_tokens <= q_set:
            fused[cid] += 0.02   # el título del artículo es lo que se preguntó
        if c["source_type"] == "curated":
            fused[cid] += 0.006  # ficha curada: ayuda, pero no desplaza a la Wiki
        if c["source_type"] == "official" and c["category"] != "mods":
            fused[cid] *= 0.9
    ranked = sorted(fused.items(), key=lambda kv: -kv[1])

    selected, per_doc = [], {}
    for cid, score in ranked:
        c = by_id[cid]
        if per_doc.get(c["source_id"], 0) >= cfg.MAX_CHUNKS_PER_DOC:
            continue
        per_doc[c["source_id"]] = per_doc.get(c["source_id"], 0) + 1
        c["score"] = round(score, 4)
        selected.append(c)
        if len(selected) >= cfg.MAX_CONTEXT_CHUNKS:
            break
    info = (f"pool={len(pool)} sem_ok={len(sem_rank)} bm25_ok={len(bm_rank)} "
            f"semantico={'si' if semantic_ok else 'no'}")
    return selected, info


# ------------------------------------------------------------------ orquestación
def retrieve_knowledge(question: str, edition="No especificada", game_version="") -> RetrievalResult:
    intent = understand_query(question, edition, game_version)
    category = "mods" if intent["mod"] else classify_category(question)
    result = RetrievalResult(category=category)
    keywords = sources.wiki_keywords(question)

    try:
        query_vec = embeddings.embed_texts([question])[0]
    except Exception as exc:
        log.warning("No se pudo vectorizar la pregunta: %s", str(exc)[:150])
        query_vec = None

    for attempt in (0, 1):
        live_docs, errors = gather_live_documents(question, intent, edition, game_version, attempt)
        result.errors = errors if attempt == 0 else result.errors + errors
        live_chunks = [c for d in live_docs for c in doc_to_chunks(d)]

        if category == "mods" and any(d["source_type"] == "modrinth" for d in live_docs):
            # Modrinth ya devuelve los resultados ordenados por relevancia: se respeta ese orden.
            selected = [c for c in live_chunks if c["source_type"] == "modrinth"][: cfg.MAX_CONTEXT_CHUNKS]
            info = "orden de relevancia de Modrinth"
        else:
            stored = []
            if query_vec is not None:
                stored = persistence.match_chunks(query_vec, count=12)
            live_ids = {c["source_id"] for c in live_chunks}
            stored = [
                {**row, "live": False, "bm25": 0.0, "embedding": None}
                for row in stored
                if row["source_id"] not in live_ids  # lo recién descargado manda sobre lo guardado
                and (row.get("source_type") == "modrinth") == (category == "mods")
                and (not game_version or not row.get("game_version") or row.get("game_version") == game_version)
            ]
            selected, info = rank_chunks(question, keywords, live_chunks + stored, query_vec)

        result.live_docs, result.live_chunks = live_docs, live_chunks
        result.reused = any(not c["live"] for c in selected)
        result.chunks = selected
        result.debug = (f"intento={attempt} intención={'mod' if intent['mod'] else 'vanilla'}({intent['by']}) "
                        f"palabras_clave='{keywords}' en_vivo={len(live_docs)} docs/{len(live_chunks)} frag; {info}")
        log.info("RETRIEVAL %s | pregunta=%r", result.debug, question[:120])
        for c in selected:
            log.info("  -> [%s] %s #%s score=%s sim=%s bm25=%.2f", c["source_type"], c["title"][:50],
                     c["chunk_index"], c.get("score"), None if c["sim"] is None else round(c["sim"], 3), c["bm25"])
        if selected or intent["mod"]:
            break  # con mods el reintento repetiría exactamente las mismas consultas
        log.info("Sin evidencia en el intento %d; se reintenta con otra consulta.", attempt)
    return result
