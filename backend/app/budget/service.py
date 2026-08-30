import logging
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.budget.exchange import get_current_rate
from app.budget.schulwochen import naechste_woche_nach
from app.budget.tiers import get_budget_for, vorsprung_wochen
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
        "max_budget_eur": None,
        "spend_eur": None,
        "remaining_eur": None,
        "wochenbetrag_eur": None,
        "naechste_aufstockung": None,
        "vorsprung_wochen": None,
        "eur_usd_rate": eur_usd,
    }


def _build_response(
    user_info: dict,
    eur_usd: float,
    *,
    wochenbetrag_eur: Optional[float] = None,
    naechste_aufstockung: Optional[str] = None,
    vorsprung: Optional[int] = None,
) -> dict:
    """Baut die Response aus LiteLLM user_info und Wechselkurs.

    `budget_duration` und `budget_reset_at` aus LiteLLM werden **nicht** durchgereicht:
    Seit dem Wochenmodell wird nichts zurückgesetzt, beide Felder sind leer. Sie stehen zu
    lassen hieße, der Oberfläche eine Rücksetzung anzubieten, die es nicht gibt.
    """
    max_budget_usd = user_info.get("max_budget")
    spend_usd = user_info.get("spend")

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
        "max_budget_eur": max_budget_eur,
        "spend_eur": spend_eur,
        "remaining_eur": remaining_eur,
        # Was jede Unterrichtswoche dazukommt, und wann das nächste Mal.
        # `naechste_aufstockung` ist None in den letzten Ferien des Schuljahres —
        # dann kommt tatsächlich nichts mehr dazu.
        "wochenbetrag_eur": wochenbetrag_eur,
        "naechste_aufstockung": naechste_aufstockung,
        # Wie viele Wochenbeträge sich höchstens ansammeln. Gehört in die Antwort, damit
        # die Oberfläche „einige Wochen" nicht raten muss — die Zahl ist konfiguriert.
        "vorsprung_wochen": vorsprung,
        "eur_usd_rate": eur_usd,
    }


def _zuwachs(
    roles: list[str], grade: Optional[int]
) -> tuple[Optional[float], Optional[str], Optional[int]]:
    """Wochenbetrag und Datum der nächsten Aufstockung — beide bestenfalls.

    Fehlt die Schuljahres- oder Budget-Konfiguration, bleibt das Feld leer und die
    Oberfläche lässt den Hinweis weg. Die Budget-Anzeige selbst darf daran nicht scheitern:
    Der verbleibende Betrag ist die wichtigere Auskunft.
    """
    betrag: Optional[float] = None
    naechste: Optional[str] = None
    vorsprung: Optional[int] = None
    try:
        betrag = get_budget_for(roles, grade)
        vorsprung = vorsprung_wochen()
    except Exception:
        logger.warning("Wochenbetrag nicht ermittelbar", exc_info=True)
    try:
        woche = naechste_woche_nach(date.today())
        naechste = woche.montag.isoformat() if woche else None
    except Exception:
        logger.warning("Nächste Unterrichtswoche nicht ermittelbar", exc_info=True)
    return betrag, naechste, vorsprung


async def get_budget_info(
    db: AsyncSession,
    pseudonym: str,
    *,
    roles: Optional[list[str]] = None,
    grade: Optional[int] = None,
) -> dict:
    """
    Laedt Budget-Daten aus LiteLLM und rechnet sie in EUR um.
    Fehler werden nicht propagiert — nur null-Felder oder 503.
    """
    eur_usd = await get_current_rate(db)
    wochenbetrag, naechste, vorsprung = _zuwachs(roles or [], grade)

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
        return _empty_budget(eur_usd) | {
            "wochenbetrag_eur": wochenbetrag,
            "naechste_aufstockung": naechste,
            "vorsprung_wochen": vorsprung,
        }

    return _build_response(
        user_info, eur_usd,
        wochenbetrag_eur=wochenbetrag, naechste_aufstockung=naechste,
        vorsprung=vorsprung,
    )
