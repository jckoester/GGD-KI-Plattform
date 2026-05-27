"""Batch-Embedding-Job: generiert Embeddings für alle Knoten ohne Embedding.

Verarbeitet nur content_types aus EMBEDDING_CONTENT_TYPES (Whitelist).

Verwendung:
  python -m scripts.run_embedding_batch --db-url postgresql+asyncpg://... [--batch-size 50] [--dry-run]
"""

import argparse
import asyncio
import logging

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.context.embedding import EMBEDDING_CONTENT_TYPES, _build_embedding_input, generate_embedding
from app.db.models import ContextNode

logger = logging.getLogger(__name__)


async def run_batch(db_url: str, batch_size: int = 50, dry_run: bool = False) -> None:
    """Generiert Embeddings für alle Whitelist-Knoten ohne Embedding.

    Args:
        db_url: asyncpg-Verbindungs-URL
        batch_size: Anzahl Knoten pro DB-Commit
        dry_run: Wenn True, kein DB-Update
    """
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        result = await db.execute(
            sa.select(ContextNode)
            .where(
                ContextNode.content_type.in_(EMBEDDING_CONTENT_TYPES),
                ContextNode.status == "active",
                ContextNode.embedding.is_(None),
            )
            .order_by(ContextNode.created_at)
        )
        nodes = list(result.scalars().all())

    logger.info(f"{len(nodes)} Knoten ohne Embedding gefunden.")

    processed = 0
    async with session_factory() as db:
        for node in nodes:
            try:
                text = _build_embedding_input(node)
                embedding = await generate_embedding(text)
                if not dry_run:
                    await db.execute(
                        sa.update(ContextNode)
                        .where(ContextNode.id == node.id)
                        .values(embedding=embedding)
                    )
                processed += 1
                if processed % batch_size == 0:
                    if not dry_run:
                        await db.commit()
                    logger.info(f"{processed}/{len(nodes)} verarbeitet.")
            except Exception as exc:
                logger.error(f"Fehler bei Knoten {node.id} ({node.content_type}): {exc}")

        if not dry_run and processed % batch_size != 0:
            await db.commit()

    logger.info(f"Fertig: {processed}/{len(nodes)} Embeddings generiert.")

    await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Embedding-Batch-Job")
    parser.add_argument("--db-url", required=True)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run_batch(args.db_url, args.batch_size, args.dry_run))
