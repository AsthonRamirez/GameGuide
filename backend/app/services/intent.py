"""Comprensión de la consulta: categoría, ¿mod o Vanilla?, y reescritura de seguimientos."""
from __future__ import annotations
import json
import logging
import re

from ..core import config as cfg
from . import llm
from .sources import (
    MODRINTH_LOADERS, MODRINTH_TYPES, WIKI_TERM_MAP, build_modrinth_query, curated_documents,
    detect_mod_loader, detect_mod_project_type,
)
from .textutils import tokenize

log = logging.getLogger("gameguide.intent")

MOD_PATTERN = re.compile(
    r"\b(mods?|mod ?packs?|shaders?|neoforge|forge|fabric|quilt|modrinth|curseforge|"
    r"resource ?packs?|texture ?packs?|paquetes? de (?:recursos|texturas))\b"
)


def is_mod_request(question: str) -> bool:
    # Usa límites de palabra para no confundir "modo", "modificar" o "moderno" con "mod".
    return bool(MOD_PATTERN.search(question.lower()))


def classify_category(question: str) -> str:
    q = question.lower()
    if is_mod_request(question):
        return "mods"
    if any(x in q for x in ["misión", "misiones", "avance", "progreso", "advancement", "quest"]):
        return "misiones"
    if any(x in q for x in ["personaje", "aldeano", "mob", "criatura", "dragón", "zombie", "creeper"]):
        return "personajes"
    if any(x in q for x in ["objeto", "ítem", "item", "bloque", "armadura", "herramienta", "craftear", "receta",
                            "élitra", "elitra", "elytra", "diamante", "netherita", "tridente", "espada", "pico"]):
        return "objetos"
    if any(x in q for x in ["cómo", "como", "mecánica", "mecanica", "redstone", "encantamiento", "portal", "granja", "comando"]):
        return "mecanicas"
    return "general"


def has_vanilla_signal(question: str) -> bool:
    """¿La pregunta menciona claramente algo del juego base? Si sí, no hace falta llamar a la IA."""
    q = " " + question.lower() + " "
    if classify_category(question) != "general":
        return True
    if any(f" {term} " in q or f" {term}?" in q or f" {term}," in q for term in WIKI_TERM_MAP):
        return True
    return bool(curated_documents(question, limit=1))


INTENT_PROMPT = "\n".join([
    "Eres un clasificador para un chatbot de Minecraft. Analiza la pregunta del jugador y responde SOLO un objeto JSON con estas claves:",
    '- "mod": true si pregunta por un mod, modpack, shader, paquete de recursos o contenido de la comunidad, incluso si solo escribe el nombre '
    "(por ejemplo Sodium, Create, JEI, Iris, Xaero's Minimap, Distant Horizons, Lithium). false si trata del juego base (Vanilla).",
    '- "terms": palabras clave en INGLÉS para buscar el proyecto en Modrinth (el nombre del mod si aparece; máximo 6 palabras). Vacío si "mod" es false.',
    '- "project_type": "mod", "modpack", "shader" o "resourcepack".',
    '- "loader": "fabric", "forge", "neoforge" o "quilt" solo si el jugador lo menciona; si no, null.',
])


def _parse_json_object(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.I | re.M).strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.S)
        return json.loads(match.group(0)) if match else {}


def understand_query(question: str, edition="No especificada", game_version="") -> dict:
    """Reglas primero. La IA solo se llama cuando la pregunta es ambigua (p. ej. solo el nombre de un mod)."""
    intent = {
        "mod": is_mod_request(question), "terms": "",
        "project_type": detect_mod_project_type(question),
        "loader": detect_mod_loader(question), "by": "reglas",
    }
    if intent["mod"]:
        intent["terms"] = build_modrinth_query(question)
        return intent
    if has_vanilla_signal(question) or not cfg.USE_LLM_INTENT or not llm.is_configured():
        return intent
    contents = f"Edición: {edition}\nVersión: {game_version or 'no indicada'}\nPregunta: {question}"
    try:
        result = llm.generate(INTENT_PROMPT, [{"role": "user", "content": contents}],
                              json_mode=True, temperature=0, max_tokens=200)
        data = _parse_json_object(result.text)
        if isinstance(data, dict):
            intent["mod"] = bool(data.get("mod") is True)
            terms = re.sub(r"[^\w\s'\-áéíóúñü]", " ", str(data.get("terms") or ""))
            intent["terms"] = re.sub(r"\s+", " ", terms).strip()[:100]
            if data.get("project_type") in MODRINTH_TYPES:
                intent["project_type"] = data["project_type"]
            if data.get("loader") in MODRINTH_LOADERS:
                intent["loader"] = data["loader"]
            intent["by"] = result.model
    except Exception as exc:
        log.info("Intención por IA no disponible, se usan reglas: %s", str(exc)[:150])
    return intent


REWRITE_PROMPT = (
    "Reescribe la ÚLTIMA pregunta del jugador como una pregunta completa e independiente en español, "
    "resolviendo pronombres y referencias con ayuda del historial (por ejemplo 'y cómo la reparo?' -> "
    "'¿Cómo se reparan las élitras en Minecraft?'). Responde SOLO con la pregunta reescrita, sin comillas ni explicaciones."
)


def standalone_question(question: str, history: list[dict]) -> str:
    """Convierte un seguimiento en una pregunta independiente para recuperar mejor."""
    prior = [h for h in history if h.get("role") in ("user", "assistant")]
    prior_users = [str(h.get("content", "")) for h in prior if h.get("role") == "user"]
    if not prior_users:
        return question
    short = len(tokenize(question)) <= 8
    if not short:
        return question
    if llm.is_configured():
        convo = "\n".join(f"{h['role']}: {str(h.get('content',''))[:400]}" for h in prior[-4:])
        try:
            result = llm.generate(REWRITE_PROMPT,
                                  [{"role": "user", "content": f"HISTORIAL:\n{convo}\n\nÚLTIMA PREGUNTA: {question}"}],
                                  temperature=0, max_tokens=120)
            rewritten = result.text.strip().strip('"“”').splitlines()[0].strip()
            if 3 <= len(rewritten) <= 300:
                return rewritten
        except Exception as exc:
            log.info("No se pudo reescribir el seguimiento: %s", str(exc)[:150])
    # Respaldo sin IA: pregunta anterior + nueva (solo si la nueva es muy corta).
    return (prior_users[-1] + " " + question) if len(tokenize(question)) <= 4 else question
