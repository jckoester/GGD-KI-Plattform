import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import ExchangeRate

logger = logging.getLogger(__name__)


def preise_in_euro() -> bool:
    """Stehen die Preise in der LiteLLM-Config bereits in Euro?"""
    return str(getattr(settings, "litellm_price_currency", "USD")).strip().upper() == "EUR"


async def get_current_rate(db: AsyncSession) -> float:
    """
    Umrechnungsfaktor von der Budget-Währung (EUR) in die Einheit der LiteLLM-Preise.

    Stehen die Preise bereits in Euro (``LITELLM_PRICE_CURRENCY=EUR``), ist der Faktor
    **1,0** — es wird nicht gerechnet, und damit gibt es an dieser Stelle **kein
    Kursrisiko**. Das ist kein Sonderfall, sondern der Regelfall bei Anbietern, die in
    Euro abrechnen.

    Sonst: der neueste gültige EUR/USD-Kurs, Fallback ``settings.exchange_rate_fallback``.
    """
    if preise_in_euro():
        # Bewusst ohne DB-Zugriff und ohne Log auf INFO: Das ist der Normalbetrieb einer
        # Euro-Schule und soll nicht bei jedem Aufruf Rauschen erzeugen.
        return 1.0

    try:
        now = datetime.now(timezone.utc)
        stmt = (
            select(ExchangeRate.eur_usd_rate)
            .where(ExchangeRate.effective_from <= now)
            .order_by(ExchangeRate.effective_from.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        row = result.fetchone()
        
        if row and row[0] is not None:
            return float(row[0])
    except Exception as e:
        logger.error("Fehler beim Abrufen des Wechselkurses: %s", e)
    
    # Fallback
    fallback_rate = getattr(settings, "exchange_rate_fallback", 1.10)
    logger.info("Verwende Fallback-Wechselkurs: %.2f", fallback_rate)
    return float(fallback_rate)
