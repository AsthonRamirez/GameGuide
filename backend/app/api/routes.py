import logging
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from .schemas import ChatRequest, VoteRequest
from ..core.ratelimit import limit_chat, limit_vote
from ..services import gameguide as gg
from ..core import config as cfg_
from ..services import llm
from ..services.generation import group_sources

log = logging.getLogger("gameguide.api")
router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {
        "status": "ok",
        "gemini_configured": gg.llm_configured(),  # nombre histórico: el frontend lo usa
        "llm_provider": cfg_.LLM_PROVIDER,
        "supabase_configured": gg.supabase is not None,
    }


def _public_sources(chunks):
    return [{"title": s["title"], "url": s["url"], "source_type": s["source_type"], "source_name": s["source_name"]}
            for s in group_sources(chunks)]


@router.post("/chat", dependencies=[Depends(limit_chat)])
def chat(payload: ChatRequest, background: BackgroundTasks):
    question = payload.message.strip()
    if not question:
        raise HTTPException(400, "Escribe una pregunta.")
    session_id = payload.session_id or str(uuid.uuid4())
    history = payload.history[-8:]
    is_first_question = not any(x.get("role") == "user" for x in payload.history)

    # En una sesión nueva, busca una pregunta casi idéntica ya respondida (misma edición y versión).
    if is_first_question:
        previous = gg.find_similar_interaction(question, payload.edition, payload.game_version)
        if previous:
            return {
                "answer": previous.get("answer", ""), "interaction_id": previous.get("id"),
                "session_id": session_id, "category": previous.get("category", "general"),
                "model_used": "respuesta reutilizada", "response_ms": 0,
                "sources": previous.get("sources") or [],
                "status": "Se reutilizó una respuesta existente de la biblioteca.", "reused_existing": True,
            }

    started = time.perf_counter()
    try:
        standalone = gg.standalone_question(question, history)  # seguimiento -> pregunta independiente
        result = gg.retrieve_knowledge(standalone, payload.edition, payload.game_version)
        answer, model_used = gg.generate_answer(standalone, result.chunks, payload.edition,
                                                payload.game_version, history)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if result.errors:
            answer += "\n\n> Nota de recuperación: " + " ".join(result.errors)

        # Guardar lo recién descargado (y vectorizarlo) NO retrasa la respuesta.
        if result.live_docs:
            background.add_task(gg.persist_retrieval, result.live_docs, result.live_chunks)

        interaction_id, save_status = None, "Consulta respondida."
        if model_used not in ("error", "sin_llamada") and is_first_question:
            try:
                interaction_id = gg.save_interaction(
                    session_id, question, answer, result.category, payload.edition,
                    payload.game_version, model_used, elapsed_ms, result.chunks, result.reused)
                if not interaction_id:
                    save_status = "Respuesta generada, pero Supabase no devolvió el ID."
            except Exception as exc:
                log.warning("No se guardó la interacción: %s", exc)
                save_status = "Respuesta generada, pero no se guardó en Supabase: " + str(exc)[:150]
        elif model_used == "error":
            save_status = "El modelo de IA no estuvo disponible."
        elif not is_first_question:
            save_status = "Seguimiento conversacional; no se guarda como consulta independiente."
        return {
            "answer": answer, "interaction_id": interaction_id, "session_id": session_id,
            "category": result.category, "model_used": model_used, "response_ms": elapsed_ms,
            "sources": _public_sources(result.chunks), "status": save_status, "debug": result.debug,
        }
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        log.exception("Error procesando la consulta")
        raise HTTPException(500, f"No se pudo procesar la consulta: {str(exc)[:300]}")


@router.get("/public/consultations")
def public_consultations(limit: int = 30, offset: int = 0):
    try:
        return {"items": gg.list_public_interactions(max(1, min(limit, 100)), max(0, offset))}
    except Exception as exc:
        raise HTTPException(503, f"No se pudieron consultar las publicaciones: {str(exc)[:180]}")


@router.post("/public/consultations/{interaction_id}/vote", dependencies=[Depends(limit_vote)])
def vote(interaction_id: str, payload: VoteRequest):
    try:
        result = gg.save_vote(interaction_id, payload.voter_id.strip(), payload.vote)
        return {"status": "Calificación guardada.", "vote": result}
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.get("/dashboard")
def dashboard():
    if gg.supabase is None:
        return {"configured": False, "total": 0, "categories": {}, "feedback": {}}
    try:
        data = gg.load_live_metrics()
        return {
            "configured": True, "total": data["total"], "total_feedback": data["total_feedback"],
            "positive": data["positive"], "resolution": data["resolution"],
            "satisfaction": data["satisfaction"], "feedback_rate": data["feedback_rate"],
            "avg_seconds": data["avg_seconds"], "evidence_pct": data["evidence_pct"],
            "reuse_pct": data["reuse_pct"], "categories": data["categories"],
            "feedback": {"likes": data["likes"], "dislikes": data["dislikes"]},
            "daily": data["daily"],
        }
    except Exception as exc:
        raise HTTPException(503, f"No se pudieron consultar métricas: {str(exc)[:200]}")
