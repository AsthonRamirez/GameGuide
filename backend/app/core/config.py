"""Configuración central. Todo se lee de variables de entorno (backend/.env)."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/

# Los modelos de FastEmbed se guardan fuera de Temp para no volver a descargarlos (~250 MB).
os.environ.setdefault("FASTEMBED_CACHE_PATH", str(BASE_DIR / ".cache" / "fastembed"))


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


APP_NAME = "GameGuide AI API"

# --- CORS: uno o varios orígenes separados por coma -------------------------------
FRONTEND_ORIGINS = [
    o.strip() for o in os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").split(",") if o.strip()
]
for _extra in ("http://127.0.0.1:5173",):
    if _extra not in FRONTEND_ORIGINS and os.getenv("FRONTEND_ORIGIN_STRICT", "0") != "1":
        FRONTEND_ORIGINS.append(_extra)
FRONTEND_ORIGIN = FRONTEND_ORIGINS[0]  # compatibilidad

# --- Supabase ----------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# --- Proveedor de IA (intercambiable) ----------------------------------------------
# LLM_PROVIDER=gemini  -> usa GEMINI_API_KEY y los modelos GEMINI_*
# LLM_PROVIDER=openai  -> cualquier API compatible con OpenAI (Mistral, Groq, OpenRouter, Ollama...)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_PRIMARY_MODEL = os.getenv("GEMINI_PRIMARY_MODEL", "gemini-3.8-flash")
GEMINI_BACKUP_MODEL = os.getenv("GEMINI_BACKUP_MODEL", "gemini-3.6-flash")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.mistral.ai/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "mistral-small-latest")
LLM_BACKUP_MODEL = os.getenv("LLM_BACKUP_MODEL", "")

LLM_TEMPERATURE = _float("LLM_TEMPERATURE", 0.3)
LLM_MAX_OUTPUT_TOKENS = _int("LLM_MAX_OUTPUT_TOKENS", 2048)
USE_LLM_INTENT = os.getenv("USE_LLM_INTENT", "1") == "1"

# --- Recuperación ------------------------------------------------------------------
CACHE_TTL_DAYS = _int("CACHE_TTL_DAYS", 14)
MAX_CONTEXT_CHUNKS = _int("MAX_CONTEXT_CHUNKS", 6)
MAX_CHUNKS_PER_DOC = _int("MAX_CHUNKS_PER_DOC", 2)
CHUNK_SIZE = _int("CHUNK_SIZE", 800)          # caracteres por fragmento
CHUNK_OVERLAP = _int("CHUNK_OVERLAP", 150)    # traslape entre fragmentos
MAX_LIVE_CHUNKS_EMBEDDED = _int("MAX_LIVE_CHUNKS_EMBEDDED", 40)
SEMANTIC_MIN_SIMILARITY = _float("SEMANTIC_MIN_SIMILARITY", 0.30)
RRF_K = 60

# --- Reutilización de respuestas ---------------------------------------------------
REUSE_ENABLED = os.getenv("REUSE_ENABLED", "1") == "1"
REUSE_THRESHOLD = _float("REUSE_THRESHOLD", 0.93)

# --- Límite de peticiones por IP ---------------------------------------------------
RATE_LIMIT_CHAT_PER_MIN = _int("RATE_LIMIT_CHAT_PER_MIN", 8)
RATE_LIMIT_VOTE_PER_MIN = _int("RATE_LIMIT_VOTE_PER_MIN", 30)
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "0") == "1"

# --- Dashboard ---------------------------------------------------------------------
DASHBOARD_CACHE_SECONDS = _int("DASHBOARD_CACHE_SECONDS", 60)
