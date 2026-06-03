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

logger = logging.getLogger(__name__)


async def create_db_session(db_url: str) -> AsyncSession:
    """Erstellt eine asynchrone DB-Session."""
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


def convert_yaml_to_draft(data: dict) -> CurriculumDraftConfirmed:
    """Konvertiert YAML-Daten in das CurriculumDraftConfirmed-Format."""
    # Validierung der Pflichtfelder
    required_fields = ["schule", "fach_code", "schulart", "jahrgangsstufe", "fachplan_id", "bp_version"]
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
                entry = CurriculumDraftEntry(
                    ik=entry_data.get("ik"),
                    ik_partiell=entry_data.get("ik_partiell", False),
                    pk=entry_data.get("pk", []),
                    konkretisierung=entry_data.get("konkretisierung"),
                    hinweise=entry_data.get("hinweise"),
                    lp=entry_data.get("lp", []),
                    _confidence=1.0,
                    _warnings=[],
                )
                eintraege.append(entry)
            
            ls = CurriculumDraftLernsequenz(
                bp_titel=ls_data.get("bp_titel"),
                bp_leitidee=ls_data.get("bp_leitidee"),
                reihenfolge=ls_data.get("reihenfolge"),
                eintraege=eintraege,
                _confidence=1.0,
                _warnings=[],
            )
            lernsequenzen.append(ls)
        
        kapitel = CurriculumDraftKapitel(
            titel=kap_data["titel"],
            reihenfolge=kap_data["reihenfolge"],
            std=kap_data.get("std"),
            hinweis=kap_data.get("hinweis"),
            konkretisierung=kap_data.get("konkretisierung", []),
            lernsequenzen=lernsequenzen,
            _confidence=1.0,
            _warnings=[],
        )
        kapitel_list.append(kapitel)
    
    return CurriculumDraftConfirmed(
        schule=data["schule"],
        fach_code=data["fach_code"],
        fach=data.get("fach"),
        schulart=data["schulart"],
        jahrgangsstufe=data["jahrgangsstufe"],
        fachplan_id=data["fachplan_id"],
        bp_version=data["bp_version"],
        vorwort=data.get("vorwort"),
        kapitel=kapitel_list,
    )


async def import_single_curriculum(
    db_session: AsyncSession,
    yaml_data: dict,
    owner_pseudonym: str = "system",
) -> tuple[str, int]:
    """Importiert ein einzelnes Curriculum.
    
    Rückgabe: (curriculum_import_key, node_count)
    """
    draft = convert_yaml_to_draft(yaml_data)
    curriculum_id, stats = await import_curriculum_from_draft(db_session, draft, owner_pseudonym)
    
    total_nodes = stats.curriculum_count + stats.kapitel_count + stats.lernsequenz_count
    
    import_key = f"{draft.fachplan_id}_{draft.jahrgangsstufe}"
    
    return import_key, total_nodes


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
        
        for yaml_file in yaml_files:
            logger.info(f"Verarbeite {yaml_file}...")
            try:
                yaml_data = load_yaml_file(yaml_file)
                import_key, node_count = await import_single_curriculum(
                    db, yaml_data, args.owner or "system"
                )
                total_curricula += 1
                total_nodes += node_count
                logger.info(f"  ✓ Importiert: {node_count} Knoten (Import-Key: {import_key})")
                
                # Warnungen ausgeben
                if "warnings" in yaml_data:
                    for warning in yaml_data["warnings"]:
                        logger.warning(f"  ⚠ {warning}")
                
            except Exception as e:
                logger.error(f"  ✗ Fehler bei {yaml_file}: {e}")
                errors += 1
                if not args.continue_on_error:
                    logger.error("Abbruch wegen Fehlers (--continue-on-error zum Fortsetzen)")
                    return 1
        
        logger.info(f"\nFertig: {total_curricula} Curricula importiert, {total_nodes} Knoten erstellt")
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
