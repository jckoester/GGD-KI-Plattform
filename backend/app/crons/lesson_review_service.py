"""Auto-Bestätigung von Nachbereitungen nach der nächsten Stunde der Gruppe."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from time import perf_counter
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LessonSlot
from app.planning.review_service import complete_review

logger = logging.getLogger(__name__)


@dataclass
class AutoConfirmStats:
    candidates: int = 0
    confirmed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_ms: int = 0


async def auto_confirm_reviews(
    db: AsyncSession,
    *,
    today: date | None = None,
    dry_run: bool = False,
) -> AutoConfirmStats:
    """Bestätigt vergangene Stunden, auf die eine spätere Stunde derselben Gruppe folgt."""
    stats = AutoConfirmStats()
    started = perf_counter()
    current_date = today or date.today()

    # Kandidaten: vergangene Slots mit Stunde, noch nicht nachbereitet
    result = await db.execute(
        sa.select(LessonSlot).where(
            LessonSlot.stunde_node_id.is_not(None),
            LessonSlot.kategorie.in_(["unterricht", "vertretung"]),
            LessonSlot.nachbereitet_at.is_(None),
            LessonSlot.date < current_date,
        )
    )
    candidates = result.scalars().all()
    stats.candidates = len(candidates)

    for slot in candidates:
        # Prüfen ob bereits eine spätere Stunde derselben Gruppe in der Vergangenheit liegt
        later = await db.execute(
            sa.select(LessonSlot.id).where(
                LessonSlot.group_id == slot.group_id,
                LessonSlot.kategorie.in_(["unterricht", "vertretung"]),
                LessonSlot.date > slot.date,
                LessonSlot.date < current_date,
            ).limit(1)
        )
        if later.scalar_one_or_none() is None:
            stats.skipped += 1
            continue

        if dry_run:
            logger.info("dry_run: würde bestätigen slot_id=%s group_id=%s date=%s",
                        slot.id, slot.group_id, slot.date)
            stats.confirmed += 1
            continue

        try:
            await complete_review(
                db,
                slot.id,
                group_id=slot.group_id,
                phasen_status={},
                auto=True,
            )
            logger.info("auto_confirm: slot_id=%s group_id=%s date=%s", slot.id, slot.group_id, slot.date)
            stats.confirmed += 1
        except Exception:
            logger.exception("auto_confirm fehlgeschlagen slot_id=%s", slot.id)
            stats.errors += 1

    stats.duration_ms = int((perf_counter() - started) * 1000)
    return stats
