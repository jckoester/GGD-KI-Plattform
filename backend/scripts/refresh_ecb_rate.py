#!/usr/bin/env python3
"""
Holt den aktuellen EUR/USD-Kurs von der EZB und speichert ihn in der DB.

Verwendung:
    python scripts/refresh_ecb_rate.py
    python scripts/refresh_ecb_rate.py --dry-run
    python scripts/refresh_ecb_rate.py --force
"""
import argparse
import asyncio
import logging
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Füge backend-Verzeichnis zum Path hinzu (relativ zum Skript-Ort)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import ExchangeRate
from app.db.session import AsyncSessionLocal
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
ECB_NS = "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"


async def fetch_ecb_rate() -> float:
    """Holt den aktuellen EUR/USD-Wechselkurs von der EZB."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(ECB_URL)
            resp.raise_for_status()
        except httpx.TimeoutException as e:
            logger.error("EZB-Feed: Timeout beim Abrufen: %s", e)
            raise
        except httpx.HTTPStatusError as e:
            logger.error("EZB-Feed: HTTP-Fehler %d: %s", e.response.status_code, e)
            raise
        except httpx.RequestError as e:
            logger.error("EZB-Feed: Anfrage-Fehler: %s", e)
            raise

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        logger.error("EZB-Feed: XML-Parse-Fehler: %s", e)
        raise ValueError("Konnte EZB-XML nicht parsen") from e

    for cube in root.iter(f"{{{ECB_NS}}}Cube"):
        if cube.get("currency") == "USD":
            rate_str = cube.get("rate")
            if rate_str is None:
                raise ValueError("USD-Kurs nicht im EZB-Feed gefunden")
            try:
                return float(rate_str)
            except ValueError as e:
                raise ValueError(f"USD-Kurs ist keine gültige Zahl: {rate_str}") from e

    raise ValueError("USD-Kurs nicht im EZB-Feed gefunden")


async def run(*, dry_run: bool, force: bool) -> None:
    """Hauptlogik: Kurs abrufen und ggf. in DB speichern."""
    rate = await fetch_ecb_rate()
    logger.info("EZB EUR/USD Kurs: %.6f", rate)

    if dry_run:
        logger.info("--dry-run: Keine DB-Änderungen")
        return

    async with AsyncSessionLocal() as db:
        if not force:
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            existing = await db.execute(
                select(ExchangeRate)
                .where(ExchangeRate.source == "ECB")
                .where(ExchangeRate.created_at >= today_start)
            )
            if existing.fetchone():
                logger.info(
                    "Heute bereits ECB-Eintrag vorhanden, überspringe (--force zum Überschreiben)"
                )
                return

        now = datetime.now(timezone.utc)
        db.add(
            ExchangeRate(
                eur_usd_rate=rate,
                source="ECB",
                effective_from=now,
                created_at=now,
            )
        )
        await db.commit()

    logger.info("EZB-Kurs %.6f in exchange_rates geschrieben", rate)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Holt den aktuellen EUR/USD-Kurs von der EZB"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Rate abrufen und loggen, aber nicht in DB schreiben",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Auch dann eintragen, wenn heute bereits ein ECB-Eintrag vorhanden ist",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run(dry_run=args.dry_run, force=args.force))
    except Exception:
        logger.exception("refresh_ecb_rate fehlgeschlagen")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
