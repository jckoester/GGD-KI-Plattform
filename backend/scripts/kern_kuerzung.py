#!/usr/bin/env python3
"""Welche Begriffe und Stoffsteckbriefe verlieren im Prompt Teile ihres **Kerns**?

    cd backend && venv/bin/python scripts/kern_kuerzung.py            # Übersicht
    cd backend && venv/bin/python scripts/kern_kuerzung.py --text     # mit dem abgeschnittenen Teil

Der Kern ist Definition und Erklärung — alles vor „### Beispiele". `kuerze()` opfert
zuerst die Beispiele; ist der Kern selbst länger als das Budget, schneidet es ihn hart.
Das Skript rechnet genau wie der Prompt (Abbildungen aufgelöst, dann gekürzt) und zeigt,
was dabei wegfällt.

**Wozu (0.14, Schritt 5, F4):** Ob ein größeres Budget für den Kern sich lohnt, hängt
daran, ob im abgeschnittenen Teil etwas steht, das eine Antwort braucht — das lässt sich
nur lesen, nicht zählen. Das Skript liefert die Lesevorlage.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa

from app.context.modellsicht import (
    ABSCHNITTS_TYPEN, INHALT_MAX_ZEICHEN_ABSCHNITTE, _BEISPIEL_UEBERSCHRIFT,
    abbildungen_aufgeloest,
)
from app.db.models import ContextNode, Subject
from app.db.session import AsyncSessionLocal


def kern_von(inhalt: str) -> str:
    treffer = _BEISPIEL_UEBERSCHRIFT.search(inhalt)
    return inhalt[: treffer.start()].rstrip() if treffer else inhalt.rstrip()


async def run(mit_text: bool, grenze: int) -> None:
    async with AsyncSessionLocal() as db:
        zeilen = (await db.execute(
            sa.select(ContextNode.title, ContextNode.content, ContextNode.metadata_,
                      ContextNode.content_type, Subject.name)
            .outerjoin(Subject, Subject.id == ContextNode.subject_id)
            .where(ContextNode.content_type.in_(ABSCHNITTS_TYPEN),
                   ContextNode.status == "active")
            .order_by(ContextNode.title)
        )).all()

    gekuerzt = []
    for titel, inhalt, metadata, typ, fach in zeilen:
        kern = kern_von(abbildungen_aufgeloest((inhalt or "").strip(), metadata))
        if len(kern) >= INHALT_MAX_ZEICHEN_ABSCHNITTE:
            fassung = (metadata or {}).get("fassung")
            name = f"{titel} ({fassung})" if fassung else titel
            gekuerzt.append((name, typ, fach, kern))

    print(f"{len(zeilen)} Knoten ({', '.join(ABSCHNITTS_TYPEN)}), davon {len(gekuerzt)} mit "
          f"gekürztem Kern (Budget {INHALT_MAX_ZEICHEN_ABSCHNITTE} Zeichen)\n")
    print(f"{'Kern':>6}  {'weg':>5}  {'bis ' + str(grenze):>9}  Knoten")
    for name, typ, fach, kern in sorted(gekuerzt, key=lambda z: -len(z[3])):
        weg = len(kern) - INHALT_MAX_ZEICHEN_ABSCHNITTE
        passt = "ganz" if len(kern) <= grenze else f"−{len(kern) - grenze}"
        print(f"{len(kern):6d}  {weg:5d}  {passt:>9}  {name} · {typ} · {fach or '—'}")
    if not mit_text:
        return
    for name, _, _, kern in sorted(gekuerzt, key=lambda z: z[0]):
        print(f"\n{'─' * 78}\n▸ {name} — abgeschnitten ab Zeichen {INHALT_MAX_ZEICHEN_ABSCHNITTE}:\n")
        print(kern[INHALT_MAX_ZEICHEN_ABSCHNITTE:])


def main() -> None:
    p = argparse.ArgumentParser(description="Gekürzte Kerne von Begriffen auflisten")
    p.add_argument("--text", action="store_true", help="Den abgeschnittenen Teil ausgeben")
    p.add_argument("--grenze", type=int, default=2500,
                   help="Vergleichsbudget für den Kern (Vorgabe 2500, Variante b)")
    args = p.parse_args()
    asyncio.run(run(args.text, args.grenze))


if __name__ == "__main__":
    main()
