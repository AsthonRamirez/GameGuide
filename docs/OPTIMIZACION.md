# Optimización de GameGuide (rama Actividad-5) — resumen de cambios

## Causa raíz de las respuestas malas
`retrieve_knowledge` descargaba documentos en vivo, pero hacía la búsqueda semántica sobre lo **ya guardado**
(sin umbral, así que siempre devolvía algo) y descartaba lo recién descargado. Además, las páginas enteras se
vectorizaban como un único embedding difuso. Para "¿Cómo consigo las élitras?" Gemini recibía páginas oficiales
de actualizaciones en lugar del artículo de las élitras.

## Qué cambió

| Área | Antes | Ahora |
|---|---|---|
| Ranking | Semántico sobre lo guardado; lo nuevo se tiraba | Documentos en vivo + guardados rankeados **juntos** (semántico con umbral + BM25, fusión RRF) |
| Granularidad | Página completa (embedding de los primeros 6000 car.) | Fragmentos de ~800 car. con traslape; máx. 2 por documento |
| Umbral | Ninguno | `SEMANTIC_MIN_SIMILARITY` (0.30); sin evidencia → reintenta con otra consulta |
| Wiki | Frase completa + edición + versión; `exchars=8000` (la API de extractos recorta ese valor); varios títulos por petición | Palabras clave en inglés; una página completa por petición, en paralelo |
| Fuentes oficiales | Siempre en el contexto | Solo si la pregunta trata de versiones/soporte |
| Respaldo curado | Una ficha (élitras), nunca se ejecutaba | `curated_faq.json` con 17 fichas, entra al ranking como candidata |
| Seguimientos | Regla de ≤4 palabras | Reescritura como pregunta independiente (IA; regla como respaldo) |
| Reutilización | 0.88, cualquier edición/versión | 0.93, misma edición y versión, con evidencia, sin dislikes |
| Llamadas a IA | 2 por pregunta (intención + respuesta) | 1 normalmente; la intención solo se pide si la pregunta es ambigua |
| Guardado | Antes de responder, fila por fila | En segundo plano, por lotes, sin recalcular lo ya guardado hace <24 h |
| Estado global | `LAST_RETRIEVAL_INFO` compartido entre usuarios | Eliminado; el detalle va en el campo `debug` de la respuesta y en el log |
| Generación | Historial pegado como texto; 1400 tokens; sin temperatura | Turnos reales; 2048 tokens; temperatura 0.3; avisa si se corta; reintento ante 429 |
| Dashboard | Hasta 5000 filas contadas en Python | Agregados en SQL (`dashboard_metrics`) + caché de 60 s |
| Biblioteca | Todos los votos en cada llamada | Solo los de las filas mostradas |
| Seguridad | Sin límite, CORS amplio | Límite por IP, CORS estricto, RLS, no publica correos/teléfonos/credenciales |
| Código | `gameguide.py` de 938 líneas; código muerto de Colab; pandas/plotly | 8 módulos; código muerto eliminado; dependencias fijadas |
| Arranque | Vectorizaba fila por fila; primera consulta esperaba la descarga | Modelo precargado en segundo plano; backfill en un script aparte |

## Cómo aplicarlo
1. Ejecuta `database/supabase_schema.sql` en el SQL Editor (es idempotente).
2. `pip install -r requirements.txt` (Python 3.12).
3. `python -m scripts.backfill_chunks` (indexa lo que ya tenías guardado).
4. Revisa `GEMINI_PRIMARY_MODEL` / `GEMINI_BACKUP_MODEL`: al arrancar, el log avisa si no existen para tu llave.
5. `python -m pytest -q` y `python -m scripts.eval_retrieval` para medir.

## Pendiente / no incluido
- `edition` (Java/Bedrock) sigue sin filtrar la recuperación de Vanilla (solo se pasa al prompt).
- La moderación de contenido ofensivo no está implementada (solo el filtro de datos personales).
- El límite de peticiones es en memoria: con varios procesos/instancias habría que moverlo a Redis.
- `SEMANTIC_MIN_SIMILARITY=0.30` es un valor inicial: afínalo con `scripts.eval_retrieval`.
