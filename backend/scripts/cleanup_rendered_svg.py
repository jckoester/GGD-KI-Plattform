#!/usr/bin/env python3
"""
Räumt den SVG-Render-Cache (Tabelle `rendered_svg`): Einträge älter als
settings.render_cache_max_age_days. Der Cache ist eine reine Funktion Eingabe→SVG
(deterministisch, content-adressiert) und wird darum nur altersbasiert begrenzt.

Verwendung:
    python scripts/cleanup_rendered_svg.py
    python scripts/cleanup_rendered_svg.py --max-age-days 90
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

# backend-Verzeichnis zum Path (relativ zum Skript-Ort)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.render.cache import cleanup_rendered_svg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_cleanup(max_age_days: int) -> int:
    async with AsyncSessionLocal() as db:
        deleted = await cleanup_rendered_svg(db, max_age_days)
    logger.info("cleanup_rendered_svg done deleted=%d (max_age_days=%d)", deleted, max_age_days)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Räumt über-alte Einträge aus dem SVG-Render-Cache")
    parser.add_argument(
        "--max-age-days", type=int, default=None,
        help="Aufbewahrung überschreiben (Default: settings.render_cache_max_age_days)",
    )
    args = parser.parse_args()

    max_age = args.max_age_days if args.max_age_days is not None else settings.render_cache_max_age_days
    if max_age < 1:
        logger.error("--max-age-days muss >= 1 sein")
        sys.exit(1)

    try:
        sys.exit(asyncio.run(run_cleanup(max_age)))
    except Exception:
        logger.exception("cleanup_rendered_svg fehlgeschlagen")
        sys.exit(1)


if __name__ == "__main__":
    main()
