#!/usr/bin/env python3
"""
Schüler-Bausteine in die Werkstatt überführen (0.41, Päckchen AN, Schritt 9). Einmalig nach
dem Update; Regeln in `app/artifacts/schueler_wechsel.py`.

Verwendung (aus `backend/`):
    python scripts/schueler_bausteine_ueberfuehren.py --dry-run
    python scripts/schueler_bausteine_ueberfuehren.py
    python scripts/schueler_bausteine_ueberfuehren.py --mit-strukturierung

Erst den Probelauf ansehen. Gliederungen/Mindmaps (`strukturierung`) von Personen ohne
Lehrkraft-Rolle listet der Lauf nur; überführt werden sie mit `--mit-strukturierung`.

Exit-Code 0 = durchgelaufen (auch wenn Bausteine stehen blieben), 1 = Fehler.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.artifacts.schueler_wechsel import BLEIBT_STEHEN, ueberfuehre
from app.core.audit import audit_getrennt
from app.db.session import AsyncSessionLocal


async def run(*, dry_run: bool, mit_strukturierung: bool) -> int:
    async with AsyncSessionLocal() as db:
        bericht = await ueberfuehre(db, dry_run=dry_run, mit_strukturierung=mit_strukturierung)

    kopf = "PROBELAUF — nichts geändert" if dry_run else "Überführt"
    print(f"{kopf}: {len(bericht.eintraege)} Bausteine geprüft")
    for e in bericht.eintraege:
        bleibt = " (bleibt stehen)" if e.ausgang in BLEIBT_STEHEN else ""
        produkt = f" → Produkt {e.produkt_id}" if e.produkt_id else ""
        print(f"  {e.node_id}  {e.content_type:<22} {e.ausgang}{produkt}{bleibt}")
    print("Zusammen:")
    for ausgang, anzahl in sorted(bericht.zaehlung().items()):
        print(f"  {ausgang:<22} {anzahl}")
    if not dry_run:
        await audit_getrennt(
            "system", "schueler_bausteine_ueberfuehrt",
            daten={**bericht.zaehlung(), "geloescht": bericht.geloescht},
        )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Schüler-Bausteine in die Werkstatt überführen")
    parser.add_argument("--dry-run", action="store_true", help="Nur zeigen, nichts ändern")
    parser.add_argument(
        "--mit-strukturierung", action="store_true",
        help="Auch Gliederungen/Mindmaps von Schüler:innen überführen (sonst nur gelistet)",
    )
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(run(dry_run=args.dry_run, mit_strukturierung=args.mit_strukturierung)))
    except Exception as exc:  # noqa: BLE001 — Skript: Meldung statt Traceback-Wand
        print(f"Fehler: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
