"""Slot-Generator: erzeugt lesson_slots für ein Halbjahr aus group_week_patterns."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GroupWeekPattern, LessonSlot
from app.planning.calendar import SchoolYearConfig, halbjahr_bounds, is_schoolday, load_school_year
from app.planning.snapshots import create_snapshot


@dataclass
class SlotGenStats:
    created: int
    halbjahr: int
    used_hj1_fallback: bool = False


async def generate_slots(
    db: AsyncSession,
    group_id: int,
    halbjahr: int,
    *,
    regenerate: bool = False,
    created_by: str | None = None,
    cfg: SchoolYearConfig | None = None,
) -> SlotGenStats:
    """Erzeugt lesson_slots für ein Halbjahr aus den Wochenmustern der Gruppe.

    Idempotenz-Guard: ohne regenerate=True bricht die Funktion mit 409 ab wenn
    das Halbjahr bereits Slots hat.

    Mit regenerate=True: erst Snapshot anlegen, dann alte Slots löschen, dann neu erzeugen.
    Ohne Muster für HJ2 wird das HJ1-Muster als Fallback verwendet (vorläufig).
    """
    existing_count = await db.scalar(
        sa.select(sa.func.count()).where(
            LessonSlot.group_id == group_id,
            LessonSlot.halbjahr == halbjahr,
        )
    )
    if existing_count and not regenerate:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Halbjahr {halbjahr} hat bereits {existing_count} Slots. "
                "regenerate=true verwenden um neu zu generieren."
            ),
        )

    patterns_result = await db.execute(
        sa.select(GroupWeekPattern).where(
            GroupWeekPattern.group_id == group_id,
            GroupWeekPattern.halbjahr == halbjahr,
        )
    )
    patterns = patterns_result.scalars().all()

    used_hj1_fallback = False
    if not patterns and halbjahr == 2:
        patterns_result = await db.execute(
            sa.select(GroupWeekPattern).where(
                GroupWeekPattern.group_id == group_id,
                GroupWeekPattern.halbjahr == 1,
            )
        )
        patterns = patterns_result.scalars().all()
        used_hj1_fallback = True

    calendar = cfg or load_school_year()
    start, end = halbjahr_bounds(halbjahr, calendar)

    if regenerate and existing_count:
        await create_snapshot(db, group_id, reason="regeneration", created_by=created_by)
        await db.execute(
            sa.delete(LessonSlot).where(
                LessonSlot.group_id == group_id,
                LessonSlot.halbjahr == halbjahr,
            )
        )
        await db.flush()

    by_weekday: dict[int, list[GroupWeekPattern]] = defaultdict(list)
    for p in patterns:
        by_weekday[p.weekday].append(p)

    created = 0
    d = start
    while d <= end:
        if is_schoolday(d, calendar):
            for p in by_weekday.get(d.weekday(), []):
                slot = LessonSlot(
                    group_id=group_id,
                    date=d,
                    start_period=p.start_period,
                    periods=p.periods,
                    halbjahr=halbjahr,
                    kategorie="unterricht",
                )
                db.add(slot)
                created += 1
        d += timedelta(days=1)

    await db.commit()
    return SlotGenStats(created=created, halbjahr=halbjahr, used_hj1_fallback=used_hj1_fallback)
