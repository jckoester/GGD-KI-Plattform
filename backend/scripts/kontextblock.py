#!/usr/bin/env python3
"""Den Kontextblock zeigen, den eine Frage in den Prompt bringt — ohne Modell.

    cd backend && venv/bin/python scripts/kontextblock.py \\
        --datei scripts/szenarien/ap7_chemie.txt --fach CH --stufe 8 --ausgabe /tmp/vorher

Ruft die **echte** ``get_context_for_query`` auf, mit einer Konversation im angegebenen
Fach oder in der angegebenen Unterrichtsgruppe — angelegt in einer Transaktion, die am
Ende zurückgerollt wird. In der Datenbank bleibt nichts.

Mit ``--gruppe`` misst es dieselbe Lage wie ``chat_probe.py --gruppe``: Fach **und** Stufe
kommen dann aus der Gruppe, ``--stufe`` tritt dahinter zurück (wie im Chat).

**Wozu (0.14, Schritt 1):** Prompt-Änderungen an der Vorab-Suche werden vorher und nachher
am selben Prüfsatz gemessen. Der Kontextblock ist der deterministische Teil davon: Er hängt
nicht vom Modell ab, und ein ``diff`` zweier Ausgabeverzeichnisse zeigt genau, was sich am
Prompt geändert hat. Was das Modell daraus macht, misst ``chat_probe.py``.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa

from app.context.embedding import vor_einer_messung
from app.context.service import get_context_for_query
from app.db.models import Conversation, Subject
from app.db.session import AsyncSessionLocal


def _fragen(pfad: Path) -> list[str]:
    return [z.strip() for z in pfad.read_text(encoding="utf-8").splitlines()
            if z.strip() and not z.startswith("#")]


async def run(args) -> None:
    await vor_einer_messung(trotzdem=args.trotzdem)
    fragen = _fragen(args.datei)
    args.ausgabe.mkdir(parents=True, exist_ok=True)
    async with AsyncSessionLocal() as db:
        fach_id = None
        if args.fach:
            fach_id = (await db.execute(
                sa.select(Subject.id).where(
                    sa.or_(Subject.fach_code == args.fach, Subject.slug == args.fach)
                )
            )).scalar_one_or_none()
            if fach_id is None:
                sys.exit(f"Fach nicht gefunden: {args.fach}")
        try:
            for nr, frage in enumerate(fragen, start=1):
                konversation = Conversation(
                    pseudonym=args.pseudonym, subject_id=fach_id, group_id=args.gruppe,
                    assistant_id=args.assistent, model_used="messung",
                )
                db.add(konversation)
                await db.flush()
                block = await get_context_for_query(
                    args.assistent, args.pseudonym, frage, konversation.id, db,
                    rollen=(args.rolle,), jwt_stufe=args.stufe,
                )
                datei = args.ausgabe / f"{nr:02d}.txt"
                datei.write_text(f"# {frage}\n\n{block}\n", encoding="utf-8")
                print(f"{nr:02d}  {len(block):6d} Zeichen  {frage}")
        finally:
            await db.rollback()


def main() -> None:
    p = argparse.ArgumentParser(description="Kontextblock einer Frage zeigen, ohne Modell")
    p.add_argument("--datei", type=Path, required=True, help="Eine Frage je Zeile")
    p.add_argument("--ausgabe", type=Path, required=True, help="Verzeichnis für NN.txt")
    p.add_argument("--fach", help="Fach der Konversation (fach_code oder slug)")
    p.add_argument("--gruppe", type=int, default=None,
                   help="Unterrichtsgruppe der Konversation (Fach und Stufe kommen dann von ihr)")
    p.add_argument("--stufe", default=None, help="Jahrgang im Token (Zeichenkette)")
    p.add_argument("--rolle", default="student", choices=["student", "teacher"])
    p.add_argument("--assistent", type=int, default=None)
    p.add_argument("--pseudonym", default="messung-kontextblock")
    p.add_argument("--trotzdem", action="store_true",
                   help="Auch messen, wenn Knoten ohne Vektor sind (sonst Abbruch)")
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
