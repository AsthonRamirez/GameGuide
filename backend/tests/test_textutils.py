from app.services.textutils import bm25_scores, chunk_text, rrf, tokenize


def test_chunking_respects_size_and_overlap():
    text = " ".join(f"Sentence number {i} talks about elytra and flying." for i in range(200))
    chunks = chunk_text(text, size=800, overlap=150)
    assert len(chunks) > 5
    assert all(len(c) <= 800 + 150 + 60 for c in chunks)
    # traslape: el comienzo de un fragmento repite palabras del final del anterior
    assert chunks[1].split()[0] in chunks[0]


def test_chunking_short_text_and_empty():
    assert chunk_text("hola mundo") == ["hola mundo"]
    assert chunk_text("") == []


def test_chunking_text_without_punctuation_is_still_split():
    assert all(len(c) <= 1000 for c in chunk_text("palabra " * 1000, 800, 150))


def test_tokenize_plural_stemming():
    assert tokenize("Diamonds and villagers") == ["diamond", "villager"]


def test_bm25_ranks_relevant_first():
    docs = [tokenize("villagers trade emeralds"), tokenize("elytra let you glide from End ships")]
    scores = bm25_scores(tokenize("elytra"), docs)
    assert scores[1] > scores[0] == 0


def test_rrf_combines_rankings():
    fused = rrf([["a", "b"], ["b", "c"]])
    assert fused["b"] > fused["a"] and fused["b"] > fused["c"]


def test_embedder_failure_has_cooldown(monkeypatch):
    """Si el modelo no se puede descargar, no se bloquea cada consulta reintentando."""
    import sys, types
    from app.services import embeddings
    calls = []

    class Boom:
        def __init__(self, *a, **k):
            calls.append(1)
            raise OSError("sin red")

    monkeypatch.setitem(sys.modules, "fastembed", types.SimpleNamespace(TextEmbedding=Boom))
    monkeypatch.setattr(embeddings, "_embedder", None)
    monkeypatch.setattr(embeddings, "_failed_until", 0.0)
    for _ in range(3):
        try:
            embeddings.get_embedder()
        except Exception:
            pass
    assert len(calls) == 1
