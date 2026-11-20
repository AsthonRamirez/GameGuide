# Backend — GameGuide AI

FastAPI coordina el chat, Gemini, Modrinth, recuperación semántica y persistencia Supabase.

## Instalación (PowerShell)

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Configura `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` y los modelos Gemini en `.env`.

Antes de arrancar el backend, ejecuta (de nuevo si actualizas desde una versión anterior) `../database/supabase_schema.sql` en Supabase SQL Editor. El script habilita pgvector, crea la biblioteca/votos y las funciones RPC para buscar documentos y respuestas previas.

```powershell
python -m uvicorn app.main:app --reload
```

API: http://127.0.0.1:8000 · Swagger: http://127.0.0.1:8000/docs

Si ya tenías documentos guardados, ejecuta una vez `python -m scripts.backfill_chunks` para fragmentarlos y vectorizarlos.

FastEmbed descarga el modelo multilingüe gratuito la primera vez que vectoriza el conocimiento. La descarga requiere internet; los embeddings se calculan localmente. Si no está disponible, el servicio conserva BM25 como alternativa.

No compartas el archivo `.env`. `SUPABASE_SERVICE_ROLE_KEY` se utiliza exclusivamente desde el backend.

## Variables de entorno principales

Ver `.env.example`. Las más útiles para ajustar la calidad: `SEMANTIC_MIN_SIMILARITY` (umbral de relevancia, 0.30 por defecto),
`CHUNK_SIZE`/`CHUNK_OVERLAP`, `MAX_CONTEXT_CHUNKS`, `REUSE_THRESHOLD` y `LLM_PROVIDER`.
Mide el efecto de cada cambio con `python -m scripts.eval_retrieval`.
