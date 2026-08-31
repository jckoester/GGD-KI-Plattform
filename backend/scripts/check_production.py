#!/usr/bin/env python3
"""
Prüft die Betriebswerte gegen die Anforderungen des Sicherheits-Audits.

Der Audit ist im Code abgearbeitet; offen bleiben Werte, die nur auf der Produktion
gesetzt werden können — und mehrere davon fallen **still** aus: `ALLOWED_HOSTS` auf `*`
heißt Host-Schutz aus, ein unpassendes `TRUSTED_PROXIES` heißt falsche IP im Audit-Log.
Diese Prüfung macht daraus eine Ausgabe.

Rein lokal: kein Netz, keine Datenbank, kein laufender Proxy. Läuft damit auch vor dem
ersten Start.

Verwendung:
    cd backend && python scripts/check_production.py
    docker compose exec backend python scripts/check_production.py

Exit-Code 0 = keine Fehler (Warnungen möglich), 1 = mindestens ein Fehler.

Die Modell- und Preisseite prüft `check_litellm_config.py` — beides zusammen ist die
Inbetriebnahme-Prüfung.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.core.production_check import (
    ERROR,
    INFO,
    NICHT_PRUEFBAR,
    WARNING,
    pruefe_produktion,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_MARK = {ERROR: "FEHLER ", WARNING: "WARNUNG", INFO: "INFO   "}


def _auth_config():
    """auth.yaml laden — fehlt sie, ist das selbst ein Befund, kein Absturz."""
    try:
        from app.auth.config import load_auth_config

        return load_auth_config(settings.auth_config_path)
    except Exception as exc:  # noqa: BLE001 — jede Ursache ist hier gleich zu behandeln
        logger.info("WARNUNG  auth.yaml nicht lesbar (%s) — Auth-Prüfungen entfallen.", exc)
        return None


def _schuljahr():
    try:
        from app.planning.calendar import load_school_year

        return load_school_year()
    except Exception as exc:  # noqa: BLE001
        logger.info("WARNUNG  school_year.yaml nicht lesbar (%s) — Prüfung entfällt.", exc)
        return None


def main() -> None:
    logger.info("Betriebsprüfung — ENVIRONMENT=%s\n", settings.environment)

    befunde = pruefe_produktion(settings, _auth_config(), _schuljahr())

    for level in (ERROR, WARNING, INFO):
        for befund in [b for b in befunde if b.level == level]:
            logger.info("%s  %s\n", _MARK[level], befund.message)

    fehler = sum(1 for b in befunde if b.level == ERROR)
    warnungen = sum(1 for b in befunde if b.level == WARNING)

    logger.info("Nicht prüfbar und deshalb von Hand zu bestätigen:")
    for satz in NICHT_PRUEFBAR:
        logger.info("  · %s", satz)
    logger.info("")

    if fehler:
        logger.error("%d Fehler, %d Warnung(en) — noch nicht betriebsbereit.", fehler, warnungen)
        sys.exit(1)
    if warnungen:
        logger.info("Keine Fehler, %d Warnung(en) — bitte einzeln bewerten.", warnungen)
    else:
        logger.info("Alle prüfbaren Betriebswerte gesetzt.")


if __name__ == "__main__":
    main()
