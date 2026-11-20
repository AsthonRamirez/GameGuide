from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import APP_NAME, FRONTEND_ORIGINS
from .api.routes import router
from .services.gameguide import initialize_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_data()
    yield


app = FastAPI(title=APP_NAME, version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,          # solo el/los orígenes configurados en FRONTEND_ORIGIN
    allow_credentials=False,                 # la API no usa cookies
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.include_router(router)


@app.get("/")
def root():
    return {"message": "GameGuide AI API", "docs": "/docs", "health": "/api/health"}
