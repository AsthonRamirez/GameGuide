# 🎮 GameGuide AI

Asistente inteligente de Minecraft con recuperación aumentada (RAG), búsqueda semántica, chatbot conversacional, biblioteca pública de consultas y analítica.

## Funcionalidades

- **Tres vistas:** dashboard de KPIs, asistente conversacional y biblioteca pública.
- **Dashboard:** indicadores reales de Supabase y gráficas de actividad diaria, categorías y likes/dislikes.
- **Chat:** consultas de Minecraft Vanilla, mecánicas, criaturas, objetos, crafteos y contenido de Modrinth.
- **Biblioteca pública:** muestra las consultas principales compartidas por la comunidad y sus respuestas.
- **Likes / dislikes:** cada dispositivo puede emitir un voto por consulta y cambiarlo posteriormente.
- **Persistencia:** se almacena solo la primera pregunta y la primera respuesta de cada sesión. Los mensajes de seguimiento no se guardan como consultas separadas.
- **Búsqueda semántica local:** FastEmbed con `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` genera embeddings localmente y Supabase pgvector recupera documentos por similitud. No requiere una API de embeddings de pago.
- **Recuperación híbrida (v1.1):** los documentos se dividen en fragmentos de ~800 caracteres; los documentos recién descargados y los ya guardados se rankean **juntos** con búsqueda semántica (con umbral de similitud) + BM25, fusionados por posición (RRF).
- **Fallback:** si pgvector o FastEmbed no están disponibles, la recuperación usa BM25; `backend/app/data/curated_faq.json` contiene fichas curadas de las preguntas más frecuentes de Vanilla.
- **IA intercambiable:** Gemini por defecto; cualquier API compatible con OpenAI (Mistral, Groq…) con solo cambiar variables de entorno.
- **Seguridad:** límite de peticiones por IP, CORS restringido, RLS en Supabase y filtro para no publicar consultas con datos personales.
- **Modrinth:** búsqueda de mods, modpacks, shaders y resource packs.

## Stack

| Componente | Tecnología |
|---|---|
| Frontend | Vue 3 + Vite |
| Gráficas | Chart.js + vue-chartjs |
| Backend | Python + FastAPI |
| Generación | Google Gemini |
| Embeddings locales | FastEmbed (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) |
| Persistencia | Supabase PostgreSQL |
| Búsqueda vectorial | pgvector |
| Fuentes de mods | Modrinth API |
| Fuentes Vanilla | Minecraft Wiki y páginas oficiales cuando están disponibles |

## Estructura

```text
GameGuide-main/
├── backend/
│   ├── app/
│   │   ├── api/                 # Rutas y esquemas HTTP
│   │   ├── core/                # Configuración y límite de peticiones
│   │   ├── data/                # curated_faq.json (fichas curadas)
│   │   └── services/
│   │       ├── sources.py       # Wiki, Help Center, minecraft.net, Modrinth, fichas
│   │       ├── retrieval.py     # Recuperación híbrida y ranking (chunks + BM25 + RRF)
│   │       ├── intent.py        # Categoría, ¿mod?, reescritura de seguimientos
│   │       ├── generation.py    # Prompt y respuesta
│   │       ├── llm.py           # Proveedor de IA intercambiable (Gemini / OpenAI-compatible)
│   │       ├── embeddings.py    # Embeddings locales (FastEmbed)
│   │       ├── persistence.py   # Supabase, votos y métricas
│   │       └── textutils.py     # BM25, chunking, RRF
│   ├── scripts/                 # backfill_chunks.py, eval_retrieval.py
│   ├── tests/                   # pytest + eval_questions.json
│   ├── .env.example
│   └── requirements.txt
├── docs/OPTIMIZACION.md         # Qué se cambió y por qué
├── database/
│   └── supabase_schema.sql      # Tablas, migraciones y función pgvector
└── frontend/
    ├── src/
    │   ├── App.vue              # Tres vistas
    │   └── assets/main.css
    ├── package.json
    └── vite.config.js
```

## Requisitos

- Python 3.12 recomendado (3.14 da problemas de compatibilidad en Windows).
- Node.js LTS y npm.
- Proyecto Supabase.
- API Key de Gemini.
- Conexión a internet la primera vez que FastEmbed descargue el modelo multilingüe.

## Configuración inicial

### 1. Configurar Supabase

En Supabase abre **SQL Editor** y ejecuta el archivo completo:

`database/supabase_schema.sql`

El script:
- habilita `pgcrypto` y `vector`;
- crea/actualiza `knowledge_documents` con embeddings de 384 dimensiones;
- crea/actualiza `chat_interactions` con `is_public`;
- crea `chat_votes` para likes/dislikes;
- elimina la columna de comentarios de la tabla de feedback antigua, si existe;
- crea `knowledge_chunks` y la función `match_knowledge_chunks` (búsqueda semántica por fragmentos, con umbral);
- crea `dashboard_metrics` (métricas calculadas en SQL) y activa RLS en todas las tablas;
- endurece `match_chat_interactions` (misma edición/versión, con evidencia, sin dislikes).

**Si vienes de la versión anterior**, después de ejecutar el SQL indexa tus documentos guardados:

```powershell
cd backend
python -m scripts.backfill_chunks
```

Si ya tienes datos de la versión anterior, realiza primero un respaldo. El script conserva las consultas existentes y añade las columnas/tablas necesarias. No borra las consultas históricas.

### 2. Backend

En PowerShell:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Configura `backend/.env`:

```dotenv
GEMINI_API_KEY=tu_api_key
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_SERVICE_ROLE_KEY=tu_service_role_key

GEMINI_PRIMARY_MODEL=gemini-3.6-flash
GEMINI_BACKUP_MODEL=gemini-3.8-flash
CACHE_TTL_DAYS=14
FRONTEND_ORIGIN=http://localhost:5173
```

Para comparar proveedores sin tocar código: `LLM_PROVIDER=openai`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` (ver `.env.example`).

No compartas el archivo `.env` ni publiques la `SUPABASE_SERVICE_ROLE_KEY`.

Inicia el backend:

```powershell
python -m uvicorn app.main:app --reload
```

URLs:
- API: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/health

### 3. Frontend

Abre una segunda terminal:

```powershell
cd frontend
npm install
npm run dev
```

Abre http://localhost:5173

El proxy de Vite envía `/api` a `http://127.0.0.1:8000`.

## Cómo funciona el almacenamiento

1. El primer mensaje del usuario inicia una sesión.
2. La primera pregunta y su primera respuesta se insertan en `chat_interactions` y se publican en la biblioteca.
3. Los siguientes mensajes de esa misma sesión se procesan con el historial enviado por el frontend, pero no se insertan en `chat_interactions`.
4. La biblioteca consulta solo las filas `is_public = true`.
5. Los votos se guardan en `chat_votes`. La combinación `interaction_id + voter_id` es única: el mismo dispositivo puede cambiar su voto, no duplicarlo.
6. El frontend genera un identificador anónimo en el almacenamiento local del navegador. No equivale a una cuenta ni impide que una persona use otro dispositivo o navegador para votar.

## Búsqueda semántica y costos

FastEmbed ejecuta el modelo `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` localmente en el backend. Los vectores se guardan en Supabase y se comparan mediante pgvector. No se factura una API de embeddings. La descarga inicial del modelo requiere internet y puede tardar; después se reutiliza localmente.

Si el modelo no puede cargarse o la función pgvector no está instalada, el backend informa el problema en la terminal y usa BM25 como respaldo. La generación de respuestas continúa usando Gemini, que puede estar sujeto a límites y condiciones del proveedor.

## Endpoints principales

| Método | Ruta | Función |
|---|---|---|
| GET | `/api/health` | Estado de servicios |
| GET | `/api/dashboard` | KPIs y series para gráficas |
| POST | `/api/chat` | Chat conversacional |
| GET | `/api/public/consultations` | Biblioteca pública |
| POST | `/api/public/consultations/{id}/vote` | Guardar o cambiar like/dislike |

## Consideraciones

- Los registros son permanentes mientras no se eliminen desde Supabase.
- Las consultas se publican por defecto; no se deben incluir datos personales en las preguntas.
- El voto anónimo se identifica por navegador/dispositivo, no por usuario autenticado.
- La búsqueda semántica depende de que se haya ejecutado el SQL y que la columna embedding y la función RPC existan.
- Las fuentes externas pueden fallar o cambiar. GameGuide AI intenta fuentes alternativas y no debe presentar una fuente comunitaria como oficial.
- La ficha de élitras es un respaldo puntual; no sustituye la recuperación de fuentes actualizadas para todas las preguntas Vanilla.

---

**GameGuide AI** · Explora Minecraft. Descubre. Aprende. Juega.


## Pruebas y evaluación

```powershell
cd backend
pip install -r requirements-dev.txt
python -m pytest -q                       # pruebas automáticas (sin red ni cuota)
python -m scripts.eval_retrieval          # mide la recuperación con 26 preguntas reales
python -m scripts.eval_retrieval --answers --csv resultados.csv   # además evalúa las respuestas
```
