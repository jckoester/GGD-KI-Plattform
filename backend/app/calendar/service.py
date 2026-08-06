"""Zugang zur konfigurierten Stundenplanquelle (UP-8).

Die Zugangsdaten stehen in der Umgebung (`WEBUNTIS_*`), nicht in der Datenbank — es ist
**ein** schulweites Dienstkonto, einmal gesetzt und selten geändert, also dieselbe
Behandlung wie `SCHOOL_SECRET` oder `LITELLM_MASTER_KEY`.

> Der frühere Entwurf sah eine Tabelle `calendar_sources` mit verschlüsselter
> Konfiguration vor. Der stammte aus der ICS-Variante, in der **jede Lehrkraft** eine
> eigene Abo-URL gehabt hätte — 75 Geheimnisse lassen sich nicht in der Umgebung
> verwalten, eines schon. Mit dem Servicekonto entfiel die Voraussetzung; Tabelle,
> Verschlüsselung und Verwaltungsoberfläche entfielen mit ihr.
"""
from __future__ import annotations

import logging

from app.calendar.base import CalendarAdapter, CalendarSourceError
from app.calendar.webuntis import WebUntisAdapter
from app.config import settings

logger = logging.getLogger(__name__)

# Schlüssel in `user_preferences.preferences`. Als Konstante, damit der strukturelle Test
# (UP-8 Schritt 3) dieselbe Zeichenkette prüft wie der Produktivcode.
KUERZEL_PREFERENCE_KEY = "webuntis_kuerzel"


class NoCalendarSourceError(CalendarSourceError):
    """Keine Stundenplanquelle konfiguriert.

    Eigener Typ, weil das der **Normalfall** einer Schule ohne WebUntis ist und kein
    Fehler: Die Oberfläche blendet die zugehörigen Bedienelemente aus, statt eine
    Störungsmeldung zu zeigen (Plan §0).
    """


def is_configured() -> bool:
    """Ob eine Stundenplanquelle eingerichtet ist.

    Der Servername ist das Merkmal: Ohne ihn gibt es nichts abzurufen. Benutzername und
    Passwort werden erst beim Verbinden geprüft — hier zu prüfen hieße, eine halb
    ausgefüllte Konfiguration als „nicht vorhanden" zu behandeln, was den Fehler
    verstecken statt melden würde.
    """
    return bool(settings.webuntis_server.strip())


def get_adapter() -> CalendarAdapter:
    """Einsatzbereiter Adapter für die konfigurierte Quelle."""
    if not is_configured():
        raise NoCalendarSourceError(
            "Es ist keine Stundenplanquelle eingerichtet (WEBUNTIS_SERVER)."
        )
    return WebUntisAdapter(
        server=settings.webuntis_server,
        user=settings.webuntis_user,
        password=settings.webuntis_password,
        school=settings.webuntis_school,
    )


async def list_kuerzel() -> list[str]:
    """Auswählbare Lehrkraft-Kürzel der konfigurierten Quelle."""
    adapter = get_adapter()
    async with adapter:  # type: ignore[attr-defined]
        mapping = await adapter.element_ids()  # type: ignore[attr-defined]
    return sorted(mapping)


async def validate_kuerzel(value: object) -> str:
    """Ein eingetragenes Kürzel prüfen. Gibt die normalisierte Form zurück.

    **Leeren ist immer erlaubt** — die Abschaltung darf nie daran scheitern, dass die
    Quelle gerade nicht erreichbar ist. Wer die Stundenplan-Übernahme beenden will, soll
    das jederzeit können.

    **Setzen wird gegen die Liste geprüft** und schlägt fehl, wenn sie nicht abrufbar ist.
    Das ist bewusst streng: Ein nicht existierendes Kürzel führte sonst zu einem stillen
    Nicht-Abruf, den später niemand mehr zuordnet. Die Oberfläche lädt die Liste ohnehin,
    um die Auswahl anzuzeigen — ist sie erreichbar, stört die Prüfung nicht.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return ""
    if not isinstance(value, str):
        raise ValueError("Das Kürzel muss Text sein.")

    normalized = value.strip().upper()
    if normalized not in await list_kuerzel():
        raise ValueError(
            f"'{value.strip()}' steht nicht in der Kürzel-Liste des Stundenplans."
        )
    return normalized
