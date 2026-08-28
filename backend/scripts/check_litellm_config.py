#!/usr/bin/env python3
"""
Prüft die LiteLLM-Konfiguration gegen die Anforderungen der Plattform.

Fragt den laufenden Proxy (`GET /model/info`) ab und gleicht ihn mit der `.env` ab. Meldet
genau die Dinge, die sonst **still** brechen: fehlende Preise (Spend = 0 → Budgets wirkungslos),
fehlendes `supports_function_calling` (Werkzeuge fallen aus), falsche/fehlende `mode`-Angaben,
und Modellnamen in der `.env`, die der Proxy gar nicht kennt.

Gedacht als letzter Schritt vor der Inbetriebnahme eines neuen Anbieters — und nach jeder
Änderung an der `model_list`.

Verwendung:
    cd backend && python scripts/check_litellm_config.py

Exit-Code 0 = keine Fehler (Warnungen möglich), 1 = mindestens ein Fehler.
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.config import settings
from app.litellm.config_check import ERROR, INFO, WARNING, check_config

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_MARK = {ERROR: "FEHLER ", WARNING: "WARNUNG", INFO: "INFO   "}


async def _fetch_model_infos() -> list[dict]:
    url = f"{settings.litellm_proxy_url.rstrip('/')}/model/info"
    async with httpx.AsyncClient(timeout=30.0, verify=settings.litellm_verify_ssl) as client:
        response = await client.get(
            url, headers={"Authorization": f"Bearer {settings.litellm_master_key}"}
        )
        response.raise_for_status()
        return response.json().get("data", [])


def _aus_env_datei(name: str) -> str | None:
    """Liest einen Wert aus der `.env` im Repo-Wurzelverzeichnis.

    `IMAGE_PRICES` ist bewusst **kein** Feld in `settings`: Die Variable liest im Betrieb
    der Proxy, nicht das Backend. Ein Settings-Feld würde eine Zuständigkeit vortäuschen,
    die es nicht gibt — hier wird sie nur zum Prüfen gesucht, wo sie zufällig liegt.
    """
    pfad = Path(__file__).resolve().parents[2] / ".env"
    if not pfad.is_file():
        return None
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        schluessel, _, wert = zeile.partition("=")
        if schluessel.strip() == name:
            return wert.strip().strip("'\"") or None
    return None


def _image_prices() -> dict | None:
    """`IMAGE_PRICES` aus Umgebung oder `.env`, oder None (nicht vorhanden/unbrauchbar).

    None heißt **nicht prüfbar**, nicht „keine Preise": Läuft der Proxy auf einem anderen
    Host, fehlt die Variable hier zu Recht. Das wird gemeldet statt als Fehler gewertet.
    """
    roh = os.environ.get("IMAGE_PRICES") or _aus_env_datei("IMAGE_PRICES")
    if not roh:
        return None
    try:
        werte = json.loads(roh)
    except json.JSONDecodeError as exc:
        logger.warning("IMAGE_PRICES ist kein gültiges JSON (%s) — Prüfung übersprungen.", exc)
        return None
    if not isinstance(werte, dict):
        logger.warning("IMAGE_PRICES ist kein Objekt — Prüfung übersprungen.")
        return None
    return werte


def _bildarten() -> list:
    """Konfigurierte Bildarten; bei fehlerhafter Datei bricht der Lauf mit Klartext ab."""
    from app.chat.image_models import alle_bildarten

    try:
        return alle_bildarten()
    except Exception as exc:
        logger.error("Bildarten nicht ladbar: %s", exc)
        sys.exit(1)


def main() -> None:
    logger.info("Proxy: %s", settings.litellm_proxy_url)
    try:
        model_infos = asyncio.run(_fetch_model_infos())
    except Exception as exc:
        logger.error(
            "LiteLLM nicht erreichbar (%s): %s\n"
            "LITELLM_PROXY_URL und LITELLM_MASTER_KEY prüfen.",
            type(exc).__name__, exc,
        )
        sys.exit(1)

    findings = check_config(
        model_infos, settings, bildarten=_bildarten(), image_prices=_image_prices()
    )
    logger.info("%d Modell(e) gemeldet\n", len(model_infos))

    for level in (ERROR, WARNING, INFO):
        for finding in [f for f in findings if f.level == level]:
            logger.info("%s  %s", _MARK[level], finding.message)

    errors = sum(1 for f in findings if f.level == ERROR)
    warnings = sum(1 for f in findings if f.level == WARNING)
    logger.info("")
    if errors:
        logger.error("%d Fehler, %d Warnung(en) — Konfiguration unvollständig.", errors, warnings)
        sys.exit(1)
    if warnings:
        logger.info("Keine Fehler, %d Warnung(en).", warnings)
    else:
        logger.info("Konfiguration vollständig (soweit ohne Live-Aufruf prüfbar).")
        logger.info(
            "Offen bleibt der Praxistest: eine Chat-Antwort erzeugen und prüfen, dass die "
            "SpendLog-Zeile einen Betrag > 0 trägt."
        )


if __name__ == "__main__":
    main()
