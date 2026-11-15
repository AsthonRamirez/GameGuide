# Backend — GameGuide AI

## Requisitos
- Python 3.10 o superior
- Una clave de Gemini
- Proyecto Supabase con las tablas descritas en `../database/supabase_schema.sql`

## Instalación (PowerShell)
```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```
Completa las variables del `.env` y ejecuta:
```powershell
uvicorn app.main:app --reload
```
API: http://127.0.0.1:8000 · Swagger: http://127.0.0.1:8000/docs

No compartas el archivo `.env`. `SUPABASE_SERVICE_ROLE_KEY` se usa únicamente desde el backend.
