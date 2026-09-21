#!/usr/bin/env python3
"""
Löscht abgeschlossene Rückmeldungen 180 Tage nach dem Statuswechsel (ADR-020).

Offene Meldungen bleiben stehen; ab 365 Tagen meldet der Lauf sie als Warnung.

Verwendung:
    python scripts/cleanup_feedback.py
    python scripts/cleanup_feedback.py --dry-run
    python scripts/cleanup_feedback.py --now 2027-03-20T02:50:00+00:00
"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Füge backend-Verzeichnis zum Path hinzu (relativ zum Skript-Ort)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.crons.feedback_cleanup_service import cleanup_feedback
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
        lauf = await cleanup_feedback(db, dry_run=dry_run, now=now)
    logger.info(
        "cleanup_feedback done faellig=%d geloescht=%d lange_offen=%d duration_ms=%d",
        lauf.faellig, lauf.geloescht, lauf.lange_offen, lauf.duration_ms,
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Löscht abgeschlossene Rückmeldungen nach 180 Tagen"
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
        logger.exception("cleanup_feedback fehlgeschlagen")
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
