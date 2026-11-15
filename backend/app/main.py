from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import APP_NAME, FRONTEND_ORIGIN
from .api.routes import router
from .services.gameguide import initialize_data

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_data()
    yield

app = FastAPI(title=APP_NAME, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

@app.get("/")
def root():
    return {"message": "GameGuide AI API", "docs": "/docs", "health": "/api/health"}
