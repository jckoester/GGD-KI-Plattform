import logging
import logging.config
from contextlib import asynccontextmanager

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(levelname)s:     %(name)s - %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stderr",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {"app": {"level": "DEBUG", "propagate": True}},
})

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.auth.router import router as auth_router
from app.db.session import AsyncSessionLocal
from app.db.models import ExchangeRate
from app.preferences.router import router as preferences_router
from app.budget.router import router as budget_router
from app.chat.router import router as chat_router
from app.api.admin.router import router as admin_router
from app.site_texts.router import router as site_texts_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Adapter vorab instanziieren — Konfigurationsfehler früh sichtbar
    from app.auth.dependencies import get_auth_adapter
    get_auth_adapter()
    
    # Startup-Check: Wechselkurs prüfen
    from sqlalchemy import select, func
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(func.count()).select_from(ExchangeRate))
        count = result.scalar()
        if not count:
            logger.warning(
                "Kein Wechselkurs in exchange_rates gefunden. "
                "Fallback %.2f wird verwendet. "
                "Initialkurs mit scripts/seed_exchange_rate.py eintragen.",
                settings.exchange_rate_fallback,
            )
    
    yield


app = FastAPI(title="GGD-KI-Plattform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Conversation-Id"],
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(admin_router)
app.include_router(budget_router)
app.include_router(preferences_router)
app.include_router(chat_router)
app.include_router(site_texts_router)
