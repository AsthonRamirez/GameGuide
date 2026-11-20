import pytest

from app.services import llm
from app.services.persistence import is_shareable


def test_llm_retries_on_429_then_succeeds(monkeypatch):
    calls = []

    def flaky(model, *a):
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED retryDelay: 0s")
        return llm.LLMResult("ok", model, "STOP")

    monkeypatch.setattr(llm, "_call_gemini", flaky)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    out = llm.generate("sys", [{"role": "user", "content": "hola"}], models=["m1", "m2"])
    assert out.text == "ok" and calls == ["m1", "m1"]


def test_llm_falls_back_to_backup_model(monkeypatch):
    def only_backup(model, *a):
        if model == "malo":
            raise RuntimeError("404 model not found")
        return llm.LLMResult("respaldo", model, "STOP")

    monkeypatch.setattr(llm, "_call_gemini", only_backup)
    assert llm.generate("s", [{"role": "user", "content": "x"}], models=["malo", "bueno"]).model == "bueno"


def test_llm_bad_key_stops_immediately(monkeypatch):
    monkeypatch.setattr(llm, "_call_gemini", lambda *a: (_ for _ in ()).throw(RuntimeError("403 permission denied")))
    with pytest.raises(llm.LLMError):
        llm.generate("s", [{"role": "user", "content": "x"}], models=["a", "b"])


def test_private_data_is_not_published():
    assert not is_shareable("mi correo es juan@example.com", "ok")
    assert not is_shareable("mi contraseña es 1234", "ok")
    assert not is_shareable("llámame al +52 81 1234 5678", "ok")
    assert is_shareable("¿Cómo consigo las élitras en la 1.20.1?", "En el End [1]")
