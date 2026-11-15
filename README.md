# 🎮 GameGuide AI

### Tu asistente inteligente para Minecraft

GameGuide AI es un asistente inteligente diseñado para resolver dudas sobre **Minecraft Vanilla**, mecánicas del juego, criaturas, objetos, crafteos, dimensiones y contenido de la comunidad.

Además, permite descubrir mods, modpacks y shaders mediante la integración con **Modrinth**.

El proyecto utiliza inteligencia artificial generativa con Gemini, recuperación de información (RAG) y una interfaz web moderna desarrollada con Vue 3.

---

## ✨ Características principales

- 🤖 **Inteligencia artificial con Gemini:** generación de respuestas mediante modelos de Google Gemini.
- ⛏️ **Conocimiento de Minecraft Vanilla:** consultas sobre criaturas, bloques, objetos, recetas, dimensiones y mecánicas.
- 🧩 **Búsqueda de contenido en Modrinth:** descubrimiento de mods, modpacks y shaders.
- 📚 **Sistema RAG:** recuperación de información para proporcionar respuestas contextualizadas.
- 🗄️ **Supabase:** almacenamiento de información, caché de conocimiento y datos de la aplicación.
- 📊 **Panel de métricas:** visualización de información y estadísticas disponibles.
- 💬 **Sistema de feedback:** permite valorar si las respuestas fueron útiles.
- ⚡ **Interfaz moderna:** aplicación web desarrollada con Vue 3 y Vite.
- 🔌 **API REST:** backend desarrollado con Python y FastAPI.

---

## 🛠️ Tecnologías utilizadas

| Tecnología | Uso |
|---|---|
| Vue 3 | Interfaz de usuario |
| Vite | Entorno de desarrollo frontend |
| Python | Lenguaje del backend |
| FastAPI | API REST |
| Google Gemini | Generación de respuestas |
| Supabase | Base de datos y almacenamiento |
| Modrinth API | Consulta de contenido de Minecraft |
| RAG | Recuperación de información contextual |

---

## 📁 Estructura del proyecto

```text
GameGuide_AI/
│
├── backend/
│   ├── app/
│   │   ├── api/              # Endpoints y esquemas HTTP
│   │   ├── core/             # Configuración de la aplicación
│   │   └── services/         # Servicios y lógica de negocio
│   │
│   ├── .env.example          # Plantilla de variables de entorno
│   └── requirements.txt     # Dependencias de Python
│
├── frontend/
│   ├── src/
│   │   ├── assets/           # Recursos gráficos
│   │   └── components/       # Componentes Vue
│   │
│   └── package.json          # Dependencias del frontend
│
├── database/
│   └── supabase_schema.sql   # Esquema de base de datos
│
├── .gitignore
└── README.md
```

---

## 🚀 Instalación y configuración

### 1. Requisitos previos

Antes de comenzar, asegúrate de tener instalados:

- [Python](https://www.python.org/downloads/)
- [Node.js](https://nodejs.org/)
- [Git](https://git-scm.com/)
- [Visual Studio Code](https://code.visualstudio.com/)

También necesitarás:

- Un proyecto de [Google AI Studio](https://aistudio.google.com/) para obtener tu API Key de Gemini.
- Un proyecto de [Supabase](https://supabase.com/) para configurar la base de datos.

### 2. Clonar el repositorio

```bash
git clone URL_DEL_REPOSITORIO
cd GameGuide_AI
```

### 3. Configurar Supabase

1. Crea un proyecto en Supabase.
2. Abre el apartado **SQL Editor**.
3. Ejecuta el contenido de `database/supabase_schema.sql`.

> Si ya tienes las tablas creadas desde la versión anterior del proyecto, compara el esquema antes de ejecutar cambios. El script utiliza `IF NOT EXISTS` y no modifica las tablas existentes.

### 4. Configurar el backend

Abre una terminal y ejecuta:

**Windows PowerShell:**

```powershell
cd backend

# Crear entorno virtual
py -m venv .venv

# Activar entorno virtual
.venv\Scripts\Activate.ps1

# Instalar dependencias
pip install -r requirements.txt

# Crear archivo de configuración
Copy-Item .env.example .env
```

Abre `backend/.env` y configura tus credenciales:

```env
GEMINI_API_KEY=tu_api_key_de_gemini

SUPABASE_URL=tu_url_de_supabase

SUPABASE_SERVICE_ROLE_KEY=tu_service_role_key
```

Completa también las demás variables que aparezcan en `.env.example`.

**Importante:** nunca compartas tu archivo `.env` ni publiques tus claves API. El archivo está excluido del repositorio mediante `.gitignore`.

### 5. Iniciar el backend

Desde la carpeta `backend`, con el entorno virtual activado:

```powershell
uvicorn app.main:app --reload
```

La API estará disponible en:

- API: http://127.0.0.1:8000
- Documentación Swagger: http://127.0.0.1:8000/docs
- Estado del servicio: http://127.0.0.1:8000/api/health

### 6. Configurar el frontend

Abre una segunda terminal:

```powershell
cd frontend

# Instalar dependencias
npm install

# Iniciar servidor de desarrollo
npm run dev
```

Vite mostrará la dirección local de la aplicación. Normalmente:

http://localhost:5173

---

## ⚙️ Funcionamiento general

GameGuide AI utiliza una arquitectura dividida en dos partes:

**Frontend — Vue 3 + Vite**

Se encarga de mostrar la interfaz, recibir las consultas del usuario, presentar las respuestas y gestionar las interacciones con la aplicación.

**Backend — Python + FastAPI**

Procesa las solicitudes, coordina la recuperación de información, consulta los servicios externos y gestiona la generación de respuestas mediante Gemini.

**Servicios externos**

- **Gemini:** generación de respuestas mediante inteligencia artificial.
- **Supabase:** almacenamiento y recuperación de información.
- **Modrinth:** búsqueda de mods, modpacks y shaders.

El frontend se comunica con FastAPI mediante rutas `/api`. Durante el desarrollo, Vite redirige estas solicitudes al backend.

---

## 🔧 Ajustes y mejoras de esta versión

Esta versión incorpora mejoras realizadas durante la migración desde Google Colab a una arquitectura independiente con Python y Vue 3.

- Migración del proyecto original de Google Colab a un backend FastAPI y frontend Vue 3 + Vite.
- Corrección del sistema de envío de feedback para aceptar los valores enviados directamente desde Vue.
- Optimización de las búsquedas en Modrinth, reduciendo las consultas secuenciales y utilizando un intento de respaldo.
- Reducción de los tiempos de espera en las consultas externas.
- Reconocimiento de nombres de mods como `Farmer's Delight` incluso cuando las preguntas están formuladas en español.
- Separación entre el conocimiento de Minecraft Vanilla y el contenido comunitario.
- Conservación de la vigencia de 14 días para la caché de conocimiento implementada en el proyecto original.

---

## ⚠️ Consideraciones importantes

- Gemini y Supabase requieren credenciales válidas para utilizar las funcionalidades que dependen de estos servicios.
- Modrinth se consulta mediante su API pública.
- El panel de métricas utiliza datos reales de Supabase cuando está configurado; el escenario académico mostrado por separado es simulado.
- Si faltan credenciales, algunas funcionalidades no estarán disponibles. La ruta `/api/health` permite consultar el estado de los servicios.
- Los nombres de los modelos Gemini se configuran mediante las variables `GEMINI_PRIMARY_MODEL` y `GEMINI_BACKUP_MODEL`, si están definidas en la configuración del backend.
- La compatibilidad con Supabase depende de que las tablas y columnas coincidan con el esquema esperado por la aplicación.

---

## 🔐 Seguridad

Este proyecto utiliza variables de entorno para proteger las credenciales y configuraciones privadas.

Los archivos `.env` y los entornos virtuales están excluidos mediante `.gitignore`.

**No publiques claves API, contraseñas ni credenciales de Supabase en el repositorio.**

---

## 📌 Estado del proyecto

Proyecto en desarrollo. Esta versión representa la migración de GameGuide AI desde Google Colab hacia una arquitectura web independiente con FastAPI y Vue 3.

---

**GameGuide AI**  
*Explora Minecraft. Descubre. Aprende. Juega.* 🎮