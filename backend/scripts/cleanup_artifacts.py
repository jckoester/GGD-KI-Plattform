#!/usr/bin/env python3
"""
Räumt abgelaufene Artefakte der persönlichen Bibliothek (Tabelle `artifacts`): Zeilen mit
`expires_at < now` samt zugehöriger Datei. Die Aufbewahrung wird beim Speichern aus
`config/artifact_limits.yaml` (role-/jahrgangsbasiert) in `expires_at` eingefroren — der Cron
braucht daher keinen Rollen-Lookup, nur den Zeitvergleich.

Verwendung:
    python scripts/cleanup_artifacts.py
    python scripts/cleanup_artifacts.py --dry-run
    python scripts/cleanup_artifacts.py --now 2026-07-08T02:30:00+00:00
"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# backend-Verzeichnis zum Path (relativ zum Skript-Ort)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.artifacts.store import cleanup_artifacts
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
        stats = await cleanup_artifacts(db, dry_run=dry_run, now=now)
    logger.info(
        "cleanup_artifacts done scanned=%d expired_removed=%d dry_run=%s",
        stats.scanned, stats.expired_removed, dry_run,
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Räumt abgelaufene Bibliotheks-Artefakte")
    parser.add_argument("--dry-run", action="store_true", help="Nur zählen, nichts löschen")
    parser.add_argument(
        "--now", type=_parse_now, default=None,
        help="Optionaler ISO-Zeitpunkt für reproduzierbare Läufe",
    )
    args = parser.parse_args()

    try:
        sys.exit(asyncio.run(run_cleanup(dry_run=args.dry_run, now=args.now)))
    except Exception:
        logger.exception("cleanup_artifacts fehlgeschlagen")
        sys.exit(1)


if __name__ == "__main__":
    main()
