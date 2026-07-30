#!/usr/bin/env python3
"""
Stellt die Vektorbreite von context_nodes.embedding auf EMBEDDING_DIMENSIONS um.

Der Weg für einen **Modellwechsel im laufenden Betrieb**. Migration 0043 deckt nur
Neuinstallationen ab — Alembic führt eine angewendete Revision nicht erneut aus, und
`downgrade 0042 && upgrade head` würde alle Revisionen oberhalb von 0042 mit aus- und
wieder einbauen. Beide Pfade teilen die Implementierung in app/db/embedding_column.py.

⚠️ Die Umstellung VERWIRFT alle vorhandenen Embeddings: Vektoren verschiedener Modelle
liegen in unterschiedlichen Räumen und sind nicht vergleichbar. Danach ist ein
vollständiges Re-Embedding nötig, bis dahin liefert die semantische Suche keine Treffer.

Ablauf (siehe docs/runbooks/modellwechsel.md):
    1. EMBEDDING_MODEL + EMBEDDING_DIMENSIONS in .env auf die neuen Werte setzen
    2. python scripts/resize_embedding_column.py --dry-run    # was würde passieren?
    3. python scripts/resize_embedding_column.py --yes
    4. python scripts/embedding_backfill.py --batch-size 100
    5. python scripts/embedding_backfill.py --reindex

Verwendung:
    python scripts/resize_embedding_column.py --dry-run
    python scripts/resize_embedding_column.py            # fragt vor dem Zugriff nach
    python scripts/resize_embedding_column.py --yes      # ohne Rückfrage (Automation)
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine

from app.config import settings
from app.db.embedding_column import HNSW_MAX_DIM, current_dimension, resize_embedding_column

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _sync_url() -> str:
    """DDL läuft synchron — den asyncpg-DSN der App auf psycopg2 umschreiben."""
    url = settings.database_url
    if url.startswith("postgresql+asyncpg"):
        return url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    return url


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vektorbreite von context_nodes.embedding auf EMBEDDING_DIMENSIONS setzen"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Nur berichten, was passieren würde (inkl. Anzahl betroffener Embeddings)",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="Ohne Rückfrage ausführen (für Automation/Runbooks)",
    )
    args = parser.parse_args()

    target = settings.embedding_dimensions
    if target > HNSW_MAX_DIM:
        logger.error(
            "EMBEDDING_DIMENSIONS=%d überschreitet das HNSW-Limit von %d (pgvector).",
            target, HNSW_MAX_DIM,
        )
        sys.exit(1)

    engine = create_engine(_sync_url())
    try:
        # Erst lesen und berichten, dann (nach Bestätigung) in eigener Transaktion schreiben.
        with engine.connect() as conn:
            preview = resize_embedding_column(conn, target, dry_run=True)
            present = current_dimension(conn)

        if not preview.changed:
            logger.info(
                "context_nodes.embedding ist bereits vector(%d) — nichts zu tun. "
                "Embeddings bleiben erhalten.", target,
            )
            return

        logger.warning(
            "Umstellung vector(%s) → vector(%d) verwirft %d Embeddings. "
            "Danach ist ein vollständiges Re-Embedding nötig "
            "(scripts/embedding_backfill.py); bis dahin liefert die semantische Suche "
            "keine Treffer.",
            present, target, preview.cleared,
        )
        logger.info("Modell laut Konfiguration: EMBEDDING_MODEL=%s", settings.embedding_model)

        if args.dry_run:
            logger.info("--dry-run: nichts geändert.")
            return

        if not args.yes:
            answer = input(f"Wirklich auf vector({target}) umstellen? [ja/NEIN] ").strip().lower()
            if answer not in ("ja", "j", "yes", "y"):
                logger.info("Abgebrochen — nichts geändert.")
                sys.exit(1)

        with engine.begin() as conn:
            result = resize_embedding_column(conn, target)

        logger.info(
            "Fertig: vector(%s) → vector(%d), %d Embeddings verworfen. "
            "Jetzt neu einbetten: python scripts/embedding_backfill.py --batch-size 100 "
            "&& python scripts/embedding_backfill.py --reindex",
            result.previous, result.target, result.cleared,
        )
    except Exception:
        logger.exception("Umstellung fehlgeschlagen")
        sys.exit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
