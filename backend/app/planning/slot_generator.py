"""Slot-Generator: erzeugt lesson_slots für ein Halbjahr aus group_week_patterns."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GroupWeekPattern, LessonSlot
from app.planning.calendar import (
    A_WOCHE,
    WOECHENTLICH,
    SchoolYearConfig,
    ab_phasen,
    halbjahr_bounds,
    is_schoolday,
    load_school_year,
)
from app.planning.snapshots import create_snapshot
from app.planning.umhaengen import (
    AlterSlot,
    NeuerTermin,
    plane_umhaengen,
    wende_umhaengen_an,
)


@dataclass
class SlotGenStats:
    created: int
    halbjahr: int
    used_hj1_fallback: bool = False
    # Wurden die erzeugten Termine als vorläufig markiert?
    vorlaeufig: bool = False
    # Wie viele vorhandene Slots der Neuaufbau **nicht** angefasst hat, weil sie nicht
    # aus dem Muster stammen. Null bei einem Lauf ohne `regenerate`.
    verschont: int = 0
    # Wurde eine bestehende Planung auf das neue Raster umgehängt?
    umgehaengt: int = 0
    geparkt: int = 0
    meldungen: list[str] = field(default_factory=list)
    # Der Fallback trug ein 14-tägiges Muster ins zweite Halbjahr. Das ist die einzige
    # Stelle, an der eine Phase über den Halbjahreswechsel hinweg fortgeschrieben wird —
    # und die einzige, an der sie danebenliegen kann, wenn die Schule dort neu zählt.
    fallback_vierzehntaegig: bool = False


def _findet_statt(rhythmus: str, phase: int) -> bool:
    """Ob ein Muster in einer Woche dieser Phase Unterricht hat.

    Phase 0 heißt A-Woche, Phase 1 B-Woche (`ab_phasen`). Welche Woche welchen Buchstaben
    trägt, ist gleichgültig — entscheidend ist allein, dass die Ableitung aus dem
    Stundenplan und diese Funktion dieselbe Regel benutzen.
    """
    if rhythmus == WOECHENTLICH:
        return True
    return phase == (0 if rhythmus == A_WOCHE else 1)


def _raster(patterns, start, end, phasen, calendar, belegt) -> list[tuple]:
    """Die Termine des Halbjahres als `(datum, start_period, periods)`.

    Ausgelagert, weil zwei Wege sie brauchen: das gewöhnliche Erzeugen und das Umhängen.
    Zwei Rechnungen desselben Rasters wären die eine Stelle, an der beide auseinanderlaufen
    könnten, ohne dass es auffiele.
    """
    by_weekday: dict[int, list[GroupWeekPattern]] = defaultdict(list)
    for p in patterns:
        by_weekday[p.weekday].append(p)

    termine: list[tuple] = []
    d = start
    while d <= end:
        if is_schoolday(d, calendar):
            # Der Montag liegt immer in `phasen`: `is_schoolday(d)` macht die Woche zur
            # Unterrichtswoche, und genau die sammelt `ab_phasen`.
            phase = phasen[d - timedelta(days=d.weekday())]
            for p in by_weekday.get(d.weekday(), []):
                if not _findet_statt(p.rhythmus, phase):
                    continue
                if (d, p.start_period) in belegt:
                    # Ein verschonter Slot sitzt schon hier. Die Musterzeile entfällt —
                    # zwei Slots auf derselben Stunde wären eine Dublette.
                    continue
                termine.append((d, p.start_period, p.periods))
        d += timedelta(days=1)
    return termine


async def generate_slots(
    db: AsyncSession,
    group_id: int,
    halbjahr: int,
    *,
    regenerate: bool = False,
    vorlaeufig: bool = False,
    created_by: str | None = None,
    cfg: SchoolYearConfig | None = None,
) -> SlotGenStats:
    """Erzeugt lesson_slots für ein Halbjahr aus den Wochenmustern der Gruppe.

    Idempotenz-Guard: ohne regenerate=True bricht die Funktion mit 409 ab wenn
    das Halbjahr bereits Slots hat.

    Mit regenerate=True: erst Snapshot anlegen, dann alte Slots löschen, dann neu erzeugen.
    Ohne Muster für HJ2 wird das HJ1-Muster als Fallback verwendet (vorläufig).

    **Der Neuaufbau verschont, was kein Muster reproduziert.** Gelöscht wird nur
    `source='pattern'`. Ein Slot mit `source='import'` trägt eine Quellangabe aus dem
    Stundenplan, einer mit `source='manual'` eine Entscheidung von Hand — beides entsteht
    beim Neuaufbau nicht wieder. Bis zum 22.09.2026 fiel das ganze Halbjahr; ein vom
    Abgleich angelegter Termin verschwand damit beim nächsten Erzeugen wieder.

    Trägt ein verschonter Slot denselben Termin wie eine Musterzeile, **entfällt die
    Musterzeile** (Entscheidung 22.09.2026, F4): Der bestehende Slot ist der konkretere —
    er kennt seine Quelle — und zwei Slots auf derselben Stunde wären eine Dublette, die
    niemand auflösen kann.

    `vorlaeufig=True` markiert die erzeugten Termine als Annahme; siehe
    `LessonSlot.vorlaeufig`.

    **14-tägige Muster erzeugen nur in ihrer Woche einen Slot.** Welche Woche das ist,
    entscheidet `ab_phasen` — dieselbe Regel, mit der die Ableitung aus dem Stundenplan das
    Etikett vergeben hat. Bis zum 14.09.2026 wurde `rhythmus` hier gar nicht gelesen; ein
    14-tägiger Termin erzeugte doppelt so viele Stunden, wie er sollte.
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
    # Einmal bauen, danach nachschlagen: Die Unterrichtswochenzählung fängt bei jeder
    # Einzelabfrage wieder am Schuljahresbeginn an.
    phasen = ab_phasen(calendar)
    fallback_vierzehntaegig = used_hj1_fallback and any(
        p.rhythmus != WOECHENTLICH for p in patterns
    )

    verschont: list[LessonSlot] = []
    umzuhaengen: list[AlterSlot] = []
    if regenerate and existing_count:
        vorhanden = list(
            (
                await db.execute(
                    sa.select(LessonSlot).where(
                        LessonSlot.group_id == group_id,
                        LessonSlot.halbjahr == halbjahr,
                    )
                )
            )
            .scalars()
            .all()
        )
        # Nur Muster-Slots verschwinden; alles andere trägt eine Quellangabe oder eine
        # Entscheidung von Hand und überlebt (AP1).
        aus_muster = [s for s in vorhanden if s.source == "pattern"]
        verschont = [s for s in vorhanden if s.source != "pattern"]
        umzuhaengen = [
            AlterSlot(
                id=s.id,
                datum=s.date,
                start_period=s.start_period,
                periods=s.periods,
                kategorie=s.kategorie,
                pinned=s.pinned,
                ue_node_id=s.ue_node_id,
                stunde_node_id=s.stunde_node_id,
                thema=s.thema,
            )
            for s in aus_muster
        ]

    belegt = {(s.date, s.start_period) for s in verschont}

    raster = _raster(patterns, start, end, phasen, calendar, belegt)

    # Trug die alte Planung Inhalt, wird sie **umgehängt** statt weggeworfen: Inhalt
    # wandert nach Reihenfolge auf die neuen Termine (`app/planning/umhaengen.py`).
    # Bis zum 22.09.2026 löschte der Neuaufbau die Planung des Halbjahres mit.
    if umzuhaengen and any(a.hat_inhalt for a in umzuhaengen):
        plan = plane_umhaengen(
            umzuhaengen,
            [NeuerTermin(datum=d, start_period=sp, periods=pp) for d, sp, pp in raster],
        )
        created = await wende_umhaengen_an(
            db, group_id, halbjahr, plan, vorlaeufig=vorlaeufig, created_by=created_by
        )
        return SlotGenStats(
            created=created,
            halbjahr=halbjahr,
            used_hj1_fallback=used_hj1_fallback,
            fallback_vierzehntaegig=fallback_vierzehntaegig,
            vorlaeufig=vorlaeufig,
            verschont=len(verschont),
            umgehaengt=len(plan.zuordnungen),
            geparkt=len(plan.ueberhang),
            meldungen=plan.meldungen,
        )

    # Keine Planung zu retten: der bisherige Weg — Snapshot, löschen, neu erzeugen.
    if umzuhaengen:
        await create_snapshot(db, group_id, reason="regeneration", created_by=created_by)
        await db.execute(
            sa.delete(LessonSlot).where(LessonSlot.id.in_([a.id for a in umzuhaengen]))
        )
        await db.flush()

    created = 0
    for d, sp, pp in raster:
        db.add(
            LessonSlot(
                group_id=group_id,
                date=d,
                start_period=sp,
                periods=pp,
                halbjahr=halbjahr,
                kategorie="unterricht",
                vorlaeufig=vorlaeufig,
            )
        )
        created += 1

    await db.commit()
    return SlotGenStats(
        created=created,
        halbjahr=halbjahr,
        used_hj1_fallback=used_hj1_fallback,
        fallback_vierzehntaegig=fallback_vierzehntaegig,
        vorlaeufig=vorlaeufig,
        verschont=len(verschont),
    )
