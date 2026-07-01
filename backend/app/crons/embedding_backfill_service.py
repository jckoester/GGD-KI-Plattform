import asyncio
import logging
from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.embedding import EMBEDDING_CONTENT_TYPES, _build_embedding_input, generate_embedding
from app.db.models import ContextNode

logger = logging.getLogger(__name__)

_TOKENS_PER_SECOND = 3000
_AVG_TOKENS_PER_NODE = 150


@dataclass
class EmbeddingBackfillStats:
    found: int = 0
    ok: int = 0
    errors: int = 0
    skipped: int = 0  # Knoten ohne einbettbaren Text (leer) — übersprungen, kein Fehler
    duration_ms: int = 0


async def backfill_embeddings(
    db: AsyncSession,
    *,
    batch_size: int = 100,
    limit: int | None = None,
    dry_run: bool = False,
    reindex: bool = False,
    content_types: list[str] | None = None,
) -> EmbeddingBackfillStats:
    stats = EmbeddingBackfillStats()
    started = perf_counter()

    # Optional auf bestimmte content_types eingrenzen (z. B. gezieltes Nachziehen nach
    # dem Import eines neuen Typs). Nur einbettbare Typen sind zulässig.
    if content_types is None:
        selected_types = EMBEDDING_CONTENT_TYPES
    else:
        selected_types = [t for t in content_types if t in EMBEDDING_CONTENT_TYPES]
        ignored = sorted(set(content_types) - set(selected_types))
        if ignored:
            logger.warning("backfill_embeddings: nicht einbettbare content_types ignoriert: %s", ignored)

    logger.info(
        "backfill_embeddings gestartet batch_size=%d limit=%s dry_run=%s reindex=%s content_types=%s",
        batch_size,
        limit,
        dry_run,
        reindex,
        content_types or "alle",
    )

    query = (
        select(ContextNode)
        .where(
            ContextNode.embedding.is_(None),
            ContextNode.status == "active",
            ContextNode.content_type.in_(selected_types),
        )
        .order_by(ContextNode.created_at.asc())
    )
    if limit is not None:
        query = query.limit(limit)

    result = await db.execute(query)
    nodes = list(result.scalars().all())
    stats.found = len(nodes)

    if stats.found == 0:
        logger.info("backfill_embeddings: keine Knoten ohne Embedding — nichts zu tun")
        stats.duration_ms = int((perf_counter() - started) * 1000)
        return stats

    logger.info("%s%d Knoten ohne Embedding", "[DRY RUN] " if dry_run else "", stats.found)

    num_batches = -(-stats.found // batch_size)  # ceiling division
    for batch_idx, i in enumerate(range(0, stats.found, batch_size), start=1):
        batch = nodes[i : i + batch_size]
        for node in batch:
            inp = _build_embedding_input(node)
            if not inp.strip():
                # Kein einbettbarer Text (leerer Knoten) → überspringen statt 400.
                stats.skipped += 1
                continue
            if dry_run:
                stats.ok += 1
                continue
            try:
                embedding = await generate_embedding(inp)
                await db.execute(
                    update(ContextNode)
                    .where(ContextNode.id == node.id)
                    .values(embedding=embedding)
                )
                stats.ok += 1
            except Exception as exc:
                stats.errors += 1
                # Bei HTTP-Fehlern den Response-Body (der eigentliche Grund, z. B.
                # LiteLLM-400-Detail) festhalten, nicht nur die generische httpx-Meldung.
                resp = getattr(exc, "response", None)
                detail = (resp.text if resp is not None else str(exc))[:2000]
                logger.error("Embedding-Fehler Knoten %s: %s", node.id, detail)
                meta = dict(node.metadata_ or {})
                meta["embedding_error"] = detail
                await db.execute(
                    update(ContextNode)
                    .where(ContextNode.id == node.id)
                    .values(metadata_=meta)
                )

        if not dry_run:
            await db.commit()

        logger.info(
            "Batch %d/%d: ok=%d errors=%d (%d/%d Knoten)",
            batch_idx,
            num_batches,
            stats.ok,
            stats.errors,
            min(i + batch_size, stats.found),
            stats.found,
        )

        estimated_tokens = len(batch) * _AVG_TOKENS_PER_NODE
        wait = estimated_tokens / _TOKENS_PER_SECOND
        if wait > 0.1 and not dry_run and batch_idx < num_batches:
            await asyncio.sleep(wait)

    if reindex and not dry_run:
        logger.info("REINDEX INDEX idx_context_nodes_embedding")
        await db.execute(text("REINDEX INDEX idx_context_nodes_embedding"))
        await db.commit()

    stats.duration_ms = int((perf_counter() - started) * 1000)
    logger.info(
        "backfill_embeddings fertig found=%d ok=%d errors=%d skipped=%d duration_ms=%d",
        stats.found,
        stats.ok,
        stats.errors,
        stats.skipped,
        stats.duration_ms,
    )
    return stats
