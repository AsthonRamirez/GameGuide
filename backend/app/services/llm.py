"""Capa de IA intercambiable: Gemini (por defecto) o cualquier API compatible con OpenAI.

Cambiar de proveedor solo requiere variables de entorno (ver .env.example); el resto del
código no se modifica, de modo que Gemini, Mistral o Groq se pueden comparar de forma justa.
"""
from __future__ import annotations
import logging
import re
import time
from dataclasses import dataclass

import requests

from ..core import config as cfg

log = logging.getLogger("gameguide.llm")

_gemini_client = None


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    model: str
    finish_reason: str = ""

    @property
    def truncated(self) -> bool:
        return self.finish_reason.upper() in {"MAX_TOKENS", "LENGTH"}


def is_configured() -> bool:
    if cfg.LLM_PROVIDER == "openai":
        return bool(cfg.LLM_API_KEY)
    return bool(cfg.GEMINI_API_KEY)


def model_chain() -> list[str]:
    if cfg.LLM_PROVIDER == "openai":
        chain = [cfg.LLM_MODEL, cfg.LLM_BACKUP_MODEL]
    else:
        chain = [cfg.GEMINI_PRIMARY_MODEL, cfg.GEMINI_BACKUP_MODEL]
    out = []
    for m in chain:
        if m and m not in out:
            out.append(m)
    return out


def _gemini():
    global _gemini_client
    if not cfg.GEMINI_API_KEY:
        raise LLMError("Falta GEMINI_API_KEY en backend/.env")
    if _gemini_client is None:
        from google import genai
        _gemini_client = genai.Client(api_key=cfg.GEMINI_API_KEY)
    return _gemini_client


def _retry_delay(message: str) -> float:
    """Extrae el tiempo de espera sugerido por un error 429 (si existe), con tope de 8 s."""
    m = re.search(r"retry(?:Delay)?\D{0,12}(\d+(?:\.\d+)?)\s*s", message, flags=re.I)
    return min(float(m.group(1)), 8.0) if m else 2.0


def _call_gemini(model, system, messages, json_mode, temperature, max_tokens) -> LLMResult:
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in messages
    ]
    config = {"system_instruction": system, "temperature": temperature, "max_output_tokens": max_tokens}
    if json_mode:
        config["response_mime_type"] = "application/json"
    response = _gemini().models.generate_content(model=model, contents=contents, config=config)
    text = (getattr(response, "text", None) or "").strip()
    finish = ""
    try:
        finish = str(response.candidates[0].finish_reason.name)
    except Exception:
        pass
    return LLMResult(text, model, finish)


def _call_openai(model, system, messages, json_mode, temperature, max_tokens) -> LLMResult:
    if not cfg.LLM_API_KEY:
        raise LLMError("Falta LLM_API_KEY en backend/.env")
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    r = requests.post(
        cfg.LLM_BASE_URL.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {cfg.LLM_API_KEY}"},
        json=body, timeout=60,
    )
    if r.status_code >= 400:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
    choice = r.json()["choices"][0]
    return LLMResult((choice["message"].get("content") or "").strip(), model, choice.get("finish_reason") or "")


def generate(system: str, messages: list[dict], *, json_mode=False, temperature=None,
             max_tokens=None, models: list[str] | None = None) -> LLMResult:
    """Prueba cada modelo de la cadena; reintenta una vez ante 429/503 antes de pasar al respaldo."""
    temperature = cfg.LLM_TEMPERATURE if temperature is None else temperature
    max_tokens = max_tokens or cfg.LLM_MAX_OUTPUT_TOKENS
    call = _call_openai if cfg.LLM_PROVIDER == "openai" else _call_gemini
    errors = []
    for model in (models or model_chain()):
        for attempt in (1, 2):
            try:
                result = call(model, system, messages, json_mode, temperature, max_tokens)
                if not result.text:
                    raise LLMError("respuesta vacía")
                return result
            except Exception as exc:
                message = str(exc)
                lower = message.lower()
                errors.append(f"{model}: {message[:200]}")
                log.warning("LLM %s falló (intento %d): %s", model, attempt, message[:200])
                if any(x in lower for x in ("401", "403", "api key", "permission denied", "unauthorized")):
                    raise LLMError("; ".join(errors))
                transient = any(x in lower for x in ("429", "503", "resource_exhausted", "unavailable", "overloaded", "rate"))
                if attempt == 1 and transient:
                    time.sleep(_retry_delay(message))
                    continue
                break  # pasa al modelo de respaldo
    raise LLMError("; ".join(errors))


def check_models() -> None:
    """Avisa en el log si los modelos configurados no existen para esta llave."""
    if cfg.LLM_PROVIDER != "gemini" or not cfg.GEMINI_API_KEY:
        return
    try:
        available = {m.name.split("/")[-1] for m in _gemini().models.list()}
        for model in model_chain():
            if model not in available:
                log.warning("El modelo '%s' NO aparece disponible para tu llave de Gemini. "
                            "Revisa GEMINI_PRIMARY_MODEL / GEMINI_BACKUP_MODEL.", model)
    except Exception as exc:
        log.info("No se pudo verificar la lista de modelos: %s", str(exc)[:150])
