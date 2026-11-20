import time, uuid
from fastapi import APIRouter, HTTPException
from .schemas import ChatRequest, VoteRequest
from ..services import gameguide as gg

router = APIRouter(prefix="/api")

@router.get("/health")
def health():
    return {
        "status": "ok",
        "gemini_configured": gg.gemini_client is not None,
        "supabase_configured": gg.supabase is not None
    }

@router.post("/chat")
def chat(payload: ChatRequest):
    question = payload.message.strip()
    if not question:
        raise HTTPException(400, "Escribe una pregunta.")
    session_id = payload.session_id or str(uuid.uuid4())
    history_context = "\n".join(
        f"{item.get('role','')}: {str(item.get('content',''))[:650]}"
        for item in payload.history[-6:]
        if item.get("role") in ("user", "assistant")
    )[-3000:]
    prior_questions = [x.get("content", "") for x in payload.history if x.get("role") == "user"]
    # En una sesión nueva, busca una pregunta equivalente ya respondida antes de consultar fuentes/IA.
    if not prior_questions:
        previous = gg.find_similar_interaction(question, payload.edition, payload.game_version)
        if previous:
            return {
                "answer": previous.get("answer", ""),
                "interaction_id": previous.get("id"),
                "session_id": session_id,
                "category": previous.get("category", "general"),
                "model_used": "respuesta reutilizada",
                "response_ms": 0,
                "sources": previous.get("sources") or [],
                "status": "Se reutilizó una respuesta existente de la biblioteca.",
                "reused_existing": True
            }
    retrieval_query = question
    if prior_questions and len(gg.tokenize(question)) <= 4:
        retrieval_query = prior_questions[-1] + " " + question
    started = time.perf_counter()
    try:
        docs, reused, category, retrieval_errors = gg.retrieve_knowledge(
            retrieval_query, payload.edition, payload.game_version
        )
        answer, model_used = gg.generate_with_fallback(
            question, docs, payload.edition, payload.game_version, history_context
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if retrieval_errors:
            answer += "\n\n> Nota de recuperación: " + " ".join(retrieval_errors)
        interaction_id = None
        save_status = "Consulta respondida."
        if model_used not in ("error", "sin_llamada") and not prior_questions:
            try:
                interaction_id = gg.save_interaction(
                    session_id, question, answer, category, payload.edition,
                    payload.game_version, model_used, elapsed_ms, docs, reused
                )
                if not interaction_id:
                    save_status = "Respuesta generada, pero Supabase no devolvió el ID."
            except Exception as exc:
                save_status = "Respuesta generada, pero no se guardó en Supabase: " + str(exc)[:150]
        elif model_used == "error":
            save_status = "Gemini no estuvo disponible."
        else:
            save_status = "Seguimiento conversacional; no se guarda como consulta independiente."
        return {
            "answer": answer, "interaction_id": interaction_id,
            "session_id": session_id, "category": category,
            "model_used": model_used, "response_ms": elapsed_ms,
            "sources": [{"title":d.get("title"),"url":d.get("url"),"source_type":d.get("source_type"),"source_name":d.get("source_name")} for d in docs],
            "status": save_status
        }
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"No se pudo procesar la consulta: {str(exc)[:300]}")

@router.get("/public/consultations")
def public_consultations(limit: int = 30, offset: int = 0):
    try:
        return {"items": gg.list_public_interactions(max(1, min(limit, 100)), max(0, offset))}
    except Exception as exc:
        raise HTTPException(503, f"No se pudieron consultar las publicaciones: {str(exc)[:180]}")

@router.post("/public/consultations/{interaction_id}/vote")
def vote(interaction_id: str, payload: VoteRequest):
    voter_id = payload.voter_id.strip()
    vote_value = payload.vote
    try:
        result = gg.save_vote(interaction_id, voter_id, vote_value)
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
            "configured": True,
            "total": data["total"],
            "total_feedback": data["total_feedback"],
            "positive": data["positive"],
            "resolution": data["resolution"],
            "satisfaction": data["satisfaction"],
            "feedback_rate": data["feedback_rate"],
            "avg_seconds": data["avg_seconds"],
            "evidence_pct": data["evidence_pct"],
            "reuse_pct": data["reuse_pct"],
            "categories": data["categories"],
            "feedback": {
                "likes": sum(1 for x in data["feedback"] if x.get("vote") == "like"),
                "dislikes": sum(1 for x in data["feedback"] if x.get("vote") == "dislike")
            },
            "daily": data["daily"]
        }
    except Exception as exc:
        raise HTTPException(503, f"No se pudieron consultar métricas: {str(exc)[:200]}")
