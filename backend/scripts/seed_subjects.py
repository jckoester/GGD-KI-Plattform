#!/usr/bin/env python3
"""
Fächer aus config/subjects.yaml in die Datenbank einspielen (Upsert).

Verwendung (aus backend/):
    python scripts/seed_subjects.py [--yaml /pfad/zur/subjects.yaml]

Standardpfad: config/subjects.yaml (relativ zum Repo-Root, eine Ebene über backend/)
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Subject

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_YAML = Path(__file__).resolve().parent.parent.parent / "config" / "subjects.yaml"


async def seed(yaml_path: Path) -> None:
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    subjects = data.get("subjects", [])
    if not subjects:
        logger.error("Keine Fächer in %s gefunden.", yaml_path)
        sys.exit(1)

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    inserted = updated = 0
    async with session_factory() as db:
        for entry in subjects:
            slug = entry["slug"].lower()
            result = await db.execute(
                select(Subject).where(Subject.slug == slug)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.name = entry["name"]
                existing.icon = entry.get("icon")
                existing.color = entry.get("color")
                existing.min_grade = entry.get("min_grade")
                existing.max_grade = entry.get("max_grade")
                existing.sort_order = entry.get("sort_order", 0)
                updated += 1
            else:
                db.add(
                    Subject(
                        slug=slug,
                        name=entry["name"],
                        icon=entry.get("icon"),
                        color=entry.get("color"),
                        min_grade=entry.get("min_grade"),
                        max_grade=entry.get("max_grade"),
                        sort_order=entry.get("sort_order", 0),
                    )
                )
                inserted += 1

        await db.commit()

    await engine.dispose()
    logger.info("Seed abgeschlossen: %d eingefügt, %d aktualisiert.", inserted, updated)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fächer-Seed aus YAML")
    parser.add_argument(
        "--yaml",
        type=Path,
        default=DEFAULT_YAML,
        help=f"Pfad zur subjects.yaml (Standard: {DEFAULT_YAML})",
    )
    args = parser.parse_args()

    if not args.yaml.exists():
        logger.error("YAML-Datei nicht gefunden: %s", args.yaml)
        sys.exit(1)

    asyncio.run(seed(args.yaml))


if __name__ == "__main__":
    main()
