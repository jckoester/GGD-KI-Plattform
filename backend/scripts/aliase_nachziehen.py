#!/usr/bin/env python3
"""
Übernimmt weitere Namen aus dem toten Feld `metadata.aliase` in `node_aliases` (0.13.1).

Seit Migration 0057 (0.9.0) stehen Aliase in einer eigenen Tabelle. Bildungsplan-Import,
Methodik-Seed und `POST/PATCH /context/nodes` schrieben bis 0.13.0 trotzdem in die
Metadaten — dort liest sie weder die Suche noch der Embedding-Input. Einmal nach dem
Update auf 0.13.1 ausführen; ein zweiter Lauf findet nichts mehr.

Verwendung:
    python scripts/aliase_nachziehen.py --dry-run   # nur zählen
    python scripts/aliase_nachziehen.py
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.context.aliase import nachziehen
from app.db.session import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run(*, dry_run: bool) -> None:
    async with AsyncSessionLocal() as db:
        bilanz = await nachziehen(db)
        if dry_run:
            await db.rollback()
        else:
            await db.commit()

    logger.info(
        "Aliase nachgezogen%s: %d Knoten mit Altfeld, %d neue Aliase an %d Knoten, "
        "%d Vektoren verworfen.",
        " (Probelauf, nichts geschrieben)" if dry_run else "",
        bilanz.knoten_mit_altfeld,
        bilanz.neue_aliase,
        bilanz.knoten_mit_neuen_aliasen,
        bilanz.vektoren_verworfen,
    )
    if bilanz.vektoren_verworfen and not dry_run:
        logger.info(
            "Die Vektoren rechnet der nächtliche Backfill neu — sofort: "
            "python scripts/embedding_backfill.py"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="Nur zählen, nichts schreiben")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
