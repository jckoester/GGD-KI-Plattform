"""Kalender-Endpunkte (UP-8).

Bisher nur die Kürzel-Liste für die Profileinstellung (Schritt 3).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_any_role
from app.calendar.base import CalendarSourceError
from app.calendar.service import is_configured, list_kuerzel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/teachers")
async def list_teachers(
    _user=Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    """Auswählbare Lehrkraft-Kürzel der konfigurierten Stundenplanquelle.

    Grundlage der Auswahl im Profil: Ein Tippfehler in einem Freitextfeld führte zu einem
    stillen Nicht-Abruf, den niemand mehr zuordnen kann.

    **Kein Fehler, wenn nichts konfiguriert ist** — dann ist `configured` falsch und die
    Oberfläche blendet das Feld aus (Plan §0). Eine Schule ohne WebUntis soll hier keine
    Störungsmeldung sehen.

    Nur für Lehrkräfte: Die Kürzel-Liste ist kollegiumsöffentlich (Plan §2), für
    Schüler:innen aber ohne Zweck.
    """
    if not is_configured():
        return {"configured": False, "teachers": [], "error": None}
    try:
        return {"configured": True, "teachers": await list_kuerzel(), "error": None}
    except CalendarSourceError as exc:
        # Adapter-Meldungen sind bewusst frei von Zugangsdaten (siehe base.py).
        logger.warning("Kürzel-Liste nicht abrufbar: %s", exc)
        return {"configured": True, "teachers": [], "error": str(exc)}
