import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.budget.exchange import get_current_rate
from app.litellm.client import LiteLLMClient

logger = logging.getLogger(__name__)


def _usd_to_eur(usd: Optional[float], rate: float) -> Optional[float]:
    """Rechnet USD in EUR um, rundet auf 2 Dezimalstellen."""
    if usd is None:
        return None
    return round(usd / rate, 2)


def _empty_budget(eur_usd: float) -> dict:
    """Gibt ein Budget-Response mit null-Werten zurueck."""
    return {
        "max_budget_usd": None,
        "spend_usd": None,
        "remaining_usd": None,
        "budget_duration": None,
        "budget_reset_at": None,
        "max_budget_eur": None,
        "spend_eur": None,
        "remaining_eur": None,
        "eur_usd_rate": eur_usd,
    }


def _build_response(user_info: dict, eur_usd: float) -> dict:
    """Baut die Response aus LiteLLM user_info und Wechselkurs."""
    max_budget_usd = user_info.get("max_budget")
    spend_usd = user_info.get("spend")
    budget_duration = user_info.get("budget_duration")
    budget_reset_at = user_info.get("budget_reset_at")

    # remaining_usd berechnen
    if max_budget_usd is not None and spend_usd is not None:
        remaining_usd = max_budget_usd - spend_usd
    else:
        remaining_usd = None

    # EUR-Werte berechnen
    max_budget_eur = _usd_to_eur(max_budget_usd, eur_usd)
    spend_eur = _usd_to_eur(spend_usd, eur_usd)
    remaining_eur = _usd_to_eur(remaining_usd, eur_usd)

    return {
        "max_budget_usd": max_budget_usd,
        "spend_usd": spend_usd,
        "remaining_usd": remaining_usd,
        "budget_duration": budget_duration,
        "budget_reset_at": budget_reset_at,
        "max_budget_eur": max_budget_eur,
        "spend_eur": spend_eur,
        "remaining_eur": remaining_eur,
        "eur_usd_rate": eur_usd,
    }


async def get_budget_info(db: AsyncSession, pseudonym: str) -> dict:
    """
    Laedt Budget-Daten aus LiteLLM und rechnet sie in EUR um.
    Fehler werden nicht propagiert — nur null-Felder oder 503.
    """
    eur_usd = await get_current_rate(db)

    client = LiteLLMClient()
    try:
        user_info = await client.get_user(pseudonym)
    except Exception as e:
        logger.warning("LiteLLM nicht erreichbar fuer pseudonym=%s: %s", pseudonym, e)
        raise HTTPException(
            status_code=503, detail="Budget-Daten voruebergehend nicht verfuegbar"
        )
    finally:
        await client.close()

    if user_info is None:
        return _empty_budget(eur_usd)

    return _build_response(user_info, eur_usd)
