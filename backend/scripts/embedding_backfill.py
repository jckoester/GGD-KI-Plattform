#!/usr/bin/env python3
"""
Generiert Embeddings für alle Knoten mit embedding IS NULL (Backfill-Cron).

Verwendung:
    python scripts/embedding_backfill.py
    python scripts/embedding_backfill.py --dry-run
    python scripts/embedding_backfill.py --batch-size 50 --limit 500
    python scripts/embedding_backfill.py --reindex
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.crons.embedding_backfill_service import backfill_embeddings
from app.db.session import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run(
    *,
    batch_size: int,
    limit: int | None,
    dry_run: bool,
    reindex: bool,
    content_types: list[str] | None,
) -> int:
    async with AsyncSessionLocal() as db:
        stats = await backfill_embeddings(
            db,
            batch_size=batch_size,
            limit=limit,
            dry_run=dry_run,
            reindex=reindex,
            content_types=content_types,
        )
    logger.info(
        "embedding_backfill done found=%d ok=%d errors=%d skipped=%d duration_ms=%d",
        stats.found,
        stats.ok,
        stats.errors,
        stats.skipped,
        stats.duration_ms,
    )
    return 1 if stats.errors else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Embedding-Backfill für Kontextspeicher-Knoten"
    )
    parser.add_argument("--dry-run", action="store_true", help="Nur zählen, nichts schreiben")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch-Größe (Default: 100)")
    parser.add_argument("--limit", type=int, default=None, help="Maximale Anzahl Knoten")
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Nach dem Lauf REINDEX INDEX idx_context_nodes_embedding ausführen",
    )
    parser.add_argument(
        "--content-type",
        action="append",
        default=None,
        dest="content_types",
        help="Nur diesen content_type einbetten (mehrfach angebbar, z. B. --content-type operator)",
    )
    args = parser.parse_args()

    if args.batch_size < 1:
        logger.error("--batch-size muss >= 1 sein")
        sys.exit(1)

    try:
        exit_code = asyncio.run(
            run(
                batch_size=args.batch_size,
                limit=args.limit,
                dry_run=args.dry_run,
                reindex=args.reindex,
                content_types=args.content_types,
            )
        )
    except Exception:
        logger.exception("embedding_backfill fehlgeschlagen")
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
