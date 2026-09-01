#!/usr/bin/env python3
"""Testknoten für die S2-Fälle des Prüfsatzes anlegen (Entwicklungsinstanz).

Die Fälle zur **Titel-Teilsuche** brauchen Bausteine, die es im Bildungsplan nicht gibt:
beschreibende, mehrwortige Titel, wie sie Lehrkräfte selbst vergeben. Ohne sie misst der
Prüfsatz an dieser Stelle nichts — und ein Prüfsatz, dessen Erwartungen sich nicht
reproduzieren lassen, ist keiner.

    python scripts/seed_search_eval_nodes.py            # anlegen (idempotent)
    python scripts/seed_search_eval_nodes.py --entfernen # wieder wegräumen

⚠️ **Nur für Entwicklungs- und Testinstanzen.** Die Knoten gehören dem Pseudonym
``pruefsatz`` und sind schulweit lesbar; auf einer Produktivinstanz hätten sie nichts
verloren. Das Skript weigert sich deshalb, wenn ``ENVIRONMENT=production`` gesetzt ist.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa

from app.config import settings
from app.db.models import ContextNode
from app.db.session import AsyncSessionLocal

# Das Pseudonym, unter dem der Prüfsatz sucht (`scripts/search_eval.py`).
PRUEFSATZ_PSEUDONYM = "pruefsatz"
FREMDES_PSEUDONYM = "pruefsatz-fremd"

# Erkennungsmerkmal zum Wiederfinden und Aufräumen — im Titel wäre es störend.
MARKE = {"pruefsatz_fixture": True}

KNOTEN = [
    {
        "title": "Anleitung zur Verwendung des Operators nennen",
        "content": (
            "Der Operator „nennen“ verlangt eine knappe Aufzählung ohne Erläuterung. "
            "Diese Anleitung zeigt an Beispielen, wie Aufgabenstellungen damit "
            "formuliert werden und woran Schüler:innen erkennen, dass keine Begründung "
            "erwartet wird."
        ),
        "content_type": "operatorenblatt",
        "category": "document",
        "owner_pseudonym": PRUEFSATZ_PSEUDONYM,
        "notiz": "S2-Leitfall: langer beschreibender Titel, kurze Anfrage.",
    },
    {
        "title": "Anleitung zur Verwendung des Operators nennen",
        "content": (
            "Gleichnamige Handreichung einer anderen Lehrkraft. Dient dem Nachweis, "
            "dass eigene Bausteine vor fremden stehen."
        ),
        "content_type": "operatorenblatt",
        "category": "document",
        "owner_pseudonym": FREMDES_PSEUDONYM,
        "notiz": "S2-Gegenstück: gleicher Titel, fremde Eigentümerin.",
    },
    {
        "title": "Merkblatt zur Gedichtanalyse in der Mittelstufe",
        "content": (
            "Schrittfolge für die Analyse lyrischer Texte: Erschließen, sprachliche "
            "Bilder deuten, Form und Inhalt aufeinander beziehen."
        ),
        "content_type": "methodenblatt",
        "category": "document",
        "owner_pseudonym": PRUEFSATZ_PSEUDONYM,
        "notiz": (
            "Wächter: liegt thematisch neben dem Bestandsfall zur Gedichtinterpretation. "
            "Die Teilsuche darf ihn dort nicht nach vorn spülen."
        ),
    },
]


async def _vorhandene(db) -> list[ContextNode]:
    treffer = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.metadata_["pruefsatz_fixture"].astext == "true"
        )
    )
    return list(treffer.scalars().all())


async def anlegen() -> int:
    async with AsyncSessionLocal() as db:
        vorhanden = {(n.title, n.owner_pseudonym) for n in await _vorhandene(db)}
        neu = 0
        for eintrag in KNOTEN:
            schluessel = (eintrag["title"], eintrag["owner_pseudonym"])
            if schluessel in vorhanden:
                continue
            db.add(ContextNode(
                category=eintrag["category"],
                content_type=eintrag["content_type"],
                title=eintrag["title"],
                content=eintrag["content"],
                owner_pseudonym=eintrag["owner_pseudonym"],
                # Schulweit lesbar: Der Prüfsatz sucht als `pruefsatz` und muss auch den
                # fremden Knoten sehen — sonst ließe sich die Reihenfolge nicht messen.
                read_scope="school",
                write_scope="private",
                status="active",
                metadata_={**MARKE, "notiz": eintrag["notiz"]},
            ))
            neu += 1
        await db.commit()
    return neu


async def entfernen() -> int:
    async with AsyncSessionLocal() as db:
        knoten = await _vorhandene(db)
        for n in knoten:
            await db.delete(n)
        await db.commit()
    return len(knoten)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--entfernen", action="store_true",
                   help="Die Testknoten wieder löschen")
    args = p.parse_args()

    if settings.environment == "production":
        p.error(
            "Nicht auf einer Produktivinstanz. Diese Knoten sind Testdaten und hätten "
            "im Wissensgraph einer Schule nichts verloren."
        )

    if args.entfernen:
        print(f"{asyncio.run(entfernen())} Testknoten entfernt.")
        return

    neu = asyncio.run(anlegen())
    print(
        f"{neu} Testknoten angelegt"
        + (" (die übrigen gab es schon)." if neu < len(KNOTEN) else ".")
    )
    print("Embeddings werden dafür nicht gebraucht — die S2-Fälle messen die Titelsuche.")


if __name__ == "__main__":
    main()
