"""Fachada del servicio GameGuide. La lógica vive en módulos separados:

  embeddings.py   embeddings locales          sources.py      Wiki / Help Center / Modrinth / fichas
  llm.py          proveedor de IA             retrieval.py    recuperación híbrida y ranking
  intent.py       categoría y seguimientos    generation.py   prompt y respuesta
  persistence.py  Supabase y métricas         textutils.py    BM25, chunking, RRF
"""
from __future__ import annotations
import logging
import threading

from . import embeddings, llm, persistence
from .generation import generate_answer
from .intent import classify_category, standalone_question
from .persistence import (find_similar_interaction, list_public_interactions, load_live_metrics,
                          persist_retrieval, save_interaction, save_vote)
from .retrieval import RetrievalResult, retrieve_knowledge

log = logging.getLogger("gameguide")

supabase = persistence.supabase  # lo usa /api/health y /api/dashboard


def llm_configured() -> bool:
    return llm.is_configured()


def initialize_data() -> None:
    """Arranque ligero: precarga el modelo de embeddings en segundo plano y valida los modelos de IA.

    La vectorización de documentos antiguos ya NO ocurre aquí: usa `python -m scripts.backfill_chunks`.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    embeddings.warmup_async()
    threading.Thread(target=llm.check_models, daemon=True, name="llm-model-check").start()
