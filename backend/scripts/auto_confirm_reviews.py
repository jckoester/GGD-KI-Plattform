#!/usr/bin/env python3
"""
Bestätigt vergangene Unterrichtsstunden automatisch, wenn eine spätere
Stunde derselben Gruppe bereits gehalten wurde (dynamische Frist).

Verwendung:
    python scripts/auto_confirm_reviews.py
    python scripts/auto_confirm_reviews.py --dry-run
    python scripts/auto_confirm_reviews.py --today 2026-09-20
"""
import argparse
import asyncio
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.crons.lesson_review_service import auto_confirm_reviews
from app.db.session import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_date(raw: str | None) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Ungültiges ISO-Datum für --today: {raw}") from exc


async def run(*, dry_run: bool, today: date | None) -> int:
    async with AsyncSessionLocal() as db:
        stats = await auto_confirm_reviews(db, today=today, dry_run=dry_run)
    logger.info(
        "auto_confirm_reviews done candidates=%d confirmed=%d skipped=%d errors=%d duration_ms=%d",
        stats.candidates,
        stats.confirmed,
        stats.skipped,
        stats.errors,
        stats.duration_ms,
    )
    return 1 if stats.errors > 0 else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-Bestätigung vergangener Unterrichtsstunden"
    )
    parser.add_argument("--dry-run", action="store_true", help="Nur zählen, nichts schreiben")
    parser.add_argument("--today", type=_parse_date, default=None,
                        help="Optionaler ISO-Referenztag (default: heute)")
    args = parser.parse_args()

    try:
        exit_code = asyncio.run(run(dry_run=args.dry_run, today=args.today))
    except Exception:
        logger.exception("auto_confirm_reviews fehlgeschlagen")
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
