"""Embedding-Batch-Job: verarbeitet alle Knoten mit embedding IS NULL.

Aufruf:
  python scripts/run_embedding_batch.py \
    --db-url postgresql+asyncpg://user:pass@localhost/ggd_ki \
    [--batch-size 100] \
    [--dry-run]

Schreibt Fortschritts-Log nach data/import_logs/embedding_YYYY-MM-DD.log.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Backend-Package muss im PYTHONPATH sein:
#   export PYTHONPATH=backend
from app.db.models import ContextNode
from app.context.embedding import (
    EMBEDDING_CONTENT_TYPES,
    _build_embedding_input as build_embedding_input,
    generate_embedding,
)

logger = logging.getLogger('run_embedding_batch')

# Tokens/Sekunde-Limit (konservativer Default: < OpenAI-Tier-1-Limit)
DEFAULT_TOKENS_PER_SECOND = 3000
AVG_TOKENS_PER_NODE = 150  # Schaetzung: Breadcrumb + Kompetenztext


async def process_batch(
    nodes: list[ContextNode],
    session: AsyncSession,
    dry_run: bool,
    warnings: list[str],
) -> tuple[int, int]:
    """Generiert Embeddings fuer einen Batch und schreibt sie in die DB.

    Gibt (verarbeitet, fehler) zurueck.
    """
    ok = 0
    errors = 0
    for node in nodes:
        try:
            text = build_embedding_input(node)
            if dry_run:
                ok += 1
                continue
            embedding = await generate_embedding(text)
            await session.execute(
                update(ContextNode)
                .where(ContextNode.id == node.id)
                .values(embedding=embedding)
            )
            ok += 1
        except Exception as exc:
            errors += 1
            msg = f"Embedding-Fehler Knoten {node.id} ({node.metadata_.get('bp_id', '?')}): {exc}"
            logger.error(msg)
            warnings.append(msg)
            # Fehler in metadata_ vermerken (auch im dry_run nicht)
            if not dry_run:
                meta = dict(node.metadata_)
                meta['embedding_error'] = str(exc)
                await session.execute(
                    update(ContextNode)
                    .where(ContextNode.id == node.id)
                    .values(metadata_=meta)
                )

    if not dry_run:
        await session.commit()

    return ok, errors


async def run_batch(
    db_url: str,
    batch_size: int = 100,
    dry_run: bool = False,
) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            # Anzahl offener Knoten ermitteln
            count_q = select(ContextNode).where(
                ContextNode.content_type.in_(EMBEDDING_CONTENT_TYPES),
                ContextNode.embedding.is_(None),
                ContextNode.status == 'active',
            )
            result = await session.execute(count_q)
            all_nodes = list(result.scalars().all())
            total = len(all_nodes)

            if total == 0:
                logger.info("Keine Knoten ohne Embedding gefunden — nichts zu tun")
                return

            logger.info(f"{'[DRY RUN] ' if dry_run else ''}{total} Knoten ohne Embedding")

            warnings: list[str] = []
            total_ok = 0
            total_errors = 0

            for i in range(0, total, batch_size):
                batch = all_nodes[i:i + batch_size]
                ok, errors = await process_batch(batch, session, dry_run, warnings)
                total_ok += ok
                total_errors += errors
                logger.info(
                    f"Batch {i // batch_size + 1}: {ok} OK, {errors} Fehler "
                    f"({i + len(batch)}/{total})"
                )
                # Rate-Limiting: Pause proportional zur Batch-Groesse
                estimated_tokens = len(batch) * AVG_TOKENS_PER_NODE
                wait = estimated_tokens / DEFAULT_TOKENS_PER_SECOND
                if wait > 0.1 and not dry_run:
                    await asyncio.sleep(wait)
    finally:
        await engine.dispose()

    logger.info(
        f"{'[DRY RUN] ' if dry_run else ''}"
        f"Fertig: {total_ok} Embeddings generiert, {total_errors} Fehler"
    )

    # Log schreiben
    log_dir = Path('data/import_logs')
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    log_file = log_dir / f"embedding_{date_str}.log"
    with log_file.open('a') as f:
        f.write(
            f"{datetime.now(timezone.utc).isoformat()} "
            f"{'DRY_RUN ' if dry_run else ''}"
            f"total={total} ok={total_ok} errors={total_errors}\n"
        )
        if warnings:
            f.write('\n'.join(warnings) + '\n')


def main() -> None:
    parser = argparse.ArgumentParser(description='Embedding-Batch-Job')
    parser.add_argument('--db-url', default=os.environ.get('DATABASE_URL', ''))
    parser.add_argument('--batch-size', type=int, default=100)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if not args.db_url:
        logger.error("Kein --db-url und DATABASE_URL nicht gesetzt")
        sys.exit(1)

    asyncio.run(run_batch(args.db_url, args.batch_size, args.dry_run))


if __name__ == '__main__':
    main()
