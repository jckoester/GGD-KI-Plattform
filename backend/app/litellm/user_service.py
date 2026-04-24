import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.auth.audit import get_primary_role
from app.budget.exchange import get_current_rate
from app.budget.tiers import get_budget_for
from app.db.models import PseudonymAudit
from app.litellm.client import LiteLLMClient
from app.litellm.team_service import reconcile_user_team
from app.litellm.teams import get_target_team_id

logger = logging.getLogger(__name__)


def _extract_current_team_ids(user_info: dict | None) -> set[str]:
    """
    Extrahiert Team-IDs/Aliases robust aus LiteLLM user/info Antworten.
    """
    if not isinstance(user_info, dict):
        return set()

    team_ids: set[str] = set()

    def _add(value: object) -> None:
        if isinstance(value, str) and value:
            team_ids.add(value)
        elif isinstance(value, dict):
            for key in ("team_id", "team_alias", "alias", "id"):
                v = value.get(key)
                if isinstance(v, str) and v:
                    team_ids.add(v)

    for key in ("teams", "team_ids"):
        raw = user_info.get(key)
        if isinstance(raw, list):
            for item in raw:
                _add(item)

    for key in ("team_id", "team_alias"):
        _add(user_info.get(key))

    team_obj = user_info.get("team")
    _add(team_obj)

    return team_ids


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
            
            # Virtual Key generieren falls noch nicht vorhanden
            key_result = await db.execute(
                select(PseudonymAudit.litellm_key).where(PseudonymAudit.pseudonym == pseudonym)
            )
            litellm_key = await key_result.scalar_one_or_none()
            
            if litellm_key is None:
                # Key generieren und speichern
                key = await client.generate_key(pseudonym)
                await db.execute(
                    update(PseudonymAudit)
                    .where(PseudonymAudit.pseudonym == pseudonym)
                    .values(litellm_key=key)
                )
                await db.commit()
                logger.info("LiteLLM-Virtual-Key generiert und gespeichert pseudonym=%s", pseudonym)
        finally:
            await client.close()
            
    except Exception as e:
        logger.exception(
            "ensure_litellm_user fehlgeschlagen für pseudonym=%s: %s",
            pseudonym, e
        )
        # Exception wird bewusst nicht nach oben propagiert


async def ensure_litellm_team_membership(
    pseudonym: str,
    roles: list[str],
    grade: int | str | None,
) -> None:
    """
    Stellt sicher, dass der User in LiteLLM genau im richtigen Phase-1-Team ist.
    Fire-and-forget: Fehler werden geloggt, Login wird nicht blockiert.
    """
    try:
        # Zielteam bestimmen
        grade_int = None
        if grade is not None:
            try:
                grade_int = int(grade)
            except (TypeError, ValueError):
                grade_int = None

        try:
            target_team_id = get_target_team_id(roles, grade_int)
        except ValueError as e:
            logger.warning(
                "Kein Zielteam ableitbar pseudonym=%s roles=%s grade=%s error=%s",
                pseudonym,
                roles,
                grade_int,
                e,
            )
            return

        # LiteLLM-Client instanziieren
        client = LiteLLMClient()
        try:
            # Aktuellen User-Zustand abrufen
            user_info = await client.get_user(pseudonym)

            # Aktuelle Team-IDs extrahieren
            current_team_ids = _extract_current_team_ids(user_info)

            # Reconcile aufrufen
            result = await reconcile_user_team(
                client=client,
                pseudonym=pseudonym,
                target_team_id=target_team_id,
                current_team_ids=current_team_ids,
            )

            # Ergebnis loggen
            if not result.get("unchanged", False):
                logger.info(
                    "LiteLLM Team-Membership synchronisiert pseudonym=%s target=%s added=%s removed=%s",
                    pseudonym,
                    target_team_id,
                    result.get("added", []),
                    result.get("removed", []),
                )
        finally:
            await client.close()

    except Exception as e:
        logger.exception(
            "ensure_litellm_team_membership fehlgeschlagen für pseudonym=%s: %s",
            pseudonym, e
        )
        # Exception wird bewusst nicht nach oben propagiert
