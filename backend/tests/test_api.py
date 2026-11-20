from fastapi.testclient import TestClient

from app.main import app
from app.services import generation, retrieval, sources
from app.services import gameguide as gg

client = TestClient(app)


def _setup(monkeypatch, answer="Las élitras están en los barcos del End [1]."):
    monkeypatch.setattr(sources, "search_minecraft_wiki", lambda *a, **k: [])
    monkeypatch.setattr(retrieval.persistence, "match_chunks", lambda *a, **k: [])
    monkeypatch.setattr(generation.llm, "generate",
                        lambda *a, **k: generation.llm.LLMResult(answer, "modelo-prueba", "STOP"))
    monkeypatch.setattr(gg.persistence, "find_similar_interaction", lambda *a, **k: None)


def test_basic_question_gets_answered_with_sources(monkeypatch):
    _setup(monkeypatch)
    r = client.post("/api/chat", json={"message": "Como consigo las elytras ?", "edition": "Java Edition"})
    assert r.status_code == 200
    body = r.json()
    assert body["model_used"] == "modelo-prueba"
    assert "Fuentes consultadas" in body["answer"] and body["sources"]
    assert "Detalle técnico" not in body["answer"]   # ya no se filtra texto técnico al jugador
    assert body["category"] == "objetos"


def test_no_global_state_leaks_between_requests(monkeypatch):
    _setup(monkeypatch)
    a = client.post("/api/chat", json={"message": "Como consigo las elytras ?"}).json()
    b = client.post("/api/chat", json={"message": "¿Dónde encuentro diamantes?"}).json()
    assert a["debug"] != b["debug"]


def test_truncated_answer_is_flagged(monkeypatch):
    _setup(monkeypatch)
    monkeypatch.setattr(generation.llm, "generate",
                        lambda *a, **k: generation.llm.LLMResult("texto cortado", "m", "MAX_TOKENS"))
    r = client.post("/api/chat", json={"message": "elytras"})
    assert "se cortó" in r.json()["answer"]


def test_rate_limit_returns_429(monkeypatch):
    _setup(monkeypatch)
    codes = [client.post("/api/chat", json={"message": f"diamantes {i}"}).status_code for i in range(10)]
    assert 429 in codes


def test_history_becomes_conversation_turns():
    hist = [{"role": "assistant", "content": "¡Hola!"}, {"role": "user", "content": "¿Cómo consigo élitras?"},
            {"role": "assistant", "content": "En el End."}]
    turns = generation._history_turns(hist)
    assert [t["role"] for t in turns] == ["user", "assistant"]


def test_health_and_cors():
    assert client.get("/api/health").json()["status"] == "ok"
    r = client.options("/api/chat", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers
