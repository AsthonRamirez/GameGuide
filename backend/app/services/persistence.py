"""Acceso a Supabase: fragmentos de conocimiento, interacciones, votos y métricas."""
from __future__ import annotations
import logging
import re
import statistics
import threading
import time
from datetime import datetime, timedelta, timezone

from supabase import create_client

from ..core import config as cfg
from . import embeddings

log = logging.getLogger("gameguide.db")

supabase = (create_client(cfg.SUPABASE_URL, cfg.SUPABASE_SERVICE_ROLE_KEY)
            if cfg.SUPABASE_URL and cfg.SUPABASE_SERVICE_ROLE_KEY else None)


def require_supabase():
    if supabase is None:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en backend/.env")
    return supabase


# ------------------------------------------------------------------ conocimiento (chunks)
def match_chunks(query_vec, count=12) -> list[dict]:
    """Búsqueda semántica sobre fragmentos guardados, con umbral mínimo y antigüedad máxima."""
    if supabase is None:
        return []
    try:
        rows = supabase.rpc("match_knowledge_chunks", {
            "query_embedding": query_vec, "match_count": count,
            "min_similarity": cfg.SEMANTIC_MIN_SIMILARITY, "max_age_days": cfg.CACHE_TTL_DAYS,
        }).execute().data or []
        for r in rows:
            r["sim"] = r.pop("similarity", None)
        return rows
    except Exception as exc:
        log.warning("match_knowledge_chunks no disponible (¿ejecutaste supabase_schema.sql?): %s", str(exc)[:160])
        return []


def _batches(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def persist_retrieval(live_docs: list[dict], live_chunks: list[dict]) -> None:
    """Se ejecuta en segundo plano DESPUÉS de responder: guarda documentos y fragmentos vectorizados."""
    if supabase is None:
        return
    try:
        docs = [d for d in live_docs if d.get("source_type") != "curated"]
        if not docs:
            return
        # Evita volver a vectorizar lo que se guardó en las últimas 24 h.
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        ids = [d["source_id"] for d in docs]
        fresh = {r["source_id"] for r in (supabase.table("knowledge_documents").select("source_id")
                 .in_("source_id", ids).gte("retrieved_at", cutoff).execute().data or [])}
        docs = [d for d in docs if d["source_id"] not in fresh]
        if not docs:
            return
        wanted = {d["source_id"] for d in docs}
        chunks = [c for c in live_chunks if c["source_id"] in wanted]

        rows = [{k: v for k, v in d.items() if k != "was_cached"} for d in docs]
        for batch in _batches(rows, 20):
            supabase.table("knowledge_documents").upsert(batch, on_conflict="source_id").execute()

        missing = [c for c in chunks if c.get("embedding") is None]
        for batch in _batches(missing, 32):
            for c, v in zip(batch, embeddings.embed_texts([f'{c["title"]}. {c["content"]}' for c in batch])):
                c["embedding"] = v
        chunk_rows = [{
            "source_id": c["source_id"], "chunk_index": c["chunk_index"], "content": c["content"],
            "title": c["title"], "url": c["url"], "source_name": c["source_name"],
            "source_type": c["source_type"], "category": c.get("category"),
            "game_version": c.get("game_version"), "retrieved_at": c.get("retrieved_at"),
            "embedding": c["embedding"],
        } for c in chunks if c.get("embedding") is not None]
        for batch in _batches(chunk_rows, 50):
            supabase.table("knowledge_chunks").upsert(batch, on_conflict="source_id,chunk_index").execute()
        log.info("Guardados en segundo plano: %d documentos, %d fragmentos.", len(docs), len(chunk_rows))
    except Exception as exc:
        log.warning("No se pudo guardar conocimiento en segundo plano: %s", str(exc)[:200])


# ------------------------------------------------------------------ interacciones
_SENSITIVE = re.compile(
    r"([\w.+-]+@[\w-]+\.[\w.]+)|(\+?\d[\d\s().-]{8,}\d)|\b(contraseña|password|passwd|token|api[_ -]?key)\b", re.I)


def is_shareable(*texts: str) -> bool:
    """La biblioteca es pública: no se publica si hay correos, teléfonos o credenciales."""
    return not any(_SENSITIVE.search(t or "") for t in texts)


def find_similar_interaction(question, edition="No especificada", game_version=""):
    """Reutiliza una respuesta previa solo si es casi idéntica, misma edición/versión, con evidencia y sin dislikes."""
    if supabase is None or not cfg.REUSE_ENABLED:
        return None
    try:
        vector = embeddings.embed_texts([question])[0]
        data = supabase.rpc("match_chat_interactions", {
            "query_embedding": vector, "match_threshold": cfg.REUSE_THRESHOLD, "match_count": 1,
            "edition_filter": edition, "game_version_filter": game_version or None,
        }).execute().data
        return data[0] if data else None
    except Exception as exc:
        log.warning("No se pudo reutilizar una consulta previa: %s", str(exc)[:160])
        return None


def save_interaction(session_id, question, answer, category, edition, game_version,
                     model_used, response_ms, chunks, reused):
    sources, seen = [], set()
    for c in chunks:
        if c.get("url") in seen:
            continue
        seen.add(c.get("url"))
        sources.append({"title": c.get("title"), "url": c.get("url"),
                        "source_type": c.get("source_type"), "source_name": c.get("source_name")})
    row = {
        "session_id": str(session_id), "question": question, "answer": answer,
        "category": category, "edition": edition, "game_version": game_version or None,
        "model_used": model_used, "response_ms": int(response_ms), "sources": sources,
        "retrieved_count": len(chunks), "evidence": len(chunks) > 0,
        "reused_knowledge": bool(reused), "is_public": is_shareable(question, answer),
    }
    try:
        row["question_embedding"] = embeddings.embed_texts([question])[0]
    except Exception as exc:
        log.warning("No se pudo crear embedding de consulta: %s", str(exc)[:120])
    result = require_supabase().table("chat_interactions").insert(row).execute()
    return result.data[0].get("id") if result.data else None


def list_public_interactions(limit=50, offset=0):
    client = require_supabase()
    rows = (client.table("chat_interactions")
            .select("id,question,answer,category,edition,game_version,sources,created_at")
            .eq("is_public", True).order("created_at", desc=True)
            .range(offset, offset + limit - 1).execute().data or [])
    counts = {r["id"]: {"likes": 0, "dislikes": 0} for r in rows}
    if rows:  # solo los votos de las filas mostradas (antes se descargaban todos)
        votes = client.table("chat_votes").select("interaction_id,vote").in_("interaction_id", list(counts)).execute().data or []
        for v in votes:
            counts[v["interaction_id"]]["likes" if v["vote"] == "like" else "dislikes"] += 1
    for r in rows:
        r.update(counts[r["id"]])
    return rows


def save_vote(interaction_id, voter_id, vote):
    if vote not in ("like", "dislike"):
        raise ValueError("La calificación debe ser like o dislike.")
    row = {"interaction_id": str(interaction_id), "voter_id": str(voter_id), "vote": vote,
           "updated_at": datetime.now(timezone.utc).isoformat()}
    result = require_supabase().table("chat_votes").upsert(row, on_conflict="interaction_id,voter_id").execute()
    _METRICS_CACHE["ts"] = 0  # el dashboard debe reflejar el voto nuevo
    return result.data[0] if result.data else row


# ------------------------------------------------------------------ métricas
_METRICS_CACHE = {"ts": 0.0, "data": None}
_metrics_lock = threading.Lock()


def _python_metrics(days=30, max_rows=5000):
    """Respaldo si la función SQL dashboard_metrics aún no existe."""
    client = require_supabase()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    inter = (client.table("chat_interactions").select("category,response_ms,sources,evidence,reused_knowledge,created_at")
             .gte("created_at", cutoff).limit(max_rows).execute().data or [])
    votes = client.table("chat_votes").select("vote").gte("created_at", cutoff).limit(max_rows).execute().data or []
    ms = [x["response_ms"] for x in inter if x.get("response_ms") is not None]
    cats, daily = {}, {}
    for x in inter:
        cats[x.get("category") or "general"] = cats.get(x.get("category") or "general", 0) + 1
        day = str(x.get("created_at", ""))[:10]
        if day:
            daily[day] = daily.get(day, 0) + 1
    return {
        "total": len(inter), "total_feedback": len(votes),
        "likes": sum(1 for v in votes if v["vote"] == "like"),
        "dislikes": sum(1 for v in votes if v["vote"] == "dislike"),
        "avg_ms": statistics.mean(ms) if ms else None,
        "with_evidence": sum(1 for x in inter if x.get("evidence") or x.get("sources")),
        "reused": sum(1 for x in inter if x.get("reused_knowledge")),
        "categories": cats, "daily": [{"date": d, "count": daily[d]} for d in sorted(daily)],
    }


def load_live_metrics(days=30):
    with _metrics_lock:
        if _METRICS_CACHE["data"] and time.time() - _METRICS_CACHE["ts"] < cfg.DASHBOARD_CACHE_SECONDS:
            return _METRICS_CACHE["data"]
    try:
        raw = require_supabase().rpc("dashboard_metrics", {"days": days}).execute().data
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        if not isinstance(raw, dict):
            raise ValueError("respuesta vacía")
    except Exception as exc:
        log.info("dashboard_metrics (SQL) no disponible, se calcula en Python: %s", str(exc)[:120])
        raw = _python_metrics(days)
    total, fb, likes = raw["total"], raw["total_feedback"], raw["likes"]
    data = {
        "total": total, "total_feedback": fb, "positive": likes, "likes": likes, "dislikes": raw["dislikes"],
        "resolution": (likes / total * 100) if total else None,
        "satisfaction": (likes / fb * 100) if fb else None,
        "feedback_rate": (fb / total * 100) if total else None,
        "avg_seconds": (raw["avg_ms"] / 1000) if raw.get("avg_ms") is not None else None,
        "evidence_pct": (raw["with_evidence"] / total * 100) if total else None,
        "reuse_pct": (raw["reused"] / total * 100) if total else None,
        "categories": raw.get("categories") or {}, "daily": raw.get("daily") or [],
    }
    with _metrics_lock:
        _METRICS_CACHE.update(ts=time.time(), data=data)
    return data
