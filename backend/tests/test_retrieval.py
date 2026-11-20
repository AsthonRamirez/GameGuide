"""Pruebas de regresión del bug principal: los documentos recién descargados se descartaban."""
from app.services import embeddings, retrieval, sources
from app.services.retrieval import doc_to_chunks, rank_chunks


def make_doc(title, text, source_type="community_wiki", url=None):
    return sources.normalize_document("Minecraft Wiki (comunitaria)", source_type, title, text,
                                      url or f"https://minecraft.wiki/w/{title}", "vanilla")


ELYTRA = make_doc("Elytra", "Elytra are a pair of wings that allow gliding. " * 3 +
                  "Elytra can be found in End ships inside an item frame in End Cities. " * 3)
STORED_VILLAGER = {
    "source_id": "x1", "chunk_index": 0, "title": "Villager", "url": "https://minecraft.wiki/w/Villager",
    "source_name": "Minecraft Wiki", "source_type": "community_wiki", "category": "vanilla",
    "game_version": None, "content": "Villagers trade items with emeralds and have professions.",
    "live": False, "sim": 0.55, "bm25": 0.0, "embedding": None,
}


def test_live_documents_are_ranked_together_with_stored_ones():
    live = doc_to_chunks(ELYTRA)
    q = "Como consigo las elytras"
    qv = embeddings.embed_texts([q])[0]
    selected, _ = rank_chunks(q, sources.wiki_keywords(q), live + [dict(STORED_VILLAGER)], qv)
    assert selected[0]["title"] == "Elytra"          # antes: ganaba lo guardado aunque fuera de otro tema
    assert all(c["bm25"] > 0 or c["sim"] >= 0.30 for c in selected)


def test_irrelevant_stored_chunk_below_threshold_is_dropped():
    stored = dict(STORED_VILLAGER, sim=0.05)
    q = "Como consigo las elytras"
    selected, _ = rank_chunks(q, "elytra", [stored], embeddings.embed_texts([q])[0])
    assert selected == []                            # sin evidencia útil -> no se inventan documentos


def test_max_chunks_per_document():
    big = make_doc("Elytra", "Elytra glide through the air. " * 400)
    q = "elytra"
    selected, _ = rank_chunks(q, "elytra", doc_to_chunks(big), embeddings.embed_texts([q])[0])
    assert 0 < len(selected) <= 2                    # diversidad: máx. 2 fragmentos por documento


def test_works_without_embeddings_uses_bm25():
    selected, info = rank_chunks("elytra", "elytra", doc_to_chunks(ELYTRA), None)
    assert selected and "semantico=no" in info


def test_end_to_end_retrieval_with_mocked_sources(monkeypatch):
    monkeypatch.setattr(sources, "search_minecraft_wiki", lambda *a, **k: [ELYTRA])
    monkeypatch.setattr(retrieval.persistence, "match_chunks", lambda *a, **k: [dict(STORED_VILLAGER, similarity=0.9)])
    res = retrieval.retrieve_knowledge("Como consigo las elytras ?", "Java Edition", "1.20.1")
    titles = [c["title"] for c in res.chunks]
    assert "Elytra" in titles and titles[0] != "Villager"
    assert res.live_docs and res.category == "objetos"


def test_retry_with_other_query_when_first_attempt_is_empty(monkeypatch):
    calls = []

    def fake_wiki(keywords, raw="", limit=3):
        calls.append(raw)
        return [] if not raw else [ELYTRA]           # el reintento pasa la pregunta original

    monkeypatch.setattr(sources, "search_minecraft_wiki", fake_wiki)
    monkeypatch.setattr(sources, "curated_documents", lambda *a, **k: [])
    monkeypatch.setattr(retrieval.persistence, "match_chunks", lambda *a, **k: [])
    res = retrieval.retrieve_knowledge("elytra", "No especificada", "")
    assert len(calls) == 2 and res.chunks


def test_curated_card_found_even_if_wiki_is_down(monkeypatch):
    monkeypatch.setattr(sources, "search_minecraft_wiki", lambda *a, **k: [])
    monkeypatch.setattr(retrieval.persistence, "match_chunks", lambda *a, **k: [])
    res = retrieval.retrieve_knowledge("Como consigo las elytras ?", "Java Edition", "")
    assert res.chunks and res.chunks[0]["source_type"] == "curated"
