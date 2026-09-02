#!/usr/bin/env python3
"""
Lebenszyklus der Kontextknoten (ADR-013): abgelaufene archivieren, lange archivierte löschen.

Ein Skript, zwei Läufe — sie gehören zusammen und sollen im Protokoll nebeneinander stehen:
Der erste erzeugt die Archiveinträge, deren Frist der zweite Jahre später abrechnet.

Verwendung:
    python scripts/node_lifecycle.py
    python scripts/node_lifecycle.py --dry-run
    python scripts/node_lifecycle.py --nur-archivieren
    python scripts/node_lifecycle.py --nur-loeschen
    python scripts/node_lifecycle.py --now 2029-09-02T02:00:00+00:00

Exit-Code 0 = durchgelaufen (auch wenn nichts zu tun war), 1 = Fehler.
"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.crons.node_lifecycle_service import (
    archiviere_abgelaufene,
    loesche_alte_archivierte,
)
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


async def run(*, dry_run: bool, archivieren: bool, loeschen: bool, jetzt: datetime | None) -> int:
    async with AsyncSessionLocal() as db:
        if archivieren:
            lauf = await archiviere_abgelaufene(
                db, dry_run=dry_run, heute=jetzt.date() if jetzt else None
            )
            logger.info(
                "node_lifecycle archivieren: faellig=%d archiviert=%d dry_run=%s",
                lauf.geprueft, lauf.archiviert, dry_run,
            )

        if loeschen:
            lauf = await loesche_alte_archivierte(db, dry_run=dry_run, jetzt=jetzt)
            logger.info(
                "node_lifecycle loeschen: faellig=%d geloescht=%d "
                "geschuetzt_global=%d geschuetzt_ausgesetzt=%d dry_run=%s",
                lauf.faellig, lauf.geloescht, lauf.geschuetzt_global,
                lauf.geschuetzt_ausgesetzt, dry_run,
            )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Knoten archivieren und alte Archive löschen")
    parser.add_argument("--dry-run", action="store_true", help="Nur zählen, nichts ändern")
    parser.add_argument("--nur-archivieren", action="store_true")
    parser.add_argument("--nur-loeschen", action="store_true")
    parser.add_argument(
        "--now", type=_parse_now, default=None,
        help="Optionaler ISO-Zeitpunkt für reproduzierbare Läufe",
    )
    args = parser.parse_args()

    if args.nur_archivieren and args.nur_loeschen:
        parser.error("--nur-archivieren und --nur-loeschen schließen einander aus")

    archivieren = not args.nur_loeschen
    loeschen = not args.nur_archivieren

    try:
        sys.exit(asyncio.run(run(
            dry_run=args.dry_run, archivieren=archivieren, loeschen=loeschen, jetzt=args.now,
        )))
    except Exception:
        logger.exception("node_lifecycle fehlgeschlagen")
        sys.exit(1)


if __name__ == "__main__":
    main()
