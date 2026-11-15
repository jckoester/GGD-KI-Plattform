#!/usr/bin/env python3
"""
Hängt IK und PK aus einem fremden Fach in Curricula auf das eigene Fach um (0.45).

Bis 25.08.2026 löste der Curriculum-Import PK-Nummern ohne Fach auf; ein importiertes
Mathematik-Curriculum hing danach an den PK von Kunst, Geographie, Chemie … Die Abdeckung im
Curriculum zeigt solche Kompetenzen unter „aus einem anderen Fach“.

Das Skript sucht je betroffener Kompetenz dieselbe Nummer im Fach und in der
Bildungsplan-Fassung des Curriculums und hängt Eintrag und Kante dorthin um. Findet es keine
oder mehrere, ändert es nichts und meldet den Fund. Verweise in Hinweisen und Material bleiben
unberührt. Ohne `--anwenden` ein Probelauf; ein zweiter Lauf findet nichts mehr.

Verwendung (im Verzeichnis backend/):
    python scripts/curriculum_kompetenzen_reparieren.py                  # Probelauf, alle Curricula
    python scripts/curriculum_kompetenzen_reparieren.py --curriculum <id>
    python scripts/curriculum_kompetenzen_reparieren.py --anwenden
"""
import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.context.kompetenz_reparatur import kompetenzen_reparieren
from app.db.session import AsyncSessionLocal


async def run(*, anwenden: bool, curriculum_id: UUID | None) -> int:
    async with AsyncSessionLocal() as db:
        funde = await kompetenzen_reparieren(db, curriculum_id=curriculum_id, anwenden=anwenden)
        if anwenden:
            await db.commit()
        else:
            await db.rollback()

    curriculum = None
    for f in funde:
        if f.curriculum != curriculum:
            curriculum = f.curriculum
            print(f"\n{curriculum}")
        ziel = f"→ {f.neu_id}" if f.neu_id else f"NICHT repariert: {f.grund}"
        print(f"  {f.lernsequenz}: {f.typ.upper()} {f.nr} (bisher {f.alt_fach}) {ziel}")

    repariert = sum(1 for f in funde if f.neu_id)
    offen = len(funde) - repariert
    print(f"\n{repariert} Kompetenz(en) "
          f"{'umgehängt' if anwenden else 'umzuhängen (Probelauf, nichts geschrieben — mit --anwenden schreiben)'}"
          f", {offen} ohne eindeutigen Ersatz.")
    if offen:
        print("Die übrigen im Curriculum-Editor von Hand ersetzen.")
    return 1 if offen else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--anwenden", action="store_true", help="Schreiben (sonst Probelauf)")
    parser.add_argument("--curriculum", type=UUID, default=None, help="Nur dieses Curriculum")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(anwenden=args.anwenden, curriculum_id=args.curriculum)))


if __name__ == "__main__":
    main()
