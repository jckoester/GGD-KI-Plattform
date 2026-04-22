#!/usr/bin/env python3
"""
Einmaliges CLI-Skript zum Eintragen des Initialkurses in exchange_rates.

Verwendung:
    python scripts/seed_exchange_rate.py --rate 1.08

Trägt einen source='manual'-Eintrag ein. Bricht ab, wenn bereits ein Eintrag vorhanden ist.
"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Füge backend-Verzeichnis zum Path hinzu (relativ zum Skript-Ort)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import ExchangeRate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def check_existing_rate(db: AsyncSession) -> bool:
    """Prüft ob bereits ein Wechselkurs in der DB existiert."""
    result = await db.execute(
        select(ExchangeRate).order_by(ExchangeRate.created_at.desc()).limit(1)
    )
    row = result.fetchone()
    return row is not None


async def seed_exchange_rate(rate: float) -> None:
    """Trägt den Initialkurs in die Datenbank ein."""
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        existing = await check_existing_rate(db)
        if existing:
            logger.error("Abbruch: Es existiert bereits ein Wechselkurs-Eintrag in der Datenbank.")
            logger.error("Bitte löschen Sie ggf. manuell den bestehenden Eintrag, falls Sie ihn überschreiben möchten.")
            await engine.dispose()
            sys.exit(1)

        now = datetime.now(timezone.utc)
        new_rate = ExchangeRate(
            eur_usd_rate=rate,
            source="manual",
            effective_from=now,
            created_at=now,
        )
        db.add(new_rate)
        await db.commit()
        logger.info("Wechselkurs erfolgreich in die Datenbank geschrieben: %.6f EUR/USD (source=manual)", rate)

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Initialkurs in exchange_rates eintragen"
    )
    parser.add_argument(
        "--rate",
        type=float,
        required=True,
        help="EUR/USD Wechselkurs (z.B. 1.08)",
    )
    args = parser.parse_args()
    
    if args.rate <= 0:
        logger.error("Rate muss größer als 0 sein.")
        sys.exit(1)
    
    asyncio.run(seed_exchange_rate(args.rate))


if __name__ == "__main__":
    main()
