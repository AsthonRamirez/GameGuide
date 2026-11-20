import hashlib
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for var in ("GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "LLM_API_KEY"):
    os.environ[var] = ""
os.environ["RATE_LIMIT_CHAT_PER_MIN"] = "5"


def fake_embed(texts):
    """Embedding de prueba: bolsa de palabras hasheada, con traducción ES->EN para simular lo multilingüe."""
    from app.services.sources import WIKI_TERM_MAP
    from app.services.textutils import tokenize
    out = []
    for text in texts:
        v = np.zeros(256)
        for tok in tokenize(text):
            tok = WIKI_TERM_MAP.get(tok, tok)
            for part in tok.split():
                v[int(hashlib.md5(part.encode()).hexdigest(), 16) % 256] += 1
        out.append(v.tolist())
    return out


@pytest.fixture(autouse=True)
def _no_real_embeddings(monkeypatch):
    from app.services import embeddings
    from app.services import sources
    monkeypatch.setattr(embeddings, "embed_texts", fake_embed)
    # Las pruebas nunca deben tocar la red.
    monkeypatch.setattr(sources, "search_modrinth", lambda *a, **k: ([], None))
    monkeypatch.setattr(sources.HTTP, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sin red en pruebas")))
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.core import ratelimit
    ratelimit.limit_chat._hits.clear()
    ratelimit.limit_vote._hits.clear()
    yield
