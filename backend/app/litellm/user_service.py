import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.audit import get_primary_role
from app.budget.exchange import get_current_rate
from app.budget.tiers import get_budget_for
from app.litellm.client import LiteLLMClient

logger = logging.getLogger(__name__)


async def ensure_litellm_user(
    db: AsyncSession,
    pseudonym: str,
    roles: list[str],
    grade: Optional[int | str],
    old_role: str | None = None,
    old_grade: int | None = None,
) -> None:
    """
    Prüft ob LiteLLM-User existiert und legt ihn ggf. an.
    Fehler werden geloggt, aber nicht nach oben propagiert.
    
    Dies ist eine fire-and-forget Funktion - Login soll nicht scheitern,
    wenn LiteLLM nicht verfügbar ist.
    """
    try:
        grade_int: int | None
        if grade is None:
            grade_int = None
        else:
            try:
                grade_int = int(grade)
            except (TypeError, ValueError):
                grade_int = None

        new_primary_role = get_primary_role(roles)

        # Budget-Ermittlung
        max_budget_eur, budget_duration = get_budget_for(roles, grade_int)
        
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
            else:
                grade_changed = old_grade != grade_int
                role_changed = old_role is not None and old_role != new_primary_role
                if grade_changed or role_changed:
                    await client.update_user_budget(
                        pseudonym, max_budget_usd, budget_duration
                    )
                    logger.info(
                        "LiteLLM-Budget aktualisiert pseudonym=%s old_role=%s new_role=%s "
                        "old_grade=%s new_grade=%s max_budget_usd=%s",
                        pseudonym,
                        old_role,
                        new_primary_role,
                        old_grade,
                        grade_int,
                        max_budget_usd,
                    )
        finally:
            await client.close()
            
    except Exception as e:
        logger.exception(
            "ensure_litellm_user fehlgeschlagen für pseudonym=%s: %s",
            pseudonym, e
        )
        # Exception wird bewusst nicht nach oben propagiert
