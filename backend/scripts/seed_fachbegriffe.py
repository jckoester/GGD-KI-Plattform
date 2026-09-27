#!/usr/bin/env python3
"""Fachbegriffe und Stoffsteckbriefe aus einem Obsidian-Ordner in den Wissensgraph.

    python scripts/seed_fachbegriffe.py --quelle "<Vault>/Projekte/Fachbegriffe Chemie/Fachbegriffe Ch Pilot"
    python scripts/seed_fachbegriffe.py --quelle "<Pfad>" --dry-run
    python scripts/seed_fachbegriffe.py --quelle "<Pfad>" --ueberschreiben

⚠️ **Die Arbeit steckt nicht mehr hier**, sondern in
`app/context/fachbegriffe_import.py` — dort auch die Begründungen (Idempotenz, zwei
Durchläufe, nicht auflösbare Wikilinks). Dieses Skript ist die Admin-Hülle: Ordner
einlesen, Service rufen, Bericht ausgeben. Den zweiten Weg auf denselben Kern baut
Paket 10 als Upload-Dialog für die Fachschaften.

Das Format beschreibt `_Format.md` im Quellordner, die Schnittstelle
`docs/dev/fachbegriffe-import.md`.

Geänderte Knoten verlieren ihr Embedding und bekommen beim nächsten Backfill ein neues:

    python scripts/embedding_backfill.py --content-type begriff --content-type stoffsteckbrief
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.context.fachbegriffe_import import Bilanz, importiere

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def lies_ordner(quellordner: Path) -> dict[str, bytes]:
    """Einen Ordner in ein Bündel verwandeln — die einzige Stelle mit Dateisystem.

    Gelesen wird flach (`*.md`) plus alles unter `_Abb/`; mehr kennt das Vault-Format
    nicht. Der Endpunkt aus AP3 baut dasselbe Bündel aus einem Zip.
    """
    buendel: dict[str, bytes] = {}
    for pfad in sorted(quellordner.glob("*.md")):
        buendel[pfad.name] = pfad.read_bytes()
    for pfad in sorted((quellordner / "_Abb").glob("*")):
        if pfad.is_file():
            buendel[f"_Abb/{pfad.name}"] = pfad.read_bytes()
    return buendel


async def seed(
    quellordner: Path,
    *,
    fach_vorgabe: str | None = None,
    dry_run: bool = False,
    ueberschreiben: bool = False,
) -> Bilanz:
    dateien = lies_ordner(quellordner)

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        bilanz = await importiere(
            db, dateien, fach_vorgabe=fach_vorgabe, ueberschreiben=ueberschreiben
        )
        if dry_run:
            await db.rollback()
        else:
            await db.commit()

    await engine.dispose()
    return bilanz


def _berichte(bilanz: Bilanz, *, dry_run: bool) -> None:
    logger.info(
        "Fachbegriff-Seed%s: %d neu, %d aktualisiert, %d unverändert; "
        "%d Kanten, davon %s.",
        " (Probelauf, nichts geschrieben)" if dry_run else "",
        bilanz.neu, bilanz.aktualisiert, bilanz.unveraendert, bilanz.kanten,
        f"{bilanz.kanten_geaendert} angefasst" if bilanz.kanten_geaendert
        else "keine geändert",
    )
    if bilanz.uebersprungen:
        logger.warning(
            "%d Knoten seit dem letzten Seed in der Oberfläche geändert und deshalb "
            "nicht überschrieben (mit --ueberschreiben erzwingen): %s",
            len(bilanz.uebersprungen), ", ".join(bilanz.uebersprungen),
        )
    for zeile in bilanz.warnungen:
        logger.warning("%s", zeile)
    if bilanz.offene_fundstellen:
        logger.warning(
            "%d Fundstellen ohne Bildungsplan-Knoten (%d verschieden):",
            sum(bilanz.offene_fundstellen.values()), len(bilanz.offene_fundstellen),
        )
        for roh, anzahl in bilanz.offene_fundstellen.most_common():
            logger.warning("    %2dx  %s", anzahl, roh)
    if bilanz.archivierte_ziele:
        # ⚠️ Kein Fehler des Imports, aber eine Lücke in der Wirkung: In der
        # Detailansicht taucht eine Kante auf einen archivierten Knoten nicht auf.
        logger.warning(
            "%d Fundstellen zeigen auf **archivierte** Bildungsplan-Knoten — die "
            "Kanten entstehen, sind in der Oberfläche aber unsichtbar. Je Edition: %s",
            sum(bilanz.archivierte_ziele.values()),
            ", ".join(f"{k}: {n}" for k, n in bilanz.archivierte_ziele.most_common()),
        )
    if bilanz.offene_ziele:
        logger.info(
            "%d Verweise auf noch nicht vorhandene Bausteine (%d verschieden) — "
            "die Arbeitsliste für die Breite:",
            sum(bilanz.offene_ziele.values()), len(bilanz.offene_ziele),
        )
        for ziel, anzahl in bilanz.offene_ziele.most_common():
            logger.info("    %2dx  %s", anzahl, ziel)
    if bilanz.neu_einzubetten:
        logger.info(
            "%d Vektoren verworfen — ihre Eingabe hat sich geändert.", bilanz.neu_einzubetten
        )
    if bilanz.neu or bilanz.neu_einzubetten:
        logger.info(
            "Nächster Schritt: python scripts/embedding_backfill.py "
            "--content-type begriff --content-type stoffsteckbrief"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fachbegriffe und Stoffsteckbriefe aus einem Obsidian-Ordner einspielen"
    )
    parser.add_argument("--quelle", required=True, type=Path, help="Der Ordner mit den .md-Dateien")
    parser.add_argument(
        "--fach",
        default=None,
        help="Fach für Dateien **ohne** `fach:`-Angabe (Kürzel, Slug oder Name). "
             "Die Angabe in der Datei hat Vorrang.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Nur zeigen, nichts schreiben")
    parser.add_argument(
        "--ueberschreiben",
        action="store_true",
        help="Auch Knoten ersetzen, die seit dem letzten Seed in der Oberfläche "
             "geändert wurden",
    )
    args = parser.parse_args()

    if not args.quelle.is_dir():
        parser.error(f"Kein Verzeichnis: {args.quelle}")

    bilanz = asyncio.run(seed(
        args.quelle,
        fach_vorgabe=args.fach,
        dry_run=args.dry_run,
        ueberschreiben=args.ueberschreiben,
    ))
    _berichte(bilanz, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
