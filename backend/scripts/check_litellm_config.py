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
import logging
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

    findings = check_config(model_infos, settings)
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
