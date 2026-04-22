import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.budget.exchange import get_current_rate
from app.budget.tiers import get_budget_for
from app.litellm.client import LiteLLMClient

logger = logging.getLogger(__name__)


async def ensure_litellm_user(
    db: AsyncSession,
    pseudonym: str,
    roles: list[str],
    grade: Optional[int],
) -> None:
    """
    Prüft ob LiteLLM-User existiert und legt ihn ggf. an.
    Fehler werden geloggt, aber nicht nach oben propagiert.
    
    Dies ist eine fire-and-forget Funktion - Login soll nicht scheitern,
    wenn LiteLLM nicht verfügbar ist.
    """
    try:
        # Budget-Ermittlung
        max_budget_eur, budget_duration = get_budget_for(roles, grade)
        
        # Wechselkurs abrufen
        eur_usd = await get_current_rate(db)
        
        # Budget in USD umrechnen
        if max_budget_eur is not None:
            max_budget_usd = round(max_budget_eur * eur_usd, 2)
        else:
            max_budget_usd = None
        
        # LiteLLM-Client instanziieren und User prüfen/erstellen
        client = LiteLLMClient()
        try:
            existing = await client.get_user(pseudonym)
            if existing is None:
                await client.create_user(pseudonym, max_budget_usd, budget_duration)
                logger.info(
                    "LiteLLM-User angelegt pseudonym=%s max_budget_usd=%s budget_duration=%s",
                    pseudonym, max_budget_usd, budget_duration
                )
            # else: User existiert bereits, nichts zu tun
        finally:
            await client.close()
            
    except Exception as e:
        logger.exception(
            "ensure_litellm_user fehlgeschlagen für pseudonym=%s: %s",
            pseudonym, e
        )
        # Exception wird bewusst nicht nach oben propagiert
