#!/usr/bin/env python3
"""
Räumt generierte Bilddateien: verwaiste (keine DB-Zeile mehr) und über der harten
Maximal-Aufbewahrung (settings.image_max_retention_days). Backstop zum
Konversations-Lifecycle (Bilder sterben normal mit ihrer Konversation).

Verwendung:
    python scripts/cleanup_generated_images.py
    python scripts/cleanup_generated_images.py --dry-run
    python scripts/cleanup_generated_images.py --max-age-days 400
    python scripts/cleanup_generated_images.py --now 2026-04-22T02:30:00+00:00
"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Füge backend-Verzeichnis zum Path hinzu (relativ zum Skript-Ort)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chat.image_store import cleanup_generated_images
from app.db.session import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_now(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Ungültiges ISO-Datum für --now: {raw}") from exc


async def run_cleanup(*, dry_run: bool, max_age_days: int | None, now: datetime | None) -> int:
    async with AsyncSessionLocal() as db:
        stats = await cleanup_generated_images(
            db, dry_run=dry_run, max_age_days=max_age_days, now=now,
        )
    logger.info(
        "cleanup_generated_images done scanned=%d orphans=%d aged=%d kept=%d",
        stats.scanned, stats.orphans_removed, stats.aged_removed, stats.kept,
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Räumt verwaiste + über-alte generierte Bilddateien"
    )
    parser.add_argument("--dry-run", action="store_true", help="Nur zählen, nichts löschen")
    parser.add_argument(
        "--max-age-days", type=int, default=None,
        help="Harte Maximal-Aufbewahrung überschreiben (Default: settings.image_max_retention_days)",
    )
    parser.add_argument(
        "--now", type=_parse_now, default=None,
        help="Optionaler ISO-Zeitpunkt für reproduzierbare Läufe",
    )
    args = parser.parse_args()

    if args.max_age_days is not None and args.max_age_days < 1:
        logger.error("--max-age-days muss >= 1 sein")
        sys.exit(1)

    try:
        exit_code = asyncio.run(
            run_cleanup(dry_run=args.dry_run, max_age_days=args.max_age_days, now=args.now)
        )
    except Exception:
        logger.exception("cleanup_generated_images fehlgeschlagen")
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
