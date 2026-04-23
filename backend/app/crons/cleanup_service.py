import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, JwtRevocation, PseudonymAudit, UserPreference
from app.litellm.client import LiteLLMClient

logger = logging.getLogger(__name__)

_ACCOUNT_RETENTION_DAYS = 90
_CONVERSATION_RETENTION_DAYS = 93


@dataclass
class CleanupStats:
    found: int = 0
    deleted_local: int = 0
    litellm_delete_ok: int = 0
    litellm_delete_failed: int = 0
    litellm_key_delete_ok: int = 0
    litellm_key_delete_failed: int = 0
    errors: int = 0
    duration_ms: int = 0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def cleanup_inactive_accounts(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 500,
    dry_run: bool = False,
) -> CleanupStats:
    stats = CleanupStats()
    started = perf_counter()
    current_time = now or _utc_now()
    cutoff = current_time - timedelta(days=_ACCOUNT_RETENTION_DAYS)

    logger.info(
        "cleanup_inactive_accounts gestartet cutoff=%s limit=%d dry_run=%s",
        cutoff.isoformat(),
        limit,
        dry_run,
    )

    if dry_run:
        count_result = await db.execute(
            select(func.count()).select_from(PseudonymAudit).where(PseudonymAudit.last_login_at < cutoff)
        )
        stats.found = int(count_result.scalar_one() or 0)
        stats.duration_ms = int((perf_counter() - started) * 1000)
        return stats

    client = LiteLLMClient()
    failed_pseudonyms: set[str] = set()
    try:
        while True:
            query = (
                select(PseudonymAudit)
                .where(PseudonymAudit.last_login_at < cutoff)
                .order_by(PseudonymAudit.last_login_at.asc())
                .limit(limit)
            )
            if failed_pseudonyms:
                query = query.where(~PseudonymAudit.pseudonym.in_(failed_pseudonyms))

            result = await db.execute(query)
            audit_entries = list(result.scalars().all())
            if not audit_entries:
                break

            stats.found += len(audit_entries)

            for audit_entry in audit_entries:
                pseudonym = audit_entry.pseudonym
                try:
                    await client.delete_user(pseudonym)
                    stats.litellm_delete_ok += 1
                except Exception as exc:
                    stats.litellm_delete_failed += 1
                    logger.warning(
                        "LiteLLM-User konnte nicht gelöscht werden pseudonym=%s error=%s",
                        pseudonym,
                        exc,
                    )

                # Virtual Key löschen falls vorhanden
                if audit_entry.litellm_key:
                    try:
                        await client.delete_key(audit_entry.litellm_key)
                        stats.litellm_key_delete_ok += 1
                    except Exception as exc:
                        stats.litellm_key_delete_failed += 1
                        logger.warning(
                            "LiteLLM-Key konnte nicht gelöscht werden pseudonym=%s error=%s",
                            pseudonym,
                            exc,
                        )

                try:
                    # Atomare lokale Löschung pro Pseudonym.
                    async with db.begin_nested():
                        await db.execute(
                            delete(Conversation).where(Conversation.pseudonym == pseudonym)
                        )
                        await db.execute(
                            delete(UserPreference).where(UserPreference.pseudonym == pseudonym)
                        )
                        await db.execute(
                            delete(JwtRevocation).where(JwtRevocation.pseudonym == pseudonym)
                        )
                        await db.execute(
                            delete(PseudonymAudit).where(PseudonymAudit.pseudonym == pseudonym)
                        )
                    await db.commit()
                    stats.deleted_local += 1
                except Exception:
                    await db.rollback()
                    stats.errors += 1
                    failed_pseudonyms.add(pseudonym)
                    logger.exception(
                        "Lokale Löschung fehlgeschlagen pseudonym=%s", pseudonym
                    )
    finally:
        await client.close()
        stats.duration_ms = int((perf_counter() - started) * 1000)

    logger.info(
        "cleanup_inactive_accounts fertig found=%d deleted_local=%d litellm_ok=%d litellm_failed=%d "
        "key_delete_ok=%d key_delete_failed=%d errors=%d duration_ms=%d",
        stats.found,
        stats.deleted_local,
        stats.litellm_delete_ok,
        stats.litellm_delete_failed,
        stats.litellm_key_delete_ok,
        stats.litellm_key_delete_failed,
        stats.errors,
        stats.duration_ms,
    )
    return stats


async def cleanup_stale_conversations(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 500,
    dry_run: bool = False,
) -> CleanupStats:
    stats = CleanupStats()
    started = perf_counter()
    current_time = now or _utc_now()
    cutoff = current_time - timedelta(days=_CONVERSATION_RETENTION_DAYS)
    activity_ts = func.coalesce(Conversation.last_message_at, Conversation.created_at)

    logger.info(
        "cleanup_stale_conversations gestartet cutoff=%s limit=%d dry_run=%s",
        cutoff.isoformat(),
        limit,
        dry_run,
    )

    if dry_run:
        count_result = await db.execute(
            select(func.count()).select_from(Conversation).where(activity_ts < cutoff)
        )
        stats.found = int(count_result.scalar_one() or 0)
        stats.duration_ms = int((perf_counter() - started) * 1000)
        return stats

    while True:
        result = await db.execute(
            select(Conversation.id)
            .where(activity_ts < cutoff)
            .order_by(activity_ts.asc())
            .limit(limit)
        )
        ids: list[UUID] = list(result.scalars().all())
        if not ids:
            break

        stats.found += len(ids)
        try:
            async with db.begin_nested():
                await db.execute(delete(Conversation).where(Conversation.id.in_(ids)))
            await db.commit()
            stats.deleted_local += len(ids)
        except Exception:
            await db.rollback()
            stats.errors += 1
            logger.exception(
                "Batch-Löschung für Konversationen fehlgeschlagen batch_size=%d",
                len(ids),
            )
            break

    stats.duration_ms = int((perf_counter() - started) * 1000)
    logger.info(
        "cleanup_stale_conversations fertig found=%d deleted_local=%d errors=%d duration_ms=%d",
        stats.found,
        stats.deleted_local,
        stats.errors,
        stats.duration_ms,
    )
    return stats
