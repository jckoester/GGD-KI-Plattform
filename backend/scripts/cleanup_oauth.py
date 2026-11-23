#!/usr/bin/env python3
"""
Räumt den OAuth-Speicher der Schnittstelle für KI-Abos auf (0.55, Päckchen AX):
nie benutzte Registrierungen nach 30 Tagen, abgelaufene Codes und Token, eingelöste
Refresh-Token nach 7 Tagen.

Verwendung:
    python scripts/cleanup_oauth.py
    python scripts/cleanup_oauth.py --dry-run
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import AsyncSessionLocal
from app.mcp.oauth import oauth_aufraeumen

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def run(*, dry_run: bool) -> int:
    async with AsyncSessionLocal() as db:
        aus = await oauth_aufraeumen(db, dry_run=dry_run)
    logger.info("cleanup_oauth %sclients=%d codes=%d token=%d", "[DRY RUN] " if dry_run else "",
                aus["clients"], aus["codes"], aus["token"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="Nur zählen, nichts löschen")
    args = parser.parse_args()
    return asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
