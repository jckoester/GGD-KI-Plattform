from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.auth.router import router as auth_router
from app.preferences.router import router as preferences_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Adapter vorab instanziieren — Konfigurationsfehler früh sichtbar
    from app.auth.dependencies import get_auth_adapter
    get_auth_adapter()
    yield


app = FastAPI(title="GGD-KI-Plattform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(preferences_router)
