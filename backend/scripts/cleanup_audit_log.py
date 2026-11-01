#!/usr/bin/env python3
"""
Löscht Einträge des Audit-Logs nach Ablauf ihrer Frist (ADR-010 §2.3, 0.28).

auth 180 Tage, admin 2 Jahre, moderation 1 Jahr, system 90 Tage, secret nie.

Verwendung:
    python scripts/cleanup_audit_log.py
    python scripts/cleanup_audit_log.py --dry-run
    python scripts/cleanup_audit_log.py --now 2027-03-20T02:55:00+00:00
"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Füge backend-Verzeichnis zum Path hinzu (relativ zum Skript-Ort)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.crons.audit_cleanup_service import cleanup_audit_log
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


async def run_cleanup(*, dry_run: bool, now: datetime | None) -> int:
    async with AsyncSessionLocal() as db:
        lauf = await cleanup_audit_log(db, dry_run=dry_run, now=now)
    logger.info(
        "cleanup_audit_log done geloescht=%s duration_ms=%d",
        lauf.geloescht, lauf.duration_ms,
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Löscht Audit-Log-Einträge nach Ablauf ihrer Frist"
    )
    parser.add_argument("--dry-run", action="store_true", help="Nur zählen, nichts löschen")
    parser.add_argument(
        "--now",
        type=_parse_now,
        default=None,
        help="Optionaler ISO-Zeitpunkt für reproduzierbare Läufe",
    )
    args = parser.parse_args()

    try:
        exit_code = asyncio.run(run_cleanup(dry_run=args.dry_run, now=args.now))
    except Exception:
        logger.exception("cleanup_audit_log fehlgeschlagen")
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
