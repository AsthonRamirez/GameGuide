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

Antes de arrancar el backend, ejecuta `../database/supabase_schema.sql` en Supabase SQL Editor. El script habilita pgvector, crea la biblioteca/votos y las funciones RPC para buscar documentos y respuestas previas.

```powershell
python -m uvicorn app.main:app --reload
```

API: http://127.0.0.1:8000 · Swagger: http://127.0.0.1:8000/docs

FastEmbed descarga el modelo multilingüe gratuito la primera vez que vectoriza el conocimiento. La descarga requiere internet; los embeddings se calculan localmente. Si no está disponible, el servicio conserva BM25 como alternativa.

No compartas el archivo `.env`. `SUPABASE_SERVICE_ROLE_KEY` se utiliza exclusivamente desde el backend.
