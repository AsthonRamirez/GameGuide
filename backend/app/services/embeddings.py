"""Embeddings multilingües locales (FastEmbed). No usa APIs de pago."""
from __future__ import annotations
import logging
import threading
import time

import numpy as np

from ..core import config  # noqa: F401  (fija FASTEMBED_CACHE_PATH antes de importar fastembed)

log = logging.getLogger("gameguide.embeddings")

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MAX_CHARS = 2000  # los fragmentos ya son cortos; esto solo protege de textos enormes

_embedder = None
_lock = threading.Lock()
_failed_until = 0.0
FAILURE_COOLDOWN_S = 300  # tras un fallo de carga/descarga no se reintenta durante 5 minutos


def get_embedder():
    global _embedder, _failed_until
    if _embedder is None:
        with _lock:
            if time.time() < _failed_until:
                raise RuntimeError("Modelo de embeddings no disponible (reintento en unos minutos).")
            if _embedder is None:
                from fastembed import TextEmbedding
                log.info("Cargando modelo de embeddings %s ...", MODEL_NAME)
                try:
                    _embedder = TextEmbedding(model_name=MODEL_NAME)
                except Exception:
                    _failed_until = time.time() + FAILURE_COOLDOWN_S
                    raise
    return _embedder


def embed_texts(texts: list[str]) -> list[list[float]]:
    prepared = [str(t)[:MAX_CHARS] for t in texts]
    if not prepared:
        return []
    return [v.tolist() for v in get_embedder().embed(prepared)]


def cosine(a, b) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b / denom) if denom else 0.0


def warmup_async() -> None:
    """Carga el modelo en segundo plano al arrancar para que la primera consulta no espere."""
    def _run():
        try:
            get_embedder()
            embed_texts(["calentamiento"])
            log.info("Modelo de embeddings listo.")
        except Exception as exc:  # pragma: no cover
            log.warning("No se pudo precargar el modelo de embeddings: %s", str(exc)[:200])
    threading.Thread(target=_run, daemon=True, name="embedder-warmup").start()
