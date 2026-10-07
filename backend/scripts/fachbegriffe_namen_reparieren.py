#!/usr/bin/env python3
"""
Repariert Herkunftsdatei und Kennung von Fachbegriffen aus einem Zip-Import mit Umlauten
im Dateinamen (0.14).

Bis 0.14 las der Zip-Import solche Namen falsch (`Hu╠êckel-Regel` statt `Hückel-Regel`,
Kennung `ch-hu-ckel-regel`). Einmal nach dem Update auf 0.14 und **vor** dem nächsten
Import ausführen; sonst legt der nächste Import einen zweiten Knoten an. Danach denselben
Vault-Stand einmal neu importieren — das schließt Verknüpfungen, die der alte Import
nicht auflösen konnte. Ein zweiter Lauf findet nichts mehr.

Verwendung:
    python scripts/fachbegriffe_namen_reparieren.py --dry-run   # nur zeigen
    python scripts/fachbegriffe_namen_reparieren.py
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.context.fachbegriffe_namen import namen_reparieren
from app.db.session import AsyncSessionLocal


async def run(*, dry_run: bool) -> int:
    async with AsyncSessionLocal() as db:
        ergebnis = await namen_reparieren(db)
        if dry_run:
            await db.rollback()
        else:
            await db.commit()

    repariert = [r for r in ergebnis if r.kollision is None]
    kollisionen = [r for r in ergebnis if r.kollision is not None]
    for r in repariert:
        kennung = (f"   Kennung {r.alt_id} → {r.neu_id}" if r.neu_id != r.alt_id
                   else "   Kennung bleibt (aus dem Frontmatter)")
        print(f"{r.fach}: {r.alt_quelle} → {r.neu_quelle}\n{kennung}")
    for r in kollisionen:
        print(f"{r.fach}: {r.alt_quelle} — NICHT repariert: Die Kennung {r.neu_id} gehört "
              f"schon „{r.kollision}“. Einen der beiden Knoten von Hand entfernen, dann "
              "erneut laufen lassen.")
    print(f"\n{len(repariert)} Knoten {'zu reparieren (Probelauf, nichts geschrieben)' if dry_run else 'repariert'}"
          f", {len(kollisionen)} Kollision(en).")
    if repariert and not dry_run:
        print("Jetzt denselben Vault-Stand einmal neu importieren — das schließt "
              "Verknüpfungen, die der alte Import nicht auflösen konnte.")
    return 1 if kollisionen else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="Nur zeigen, nichts schreiben")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
