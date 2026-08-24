#!/usr/bin/env python3
"""CLI-Skript für den Curriculum-Import (YAML-Wiederimport & Batch-Import).

Dieses Skript liest YAML-Dateien im Curriculum-Format und importiert sie in die Datenbank.
Es verwendet dieselbe Kernlogik wie der API-Endpunkt POST /api/context/curricula.

Aufruf:
    python -m scripts.import_curriculum --file config/curricula/mathe_kl5_6.yaml --db-url $DATABASE_URL

Umgebung:
    DATABASE_URL: Postgres-Connection-String (z.B. postgresql://user:pass@localhost:5432/db)
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import yaml

# Füge das Projektverzeichnis zum Python-Pfad hinzu
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.context.schemas import CurriculumDraftConfirmed, CurriculumDraftKapitel, CurriculumDraftLernsequenz, CurriculumDraftEntry
from app.context.service import import_curriculum_from_draft
from app.db.models import ContextNode

logger = logging.getLogger(__name__)


def create_db_session(db_url: str) -> AsyncSession:
    """Erstellt eine asynchrone DB-Session.

    Bewusst **nicht** `async def`: Die Funktion wird als `async with create_db_session(...)`
    verwendet. Als Coroutine ergab das `'coroutine' object does not support the
    asynchronous context manager protocol` — das Skript brach beim Start ab, noch bevor es
    eine Datei ansah.
    """
    engine = create_async_engine(db_url, echo=False)
    AsyncTestingSession = sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    return AsyncTestingSession()


def load_yaml_file(file_path: str) -> dict:
    """Lädt eine YAML-Datei und validiert die Struktur."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    if data is None:
        raise ValueError(f"Datei {file_path} ist leer oder ungültiges YAML")
    
    return data


def convert_yaml_to_draft(data: dict, bp_version_override: str | None = None) -> CurriculumDraftConfirmed:
    """Konvertiert YAML-Daten in das CurriculumDraftConfirmed-Format.

    `bp_version_override` setzt die Bildungsplan-Edition aus der Datei außer Kraft. Nötig,
    wenn Quell- und Zielinstanz **verschiedene Editionen aktiv** haben — etwa beim
    Einspielen eines Produktiv-Exports (V2) in eine Dev-Instanz, in der die Basisedition
    aktiv ist. Bewusst ein ausdrücklicher Schalter und keine automatische Rückfallebene:
    Kompetenznummern können sich zwischen Editionen unterscheiden, das Ergebnis muss also
    jemand verantworten und die gemeldeten offenen Verweise ansehen.
    """
    # Validierung der Pflichtfelder.
    # `fachplan_id` steht bewusst NICHT mehr darin: Exporte echter Curricula schreiben
    # dort `null`, weil gescrapte Fachplan-Knoten `bp_id` tragen statt `fachplan_id`.
    # Verlangt wurde damit ein Feld, das die eigene Exportfunktion nicht füllen kann.
    required_fields = ["schule", "fach_code", "schulart", "jahrgangsstufe", "bp_version"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        raise ValueError(f"Fehlende Pflichtfelder im YAML: {', '.join(missing)}")
    
    # Kapitel konvertieren
    kapitel_list = []
    for kap_data in data.get("kapitel", []):
        lernsequenzen = []
        for ls_data in kap_data.get("lernsequenzen", []):
            eintraege = []
            for entry_data in ls_data.get("eintraege", []):
                # ik akzeptiert: str, list[str], list[dict({nr, partiell})]
                ik_raw = entry_data.get("ik")
                entry = CurriculumDraftEntry(
                    ik=ik_raw,
                    ik_partiell=entry_data.get("ik_partiell", False),
                    pk=entry_data.get("pk", []),
                    konkretisierung=entry_data.get("konkretisierung"),
                    hinweise=entry_data.get("hinweise"),
                    lp=entry_data.get("lp", []),
                    material=entry_data.get("material"),
                )
                eintraege.append(entry)

            ls = CurriculumDraftLernsequenz(
                bp_titel=ls_data.get("bp_titel"),
                bp_leitidee=ls_data.get("bp_leitidee"),
                reihenfolge=ls_data.get("reihenfolge"),
                std=str(ls_data["std"]) if ls_data.get("std") is not None else None,
                eintraege=eintraege,
            )
            lernsequenzen.append(ls)
        
        kapitel = CurriculumDraftKapitel(
            titel=kap_data["titel"],
            reihenfolge=kap_data["reihenfolge"],
            # YAML liefert `std: 4` als int zurück, das Zwischenformat erwartet Text.
            # Bei den Lernsequenzen wurde schon gecastet, bei den Kapiteln nicht — der
            # Wiederimport eines echten Exports scheiterte daran an der Validierung.
            std=str(kap_data["std"]) if kap_data.get("std") is not None else None,
            hinweis=kap_data.get("hinweis"),
            konkretisierung=kap_data.get("konkretisierung", []),
            lernsequenzen=lernsequenzen,
        )
        kapitel_list.append(kapitel)
    
    return CurriculumDraftConfirmed(
        schule=data["schule"],
        fach_code=data["fach_code"],
        fach=data.get("fach"),
        schulart=data["schulart"],
        jahrgangsstufe=str(data["jahrgangsstufe"]),
        fachplan_id=data.get("fachplan_id") or None,
        # Wird die Edition überschrieben, darf die bp_id NICHT mitgehen: Sie zeigt auf
        # den Fachplan der ursprünglichen Edition und würde die Überschreibung wieder
        # aushebeln (bp_id wird vor Fach+Edition ausgewertet).
        bp_id=None if bp_version_override else (data.get("bp_id") or None),
        bp_version=bp_version_override or data["bp_version"],
        vorwort=data.get("vorwort"),
        kapitel=kapitel_list,
    )


async def import_single_curriculum(
    db_session: AsyncSession,
    yaml_data: dict,
    owner_pseudonym: str = "system",
    bp_version_override: str | None = None,
) -> tuple[str, int]:
    """Importiert ein einzelnes Curriculum.
    
    Rückgabe: (curriculum_import_key, node_count)
    """
    draft = convert_yaml_to_draft(yaml_data, bp_version_override)
    curriculum_id, stats = await import_curriculum_from_draft(db_session, draft, owner_pseudonym)

    total_nodes = stats.curriculum_count + stats.kapitel_count + stats.lernsequenz_count

    # Den **tatsächlich vergebenen** Schlüssel melden statt ihn nachzubauen: Er hängt
    # davon ab, wie der Fachplan aufgelöst wurde (fachplan_id, sonst bp_id).
    node = await db_session.get(ContextNode, curriculum_id)
    import_key = (node.metadata_ or {}).get("import_key", "?") if node else "?"

    return import_key, total_nodes, stats


async def main(args: argparse.Namespace) -> int:
    """Hauptfunktion für das CLI-Skript."""
    # Logging konfigurieren
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    db_url = args.db_url or os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL ist erforderlich (als Argument oder Umgebungsvariable)")
        return 1
    
    # Datei(en) laden
    yaml_files = []
    if args.file:
        yaml_files = [args.file]
    elif args.directory:
        # Alle YAML-Dateien im Verzeichnis
        import glob
        yaml_files = glob.glob(os.path.join(args.directory, "*.yaml")) + \
                     glob.glob(os.path.join(args.directory, "*.yml"))
        if not yaml_files:
            logger.error(f"Keine YAML-Dateien in {args.directory} gefunden")
            return 1
    else:
        logger.error("Es muss entweder --file oder --directory angegeben werden")
        return 1
    
    logger.info(f"Importiere {len(yaml_files)} Datei(en)")
    
    # DB-Session erstellen
    async with create_db_session(db_url) as db:
        total_curricula = 0
        total_nodes = 0
        errors = 0
        
        offene_verweise = 0
        for yaml_file in yaml_files:
            logger.info(f"Verarbeite {yaml_file}...")
            try:
                yaml_data = load_yaml_file(yaml_file)
                import_key, node_count, stats = await import_single_curriculum(
                    db, yaml_data, args.owner or "system", args.bp_version
                )
                total_curricula += 1
                total_nodes += node_count
                logger.info(f"  ✓ Importiert: {node_count} Knoten (Import-Key: {import_key})")

                # Warnungen des Imports ausgeben — NICHT die des YAML.
                # Hier stehen die nicht auflösbaren Kompetenzverweise: In einer
                # Ziel-Instanz mit anderem oder fehlendem Bildungsplan werden sie
                # übersprungen, das Curriculum wird trotzdem angelegt. Ohne diese
                # Ausgabe verschwänden sie lautlos — das Curriculum sähe vollständig
                # aus und wäre es nicht.
                for warnung in stats.warnings:
                    logger.warning(f"  ⚠ {warnung}")
                offene_verweise += len(stats.warnings)

                # Je Datei festschreiben. Ohne dieses Commit schrieb das Skript nichts:
                # `import_curriculum_from_draft` flusht nur, und die Session wird ohne
                # Commit geschlossen — also verworfen. Je Datei statt am Ende, damit ein
                # später scheiterndes Curriculum die zuvor gelungenen nicht mitreißt.
                if args.dry_run:
                    await db.rollback()
                else:
                    await db.commit()

            except Exception as e:
                logger.error(f"  ✗ Fehler bei {yaml_file}: {e}")
                await db.rollback()
                errors += 1
                if not args.continue_on_error:
                    logger.error("Abbruch wegen Fehlers (--continue-on-error zum Fortsetzen)")
                    return 1

        was = "geprüft (nichts geschrieben)" if args.dry_run else "importiert"
        logger.info(
            f"\nFertig: {total_curricula} Curricula {was}, {total_nodes} Knoten"
        )
        if offene_verweise:
            logger.warning(
                f"  {offene_verweise} Kompetenzverweis(e) konnten nicht aufgelöst werden — "
                f"die betroffenen Stellen bleiben ohne Verknüpfung. "
                f"Fehlt der Bildungsplan dieses Fachs in dieser Instanz?"
            )
        if errors > 0:
            logger.warning(f"  ({errors} Fehler aufgetreten)")

        return 0 if errors == 0 else 1


def parse_args() -> argparse.Namespace:
    """Parsed die Command-Line-Argumente."""
    parser = argparse.ArgumentParser(
        description="Importiere Curricula aus YAML-Dateien in die Datenbank",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python -m scripts.import_curriculum --file config/curricula/mathe.yaml
  python -m scripts.import_curriculum --directory config/curricula/
  python -m scripts.import_curriculum --file mathe.yaml --owner teacher123

Umgebungsvariablen:
  DATABASE_URL:   Postgres-Connection-String
""",
    )
    
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="Pfad zur YAML-Datei",
    )
    
    parser.add_argument(
        "--directory", "-d",
        type=str,
        help="Verzeichnis mit YAML-Dateien (alle .yaml/.yml Dateien werden importiert)",
    )
    
    parser.add_argument(
        "--db-url",
        type=str,
        help="Datenbank-URL (überschreibt DATABASE_URL Umgebungsvariable)",
    )
    
    parser.add_argument(
        "--owner",
        type=str,
        default="system",
        help="Besitzer-Pseudonym für die importierten Knoten (Default: system)",
    )
    
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Fährt mit dem nächsten Import fort, falls ein Fehler auftritt",
    )

    parser.add_argument(
        "--bp-version",
        type=str,
        default=None,
        help=(
            "Bildungsplan-Edition aus der Datei überschreiben (z. B. '2016'). "
            "Für den Fall, dass Quell- und Zielinstanz verschiedene Editionen aktiv "
            "haben. Die gemeldeten offenen Kompetenzverweise danach unbedingt ansehen — "
            "Nummern können sich zwischen Editionen unterscheiden."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Nur prüfen: Auflösung und Warnungen melden, am Ende zurückrollen. "
            "Empfehlenswert vor dem ersten Import in eine fremde Instanz."
        ),
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Ausführliche Ausgaben",
    )
    
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    
    exit_code = asyncio.run(main(args))
    sys.exit(exit_code)
