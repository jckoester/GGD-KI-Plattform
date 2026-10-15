#!/usr/bin/env python3
"""
Listet gleichnamige Fachbegriffe über Fachgrenzen im Bestand (0.16, F7) — liest nur.

Seit 0.16 legen Import und Editor einen Begriff, den ein anderes Fach schon führt, nur noch
mit Abgrenzung an. Was davor entstand, bleibt stehen und blockiert keine Bearbeitung; diese
Liste ist die Aufräumliste dafür. Je Paar: welche Art von Namensgleichheit (gleicher Titel,
Titel = Suchbegriff, gleicher Suchbegriff) und ob einer den anderen schon abgrenzt.

Was die Fachschaften damit tun: einen Eintrag zurückziehen und auf den anderen verweisen —
oder beide behalten und unter `## Abgrenzung` den Unterschied nennen. „Gleicher Suchbegriff"
ist nur ein Hinweis; Suchbegriffe dürfen locker sein.

Verwendung:
    python scripts/fachbegriffe_kollisionen.py                 # alle Paare
    python scripts/fachbegriffe_kollisionen.py --nur-offene    # ohne Abgrenzung und ohne Hinweise
Exit-Code 1, wenn es nicht abgegrenzte Paare gibt (ohne die Hinweise).
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.context.fachbegriffe_kollision import ARTEN, bestand
from app.db.session import AsyncSessionLocal


def _eintrag(k) -> str:
    kennung = f" [[{k.kennung}]]" if k.kennung else ""
    return f"„{k.titel}“ ({k.fach or 'fachlos'}){kennung}"


async def run(*, nur_offene: bool) -> int:
    async with AsyncSessionLocal() as db:
        paare = await bestand(db)
    offen = [p for p in paare if p.art != "alias" and not p.abgegrenzt]
    for p in paare:
        if nur_offene and (p.art == "alias" or p.abgegrenzt):
            continue
        stand = ("abgegrenzt" if p.abgegrenzt
                 else "Hinweis" if p.art == "alias" else "OHNE Abgrenzung")
        print(f"{_eintrag(p.a)} ↔ {_eintrag(p.b)} — {ARTEN[p.art]}, {stand}")
    hinweise = sum(p.art == "alias" for p in paare)
    print(f"\n{len(paare)} Paar(e) über Fachgrenzen: {len(offen)} ohne Abgrenzung, "
          f"{len(paare) - len(offen) - hinweise} abgegrenzt, {hinweise} nur gleicher Suchbegriff.")
    return 1 if offen else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--nur-offene", action="store_true",
                        help="Nur Paare ohne Abgrenzung, ohne die Hinweise")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(nur_offene=args.nur_offene)))


if __name__ == "__main__":
    main()
