#!/usr/bin/env python3
"""
Löscht inaktive Accounts (90 Tage ohne Login).

Verwendung:
    python scripts/cleanup_inactive_accounts.py
    python scripts/cleanup_inactive_accounts.py --dry-run --limit 1000
    python scripts/cleanup_inactive_accounts.py --now 2026-04-22T02:00:00+00:00
"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Füge backend-Verzeichnis zum Path hinzu (relativ zum Skript-Ort)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.crons.cleanup_service import cleanup_inactive_accounts
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


async def run_cleanup(
    *,
    limit: int,
    dry_run: bool,
    now: datetime | None,
) -> int:
    async with AsyncSessionLocal() as db:
        stats = await cleanup_inactive_accounts(
            db,
            limit=limit,
            dry_run=dry_run,
            now=now,
        )
    logger.info(
        "cleanup_inactive_accounts done found=%d deleted_local=%d litellm_ok=%d litellm_failed=%d "
        "key_delete_ok=%d key_delete_failed=%d errors=%d duration_ms=%d",
        stats.found,
        stats.deleted_local,
        stats.litellm_delete_ok,
        stats.litellm_delete_failed,
        stats.litellm_key_delete_ok,
        stats.litellm_key_delete_failed,
        stats.errors,
        stats.duration_ms,
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Löscht inaktive Accounts (90 Tage ohne Login)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur zählen, nichts löschen",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximale Batch-Größe (Default: 500)",
    )
    parser.add_argument(
        "--now",
        type=_parse_now,
        default=None,
        help="Optionaler ISO-Zeitpunkt für reproduzierbare Läufe",
    )
    args = parser.parse_args()

    if args.limit < 1:
        logger.error("--limit muss >= 1 sein")
        sys.exit(1)

    try:
        exit_code = asyncio.run(
            run_cleanup(limit=args.limit, dry_run=args.dry_run, now=args.now)
        )
    except Exception:
        logger.exception("cleanup_inactive_accounts fehlgeschlagen")
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
