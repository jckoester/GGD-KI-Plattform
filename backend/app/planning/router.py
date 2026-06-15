"""CRUD-API für die Unterrichtsplanung.

Alle Endpoints erfordern Lehrkraft-Mitgliedschaft in der betroffenen teaching_group
(require_group_teacher). Kein Admin-Sonderfall — ohne Mitgliedschaft kein Zugriff.

Auto-Snapshot-Regel:
- PATCH Slot mit Zuordnungsfeldern (ue_node_id, stunde_node_id, thema, kategorie)
- POST swap, POST generate(regenerate), POST restore
lösen jeweils einen Snapshot aus.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_any_role
from app.auth.jwt import JwtPayload
from app.context.taxonomy import validate_content_type, validate_unterrichtsstunde_metadata
from app.db.models import (
    ContextEdge,
    ContextNode,
    GroupWeekPattern,
    LessonSlot,
    SlotPlanSnapshot,
)
from app.db.session import get_db
from app.planning.curriculum_resolver import resolve_group_curricula
from app.planning.permissions import require_group_teacher
from app.planning.schemas import (
    BalanceRead,
    CurriculumKapitelOption,
    CurriculumOption,
    FerienItem,
    SondertagItem,
    GroupCurriculaRead,
    LessonCreate,
    LessonNav,
    LessonRead,
    LessonSlotContext,
    LessonUeContext,
    LessonUpdate,
    OverviewRead,
    ReviewCreate,
    ReviewResultRead,
    ReviewStatusItem,
    SlotGenStatsRead,
    SlotGenerateRequest,
    SlotRead,
    SlotSwapRequest,
    SlotUpdate,
    SnapshotCreate,
    SnapshotRead,
    UnitBalanceItem,
    UnitCreate,
    UnitRead,
    WeekPatternRead,
    WeekPatternSet,
)
from app.planning.service import create_unit_node
from app.planning.snapshots import create_snapshot, restore_snapshot
from app.planning.slot_generator import generate_slots

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/planning", tags=["planning"])

_TEACHER_OR_ADMIN = require_any_role(["teacher", "admin"])

_SNAPSHOT_ASSIGNMENT_FIELDS = frozenset(
    {"ue_node_id", "stunde_node_id", "thema", "kategorie"}
)



async def _kapitel_std(db: AsyncSession, kapitel_node_id: UUID) -> int | None:
    """Gibt metadata.std eines Kapitel-Knotens zurück (None wenn nicht vorhanden)."""
    node = await db.get(ContextNode, kapitel_node_id)
    if node is None:
        return None
    return (node.metadata_ or {}).get("std")


async def _build_balance(
    db: AsyncSession,
    group_id: int,
    units: list[ContextNode],
    slots: list[LessonSlot],
) -> BalanceRead:
    total_slots = len(slots)
    assigned_slot_ids: set[UUID] = set()
    items: list[UnitBalanceItem] = []

    for ue_node in units:
        ue_slots = [s for s in slots if s.ue_node_id == ue_node.id]
        # Curriculum-Stunden sind Einzelstunden; ein Doppelstunden-Slot (periods=2)
        # zählt entsprechend als 2 Stunden. Daher Summe der periods, nicht Slot-Anzahl.
        zugewiesen = sum(s.periods for s in ue_slots)
        for s in ue_slots:
            assigned_slot_ids.add(s.id)

        soll_std: int | None = None
        kapitel_edge = await db.execute(
            sa.select(ContextEdge).where(
                ContextEdge.from_node_id == ue_node.id,
                ContextEdge.relation == "references",
            )
        )
        for edge in kapitel_edge.scalars().all():
            kapitel = await db.get(ContextNode, edge.to_node_id)
            if kapitel and kapitel.content_type == "kapitel":
                soll_std = (kapitel.metadata_ or {}).get("std")
                break

        puffer = 0
        if soll_std is not None:
            puffer = max(0, zugewiesen - soll_std)

        items.append(
            UnitBalanceItem(
                ue_node_id=ue_node.id,
                titel=ue_node.title,
                soll_std=soll_std,
                zugewiesen=zugewiesen,
                puffer=puffer,
            )
        )

    unzugewiesen = total_slots - len(assigned_slot_ids)
    return BalanceRead(items=items, total_slots=total_slots, unzugewiesen=unzugewiesen)


async def _load_units(db: AsyncSession, group_id: int) -> list[ContextNode]:
    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "unterrichtseinheit",
            ContextNode.write_scope == "group",
            ContextNode.write_scope_group_id == group_id,
            ContextNode.status == "active",
        ).order_by(ContextNode.created_at)
    )
    return result.scalars().all()


# ── GET /planning/groups/{group_id}/overview ──────────────────────────────────


@router.get("/groups/{group_id}/overview", response_model=OverviewRead)
async def get_overview(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    slots_result = await db.execute(
        sa.select(LessonSlot)
        .where(LessonSlot.group_id == group_id)
        .order_by(LessonSlot.date, LessonSlot.start_period)
    )
    slots = slots_result.scalars().all()

    patterns_result = await db.execute(
        sa.select(GroupWeekPattern)
        .where(GroupWeekPattern.group_id == group_id)
        .order_by(GroupWeekPattern.halbjahr, GroupWeekPattern.weekday, GroupWeekPattern.start_period)
    )
    patterns = patterns_result.scalars().all()

    units = await _load_units(db, group_id)
    balance = await _build_balance(db, group_id, units, slots)

    unit_reads = []
    for ue in units:
        kapitel_std = None
        kapitel_edge = await db.execute(
            sa.select(ContextEdge).where(
                ContextEdge.from_node_id == ue.id,
                ContextEdge.relation == "references",
            )
        )
        for edge in kapitel_edge.scalars().all():
            kap = await db.get(ContextNode, edge.to_node_id)
            if kap and kap.content_type == "kapitel":
                kapitel_std = (kap.metadata_ or {}).get("std")
                break
        unit_reads.append(
            UnitRead(
                id=ue.id,
                title=ue.title,
                metadata_=ue.metadata_ or {},
                kapitel_std=kapitel_std,
            )
        )

    from app.planning.calendar import load_school_year
    cfg = load_school_year()

    return OverviewRead(
        slots=[SlotRead.model_validate(s) for s in slots],
        patterns=[WeekPatternRead.model_validate(p) for p in patterns],
        units=unit_reads,
        balance=balance,
        schuljahr=cfg.schuljahr,
        beginn=cfg.beginn,
        ende=cfg.ende,
        halbjahreswechsel=cfg.halbjahreswechsel,
        ferien=[FerienItem(name=f.name, von=f.von, bis=f.bis) for f in cfg.ferien],
        feiertage=[SondertagItem(name=t.name, datum=t.datum) for t in cfg.feiertage],
        unterrichtsfreie_tage=[
            SondertagItem(name=t.name, datum=t.datum) for t in cfg.unterrichtsfreie_tage
        ],
    )


# ── PUT /planning/groups/{group_id}/pattern ───────────────────────────────────


@router.put("/groups/{group_id}/pattern", response_model=list[WeekPatternRead])
async def set_week_pattern(
    group_id: int,
    payload: WeekPatternSet,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    await db.execute(
        sa.delete(GroupWeekPattern).where(
            GroupWeekPattern.group_id == group_id,
            GroupWeekPattern.halbjahr == payload.halbjahr,
        )
    )
    new_patterns = []
    for item in payload.patterns:
        p = GroupWeekPattern(
            group_id=group_id,
            halbjahr=payload.halbjahr,
            weekday=item.weekday,
            start_period=item.start_period,
            periods=item.periods,
        )
        db.add(p)
        new_patterns.append(p)

    await db.commit()
    for p in new_patterns:
        await db.refresh(p)
    return new_patterns


# ── POST /planning/groups/{group_id}/slots/generate ───────────────────────────


@router.post("/groups/{group_id}/slots/generate", response_model=SlotGenStatsRead)
async def generate_group_slots(
    group_id: int,
    payload: SlotGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    stats = await generate_slots(
        db,
        group_id,
        payload.halbjahr,
        regenerate=payload.regenerate,
        created_by=user.sub,
    )
    return SlotGenStatsRead(
        created=stats.created,
        halbjahr=stats.halbjahr,
        used_hj1_fallback=stats.used_hj1_fallback,
    )


# ── PATCH /planning/slots/{slot_id} ──────────────────────────────────────────


@router.patch("/slots/{slot_id}", response_model=SlotRead)
async def update_slot(
    slot_id: UUID,
    payload: SlotUpdate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    slot = await db.get(LessonSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot nicht gefunden")

    await require_group_teacher(slot.group_id, user, db)

    update_data = payload.model_dump(exclude_unset=True)

    changes_assignment = bool(_SNAPSHOT_ASSIGNMENT_FIELDS & update_data.keys())
    if changes_assignment:
        await create_snapshot(
            db, slot.group_id, reason="edit", created_by=user.sub
        )

    if "kategorie" in update_data:
        valid_kategorien = {"unterricht", "pruefung", "ausfall", "puffer", "vertretung"}
        if update_data["kategorie"] not in valid_kategorien:
            raise HTTPException(
                status_code=422,
                detail=f"Ungültige Kategorie. Erlaubt: {sorted(valid_kategorien)}",
            )

    for field, value in update_data.items():
        setattr(slot, field, value)

    slot.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(slot)
    return slot


# ── POST /planning/groups/{group_id}/slots/swap ───────────────────────────────


@router.post("/groups/{group_id}/slots/swap", response_model=list[SlotRead])
async def swap_slots(
    group_id: int,
    payload: SlotSwapRequest,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    slot_a = await db.get(LessonSlot, payload.slot_a_id)
    slot_b = await db.get(LessonSlot, payload.slot_b_id)

    if slot_a is None or slot_b is None:
        raise HTTPException(status_code=404, detail="Slot nicht gefunden")
    if slot_a.group_id != group_id or slot_b.group_id != group_id:
        raise HTTPException(status_code=403, detail="Slot gehört nicht zur Gruppe")

    await create_snapshot(db, group_id, reason="swap", created_by=user.sub)

    now = datetime.now(timezone.utc)
    slot_a.ue_node_id, slot_b.ue_node_id = slot_b.ue_node_id, slot_a.ue_node_id
    slot_a.stunde_node_id, slot_b.stunde_node_id = slot_b.stunde_node_id, slot_a.stunde_node_id
    slot_a.thema, slot_b.thema = slot_b.thema, slot_a.thema
    slot_a.updated_at = now
    slot_b.updated_at = now

    await db.commit()
    await db.refresh(slot_a)
    await db.refresh(slot_b)
    return [slot_a, slot_b]


# ── POST /planning/groups/{group_id}/units ────────────────────────────────────


@router.post("/groups/{group_id}/units", response_model=UnitRead, status_code=201)
async def create_unit(
    group_id: int,
    payload: UnitCreate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    group = await require_group_teacher(group_id, user, db)

    ue_node = await create_unit_node(
        db=db,
        group_id=group_id,
        group_subject_id=group.subject_id,
        user=user,
        titel=payload.titel,
        farbe=payload.farbe,
        kapitel_node_id=payload.kapitel_node_id,
    )

    kapitel_std = None
    if payload.kapitel_node_id:
        kapitel_std = await _kapitel_std(db, payload.kapitel_node_id)

    return UnitRead(
        id=ue_node.id,
        title=ue_node.title,
        metadata_=ue_node.metadata_ or {},
        kapitel_std=kapitel_std,
    )


# ── GET /planning/groups/{group_id}/units ────────────────────────────────────


@router.get("/groups/{group_id}/units", response_model=list[UnitRead])
async def list_units(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    units = await _load_units(db, group_id)
    result = []
    for ue in units:
        kapitel_std = None
        edge_result = await db.execute(
            sa.select(ContextEdge).where(
                ContextEdge.from_node_id == ue.id,
                ContextEdge.relation == "references",
            )
        )
        for edge in edge_result.scalars().all():
            kap = await db.get(ContextNode, edge.to_node_id)
            if kap and kap.content_type == "kapitel":
                kapitel_std = (kap.metadata_ or {}).get("std")
                break
        result.append(
            UnitRead(
                id=ue.id,
                title=ue.title,
                metadata_=ue.metadata_ or {},
                kapitel_std=kapitel_std,
            )
        )
    return result


# ── GET /planning/groups/{group_id}/curriculum-chapters ───────────────────────


@router.get(
    "/groups/{group_id}/curriculum-chapters",
    response_model=GroupCurriculaRead,
)
async def get_group_curriculum_chapters(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Zur Gruppe passende Curricula mit Kapiteln (Quelle für den UE-Picker)."""
    await require_group_teacher(group_id, user, db)

    resolved = await resolve_group_curricula(db, group_id)
    return GroupCurriculaRead(
        curricula=[
            CurriculumOption(
                curriculum_id=cur.curriculum_id,
                titel=cur.titel,
                jahrgangsstufe=cur.jahrgangsstufe,
                kapitel=[
                    CurriculumKapitelOption(
                        id=k.id,
                        titel=k.titel,
                        std=k.std,
                        reihenfolge=k.reihenfolge,
                        ues=k.ues,
                    )
                    for k in cur.kapitel
                ],
            )
            for cur in resolved.curricula
        ],
        grade=resolved.grade,
        grade_unbekannt=resolved.grade_unbekannt,
    )


# ── POST /planning/units/{node_id}/lessons ────────────────────────────────────


@router.post("/units/{node_id}/lessons", response_model=dict, status_code=201)
async def create_lesson(
    node_id: UUID,
    payload: LessonCreate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    ue_node = await db.get(ContextNode, node_id)
    if ue_node is None or ue_node.status != "active":
        raise HTTPException(status_code=404, detail="Unterrichtseinheit nicht gefunden")
    if ue_node.content_type != "unterrichtseinheit":
        raise HTTPException(status_code=422, detail="Knoten ist keine Unterrichtseinheit")

    group_id = ue_node.write_scope_group_id
    if group_id is None:
        raise HTTPException(status_code=422, detail="UE hat keine Gruppe")

    await require_group_teacher(group_id, user, db)

    if payload.slot_id:
        slot = await db.get(LessonSlot, payload.slot_id)
        if slot is None:
            raise HTTPException(status_code=404, detail="Slot nicht gefunden")
        if slot.group_id != group_id:
            raise HTTPException(status_code=403, detail="Slot gehört nicht zur Gruppe")

    # Vorgängerstunde für follows-Kante ermitteln
    last_lesson = await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(
            ContextEdge.to_node_id == node_id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "unterrichtsstunde",
            ContextNode.status == "active",
        )
        .order_by(ContextNode.created_at.desc())
        .limit(1)
    )
    predecessor = last_lesson.scalar_one_or_none()

    stunde = ContextNode(
        category="artifact",
        content_type="unterrichtsstunde",
        title=payload.titel,
        read_scope="group",
        write_scope="group",
        read_scope_group_id=group_id,
        write_scope_group_id=group_id,
        owner_pseudonym=user.sub,
        subject_id=ue_node.subject_id,
        metadata_={"phasen": []},
        status="active",
    )
    db.add(stunde)
    await db.flush()

    db.add(ContextEdge(
        from_node_id=stunde.id,
        to_node_id=node_id,
        relation="part_of",
        metadata_={},
    ))

    if predecessor:
        db.add(ContextEdge(
            from_node_id=stunde.id,
            to_node_id=predecessor.id,
            relation="follows",
            metadata_={},
        ))

    if payload.slot_id:
        slot = await db.get(LessonSlot, payload.slot_id)
        if slot:
            await create_snapshot(db, group_id, reason="edit", created_by=user.sub)
            slot.stunde_node_id = stunde.id
            slot.ue_node_id = ue_node.id
            slot.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(stunde)
    return {"id": str(stunde.id), "title": stunde.title}


# ── GET /planning/groups/{group_id}/balance ───────────────────────────────────


@router.get("/groups/{group_id}/balance", response_model=BalanceRead)
async def get_balance(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    slots_result = await db.execute(
        sa.select(LessonSlot).where(LessonSlot.group_id == group_id)
    )
    slots = slots_result.scalars().all()

    units = await _load_units(db, group_id)
    return await _build_balance(db, group_id, units, slots)


# ── POST /planning/groups/{group_id}/snapshots ────────────────────────────────


@router.post(
    "/groups/{group_id}/snapshots", response_model=SnapshotRead, status_code=201
)
async def create_manual_snapshot(
    group_id: int,
    payload: SnapshotCreate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    snapshot = await create_snapshot(
        db,
        group_id,
        reason="manual",
        label=payload.label,
        created_by=user.sub,
    )
    return snapshot


# ── GET /planning/groups/{group_id}/snapshots ─────────────────────────────────


@router.get("/groups/{group_id}/snapshots", response_model=list[SnapshotRead])
async def list_snapshots(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    result = await db.execute(
        sa.select(SlotPlanSnapshot)
        .where(SlotPlanSnapshot.group_id == group_id)
        .order_by(SlotPlanSnapshot.created_at.desc())
    )
    return result.scalars().all()


# ── POST /planning/snapshots/{snapshot_id}/restore ───────────────────────────


@router.post("/snapshots/{snapshot_id}/restore", response_model=dict)
async def restore_snapshot_endpoint(
    snapshot_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    snapshot = await db.get(SlotPlanSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot nicht gefunden")

    await require_group_teacher(snapshot.group_id, user, db)

    return await restore_snapshot(db, snapshot_id, user)


# ── Hilfsfunktion: Navigations-Reihenfolge innerhalb einer UE ─────────────────


async def _build_lesson_nav(
    db: AsyncSession,
    node_id: UUID,
    unit_id: UUID | None,
) -> LessonNav:
    if unit_id is None:
        return LessonNav(prev_node_id=None, next_node_id=None, position=1, total=1)

    lessons_result = await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(
            ContextEdge.to_node_id == unit_id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "unterrichtsstunde",
            ContextNode.status == "active",
        )
    )
    all_lessons = {n.id: n for n in lessons_result.scalars().all()}

    if not all_lessons:
        return LessonNav(prev_node_id=None, next_node_id=None, position=1, total=1)

    follows_result = await db.execute(
        sa.select(ContextEdge).where(
            ContextEdge.from_node_id.in_(list(all_lessons.keys())),
            ContextEdge.relation == "follows",
        )
    )
    # follows[a] = b: lesson a follows lesson b (b is predecessor of a)
    follows = {e.from_node_id: e.to_node_id for e in follows_result.scalars().all()}

    # Build ordered list: first lesson has no outgoing follows edge
    first_candidates = set(all_lessons.keys()) - set(follows.keys())
    if not first_candidates:
        ordered = [n.id for n in sorted(all_lessons.values(), key=lambda n: n.created_at)]
    else:
        current = next(iter(first_candidates))
        ordered = [current]
        reverse_follows = {v: k for k, v in follows.items()}
        visited = {current}
        while current in reverse_follows and reverse_follows[current] not in visited:
            current = reverse_follows[current]
            ordered.append(current)
            visited.add(current)

    total = len(ordered)
    try:
        pos = ordered.index(node_id) + 1
    except ValueError:
        pos = total

    return LessonNav(
        prev_node_id=ordered[pos - 2] if pos > 1 else None,
        next_node_id=ordered[pos] if pos < total else None,
        position=pos,
        total=total,
    )


# ── GET /planning/lessons/{node_id} ──────────────────────────────────────────


@router.get("/lessons/{node_id}", response_model=LessonRead)
async def get_lesson(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    lesson = await db.get(ContextNode, node_id)
    if lesson is None or lesson.status != "active" or lesson.content_type != "unterrichtsstunde":
        raise HTTPException(status_code=404, detail="Stunde nicht gefunden")

    group_id = lesson.write_scope_group_id
    if group_id is None:
        raise HTTPException(status_code=422, detail="Stunde hat keine Gruppe")
    await require_group_teacher(group_id, user, db)

    # Übergeordnete UE
    ue_edge_result = await db.execute(
        sa.select(ContextEdge).where(
            ContextEdge.from_node_id == node_id,
            ContextEdge.relation == "part_of",
        )
    )
    ue_edge = ue_edge_result.scalar_one_or_none()
    ue_ctx: LessonUeContext | None = None
    unit_id: UUID | None = None
    if ue_edge:
        unit_id = ue_edge.to_node_id
        ue_node = await db.get(ContextNode, unit_id)
        if ue_node:
            ue_ctx = LessonUeContext(
                id=ue_node.id,
                titel=ue_node.title,
                farbe=(ue_node.metadata_ or {}).get("farbe", 0),
            )

    # Slot-Kontext
    slot_result = await db.execute(
        sa.select(LessonSlot).where(LessonSlot.stunde_node_id == node_id)
    )
    slot = slot_result.scalar_one_or_none()
    slot_ctx: LessonSlotContext | None = None
    if slot:
        slot_ctx = LessonSlotContext(
            id=slot.id,
            date=slot.date,
            start_period=slot.start_period,
            periods=slot.periods,
            verfuegbare_min=slot.periods * 45,
        )

    nav = await _build_lesson_nav(db, node_id, unit_id)
    meta = lesson.metadata_ or {}

    return LessonRead(
        id=lesson.id,
        titel=lesson.title,
        stundenziel=meta.get("stundenziel"),
        phasen=meta.get("phasen", []),
        refs=meta.get("refs", []),
        refs_dismissed=[str(x) for x in meta.get("refs_dismissed", [])],
        ue=ue_ctx,
        slot=slot_ctx,
        nav=nav,
        group_id=group_id,
        subject_id=lesson.subject_id,
    )


# ── PATCH /planning/lessons/{node_id} ────────────────────────────────────────


@router.patch("/lessons/{node_id}", response_model=dict)
async def patch_lesson(
    node_id: UUID,
    payload: LessonUpdate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    lesson = await db.get(ContextNode, node_id)
    if lesson is None or lesson.status != "active" or lesson.content_type != "unterrichtsstunde":
        raise HTTPException(status_code=404, detail="Stunde nicht gefunden")

    group_id = lesson.write_scope_group_id
    if group_id is None:
        raise HTTPException(status_code=422, detail="Stunde hat keine Gruppe")
    await require_group_teacher(group_id, user, db)

    if payload.phasen is not None:
        for phase in payload.phasen:
            try:
                phase.validate_prio()
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))

    await create_snapshot(db, group_id, reason="edit", created_by=user.sub)

    now = datetime.now(timezone.utc)
    if payload.titel is not None:
        lesson.title = payload.titel

    meta = dict(lesson.metadata_ or {})
    if payload.stundenziel is not None:
        meta["stundenziel"] = payload.stundenziel
    if payload.phasen is not None:
        meta["phasen"] = [
            p.model_dump(exclude_none=False, mode="json") for p in payload.phasen
        ]
    if payload.refs is not None:
        meta["refs"] = [r.model_dump(mode="json") for r in payload.refs]
    if payload.refs_dismissed is not None:
        meta["refs_dismissed"] = [str(rid) for rid in payload.refs_dismissed]

    lesson.metadata_ = meta
    lesson.updated_at = now
    await db.commit()

    return {"ok": True}


# ── POST /planning/slots/{slot_id}/review ────────────────────────────────────


@router.post("/slots/{slot_id}/review", response_model=ReviewResultRead, status_code=200)
async def create_review(
    slot_id: UUID,
    payload: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    slot = await db.get(LessonSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot nicht gefunden")
    await require_group_teacher(slot.group_id, user, db)
    if slot.stunde_node_id is None:
        raise HTTPException(status_code=409, detail="Slot hat keine Stunde")
    if slot.nachbereitet_at is not None:
        raise HTTPException(status_code=409, detail="Slot bereits nachbereitet")

    from app.planning.review_service import complete_review

    try:
        result = await complete_review(
            db,
            slot_id,
            group_id=slot.group_id,
            phasen_status=payload.phasen_status,
            reflexion=payload.reflexion,
            refs_offen=payload.refs_offen,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return ReviewResultRead(
        engagements_written=result.engagements_written,
        engagements_skipped=result.engagements_skipped,
        refs_offen=result.refs_offen,
        open_phases=result.open_phases,
    )


# ── DELETE /planning/slots/{slot_id}/review ───────────────────────────────────


@router.delete("/slots/{slot_id}/review", response_model=dict)
async def undo_review_endpoint(
    slot_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    slot = await db.get(LessonSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot nicht gefunden")
    await require_group_teacher(slot.group_id, user, db)
    if slot.nachbereitet_at is None:
        raise HTTPException(status_code=409, detail="Slot ist nicht nachbereitet")

    from app.planning.review_service import undo_review

    deleted = await undo_review(db, slot_id, group_id=slot.group_id)
    return {"ok": True, "deleted_engagements": deleted}


# ── GET /planning/groups/{group_id}/review-status ────────────────────────────


@router.get("/groups/{group_id}/review-status", response_model=list[ReviewStatusItem])
async def get_review_status(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Vergangene Slots mit Stunde, die noch nicht nachbereitet wurden."""
    await require_group_teacher(group_id, user, db)

    from datetime import date as date_type
    today = date_type.today()

    result = await db.execute(
        sa.select(LessonSlot).where(
            LessonSlot.group_id == group_id,
            LessonSlot.stunde_node_id.is_not(None),
            LessonSlot.kategorie.in_(["unterricht", "vertretung"]),
            LessonSlot.date < today,
        ).order_by(LessonSlot.date.desc())
    )
    slots = result.scalars().all()

    items: list[ReviewStatusItem] = []
    for slot in slots:
        stunde = await db.get(ContextNode, slot.stunde_node_id)
        items.append(
            ReviewStatusItem(
                slot_id=slot.id,
                date=slot.date,
                stunde_node_id=slot.stunde_node_id,
                titel=stunde.title if stunde else None,
                nachbereitet_auto=slot.nachbereitet_auto,
            )
        )
    return items


# ── GET /planning/lessons/{node_id}/export ────────────────────────────────────


@router.get("/lessons/{node_id}/export")
async def export_lesson(
    node_id: UUID,
    format: str = "md",  # md | pdf | docx
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    from fastapi.responses import Response

    lesson = await db.get(ContextNode, node_id)
    if lesson is None or lesson.status != "active" or lesson.content_type != "unterrichtsstunde":
        raise HTTPException(status_code=404, detail="Stunde nicht gefunden")

    group_id = lesson.write_scope_group_id
    if group_id is None:
        raise HTTPException(status_code=422, detail="Stunde hat keine Gruppe")
    await require_group_teacher(group_id, user, db)

    from app.planning.lesson_export import build_lesson_export, export_docx, export_markdown, export_pdf

    data = await build_lesson_export(db, node_id)

    if format == "md":
        content = export_markdown(data)
        filename = f"{data.datum}-{data.gruppe_slug}-{data.titel_slug}.md"
        return Response(
            content=content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    elif format == "pdf":
        content = await export_pdf(data)
        filename = f"{data.datum}-{data.gruppe_slug}-{data.titel_slug}.pdf"
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    elif format == "docx":
        content = export_docx(data)
        filename = f"{data.datum}-{data.gruppe_slug}-{data.titel_slug}.docx"
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    else:
        raise HTTPException(status_code=422, detail=f"Unbekanntes Format: {format}")
