import asyncio
import logging
from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from app.context.embedding import (
    EMBEDDING_CONTENT_TYPES,
    _build_embedding_input,
    generate_embeddings,
)
from app.db.models import ContextNode

logger = logging.getLogger(__name__)

_TOKENS_PER_SECOND = 3000
_AVG_TOKENS_PER_NODE = 150

# Abbruch nach so vielen **vollständig** fehlgeschlagenen Stapeln in Folge.
#
# Scheitert es derart, liegt es nicht am einzelnen Knoten, sondern am Modellzugang — und
# dann hilft Weitermachen nichts. Der reale Fall: Ein ungültiger Anbieter-Schlüssel
# beantwortet LiteLLM mit 401, LiteLLM nimmt die Deployment daraufhin in den Cooldown
# ("Cool down 401 Auth Errors"), und **alle** weiteren Anfragen bekommen
# `429 No deployments available`. Ohne Abbruch arbeitet der Lauf tausende Knoten ab, jeden
# mit vollem Wiederholungsbudget — Stunden Wartezeit für ein Ergebnis, das schon nach dem
# dritten Versuch feststand. Die Knoten bleiben unangetastet (`embedding IS NULL`) und
# kommen im nächsten Lauf wieder dran.
#
# Gezählt werden **Anfragen, nicht Knoten**: Seit der Stapelverarbeitung entspricht ein
# Fehlschlag bis zu EMBEDDING_BATCH_SIZE Knoten, und die verschwendete Zeit hängt an der
# Zahl der Anfragen (jede mit vollem Wiederholungsbudget), nicht an der Zahl der Knoten.
# Ein Stapel gilt nur dann als fehlgeschlagen, wenn **kein** Knoten darin gelungen ist.
_MAX_STAPEL_FEHLER_IN_FOLGE = 3


def _ist_inhaltsfehler(exc: Exception) -> bool:
    """Liegt es am Text — oder am Zugang?

    Die Unterscheidung entscheidet, ob ein gescheiterter Stapel einzeln nachgefasst wird.
    Ein 400 bemängelt die Eingabe (z. B. leerer Text: BGE-M3 lehnt ihn ab, OpenAI nicht),
    dann lohnt das Isolieren des einen schuldigen Textes. Alles andere — 401, 429, Timeout —
    trifft jeden Text gleich; einzeln nachzufassen würde daraus N sinnlose Anfragen machen,
    genau die Verschwendung, gegen die `_MAX_FEHLER_IN_FOLGE` existiert.
    """
    resp = getattr(exc, "response", None)
    return isinstance(exc, httpx.HTTPStatusError) and resp is not None and resp.status_code == 400


@dataclass
class EmbeddingBackfillStats:
    found: int = 0
    ok: int = 0
    errors: int = 0
    skipped: int = 0  # Knoten ohne einbettbaren Text (leer) — übersprungen, kein Fehler
    duration_ms: int = 0
    # True, wenn wegen Fehlerserie vorzeitig beendet — der Rest wurde nicht versucht.
    abgebrochen: bool = False


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

    from app.config import settings
    stapel_groesse = max(1, settings.embedding_batch_size)

    async def _fehler_vermerken(node: ContextNode, exc: Exception) -> None:
        stats.errors += 1
        # Bei HTTP-Fehlern den Response-Body (der eigentliche Grund, z. B.
        # LiteLLM-400-Detail) festhalten, nicht nur die generische httpx-Meldung.
        resp = getattr(exc, "response", None)
        detail = (resp.text if resp is not None else str(exc))[:2000]
        logger.error("Embedding-Fehler Knoten %s: %s", node.id, detail)
        meta = dict(node.metadata_ or {})
        meta["embedding_error"] = detail
        await db.execute(
            update(ContextNode).where(ContextNode.id == node.id).values(metadata_=meta)
        )

    async def _stapel_einbetten(stapel: list[tuple[ContextNode, str]]) -> int:
        """Bettet einen Stapel in EINER Anfrage ein. Rueckgabe: Anzahl Fehlschlaege."""
        try:
            vektoren = await generate_embeddings([text for _, text in stapel])
        except Exception as exc:
            if len(stapel) > 1 and _ist_inhaltsfehler(exc):
                logger.warning(
                    "Stapel (%d Knoten) mit 400 abgelehnt — fasse einzeln nach, um den "
                    "schuldigen Text zu finden.", len(stapel),
                )
                fehler = 0
                for eintrag in stapel:
                    fehler += await _stapel_einbetten([eintrag])
                return fehler
            for node, _ in stapel:
                await _fehler_vermerken(node, exc)
            return len(stapel)

        for (node, _), vektor in zip(stapel, vektoren):
            await db.execute(
                update(ContextNode).where(ContextNode.id == node.id).values(embedding=vektor)
            )
            stats.ok += 1
        return 0

    num_batches = -(-stats.found // batch_size)  # ceiling division
    stapel_fehler_in_folge = 0
    for batch_idx, i in enumerate(range(0, stats.found, batch_size), start=1):
        batch = nodes[i : i + batch_size]

        # Erst die Texte bauen, dann in Anfrage-Stapel schneiden. Leere Knoten fliegen
        # vorher raus — sonst kippt ein einziger von ihnen den ganzen Stapel in den
        # 400er-Sonderweg.
        aufgaben: list[tuple[ContextNode, str]] = []
        for node in batch:
            inp = _build_embedding_input(node)
            if not inp.strip():
                # Kein einbettbarer Text (leerer Knoten) → überspringen statt 400.
                stats.skipped += 1
                continue
            aufgaben.append((node, inp))

        if dry_run:
            stats.ok += len(aufgaben)
        else:
            for start in range(0, len(aufgaben), stapel_groesse):
                if stapel_fehler_in_folge >= _MAX_STAPEL_FEHLER_IN_FOLGE:
                    stats.abgebrochen = True
                    break
                ok_vorher = stats.ok
                await _stapel_einbetten(aufgaben[start : start + stapel_groesse])
                # Ein einziger Erfolg im Stapel beweist, dass der Zugang steht — dann ist
                # ein begleitender Fehler ein Einzelfall und kein Grund zum Abbruch.
                # (Auf „keine Fehler" zu prüfen wäre falsch: Beim Isolieren nach einem 400
                # scheitert genau ein Text, während die übrigen gelingen.)
                stapel_fehler_in_folge = 0 if stats.ok > ok_vorher else stapel_fehler_in_folge + 1

        if not dry_run:
            await db.commit()

        if stats.abgebrochen:
            logger.error(
                "ABBRUCH: %d Stapel in Folge vollständig fehlgeschlagen — das liegt am "
                "Modellzugang, nicht an den Knoten. %d von %d Knoten wurden nicht versucht; "
                "sie bleiben ohne Embedding und kommen im nächsten Lauf wieder dran. "
                "Ursache im gespeicherten Fehlertext nachsehen: "
                "SELECT metadata->>'embedding_error' FROM context_nodes "
                "WHERE metadata ? 'embedding_error' LIMIT 1;",
                _MAX_STAPEL_FEHLER_IN_FOLGE,
                stats.found - stats.ok - stats.errors - stats.skipped,
                stats.found,
            )
            break

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
