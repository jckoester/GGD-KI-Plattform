#!/usr/bin/env python3
"""
Grundvokabular für Methoden und Sozialformen in den Wissensgraph einspielen (Upsert).

Schulweit (read_scope=school), fach­unabhängig. Fachspezifisches legen Lehrkräfte
selbst an (privat → Fachschaft). Idempotent über (content_type, title): bei erneutem
Lauf werden nur die Aliase aktualisiert.

Verwendung (aus backend/):
    python scripts/seed_methodik.py
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import ContextNode

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# (Titel, [Aliase]) — kanonischer Titel zuerst.
SOZIALFORMEN: list[tuple[str, list[str]]] = [
    ("Plenum", ["Frontalunterricht", "Unterrichtsgespräch", "Lehrgespräch"]),
    ("Einzelarbeit", ["Stillarbeit"]),
    ("Partnerarbeit", []),
    ("Gruppenarbeit", ["Teamarbeit"]),
]

METHODEN: list[tuple[str, list[str]]] = [
    ("Think-Pair-Share", ["Ich-Du-Wir", "Prinzip der wachsenden Gruppe"]),
    ("Placemat", []),
    ("Gruppenpuzzle", ["Jigsaw", "Expertenpuzzle"]),
    ("Stationenlernen", ["Stationenarbeit"]),
    ("Lernzirkel", []),
    ("Kugellager", ["Innen-Außen-Kreis"]),
    ("Galeriegang", ["Gallery Walk", "Museumsrundgang"]),
    ("Brainstorming", []),
    ("Mindmap", []),
    ("Fishbowl", ["Innenkreis-Außenkreis-Diskussion"]),
    ("Fragend-entwickelndes Gespräch", []),
    ("Lerntempoduett", []),
    ("Lerntheke", []),
    ("Debatte", ["Pro-Contra-Debatte", "Streitgespräch"]),
    ("Rollenspiel", []),
]


async def _upsert(db: AsyncSession, content_type: str, titel: str, aliase: list[str]) -> str:
    """Legt den Vokabel-Knoten an oder aktualisiert seine Aliase. Gibt 'insert'|'update' zurück."""
    existing = (
        await db.execute(
            select(ContextNode).where(
                ContextNode.content_type == content_type,
                ContextNode.title == titel,
            )
        )
    ).scalar_one_or_none()

    if existing:
        meta = dict(existing.metadata_ or {})
        meta["aliase"] = aliase
        existing.metadata_ = meta
        return "update"

    db.add(
        ContextNode(
            category="knowledge",
            content_type=content_type,
            title=titel,
            metadata_={"aliase": aliase},
            read_scope="school",
            write_scope="school",
            status="active",
        )
    )
    return "insert"


async def seed() -> None:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    inserted = updated = 0
    async with session_factory() as db:
        for content_type, eintraege in (("sozialform", SOZIALFORMEN), ("methode", METHODEN)):
            for titel, aliase in eintraege:
                action = await _upsert(db, content_type, titel, aliase)
                if action == "insert":
                    inserted += 1
                else:
                    updated += 1
        await db.commit()

    await engine.dispose()
    logger.info("Methodik-Seed abgeschlossen: %d eingefügt, %d aktualisiert.", inserted, updated)


if __name__ == "__main__":
    asyncio.run(seed())
