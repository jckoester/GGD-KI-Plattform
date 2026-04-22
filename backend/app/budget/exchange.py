import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import ExchangeRate

logger = logging.getLogger(__name__)


async def get_current_rate(db: AsyncSession) -> float:
    """
    Gibt den neuesten gültigen EUR/USD-Kurs zurück.
    Fallback auf settings.exchange_rate_fallback (Default: 1.10) wenn kein Eintrag vorhanden.
    """
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
