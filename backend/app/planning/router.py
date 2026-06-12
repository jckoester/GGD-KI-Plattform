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
from app.planning.permissions import require_group_teacher
from app.planning.schemas import (
    BalanceRead,
    LessonCreate,
    OverviewRead,
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
from app.planning.snapshots import create_snapshot, restore_snapshot
from app.planning.slot_generator import generate_slots

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/planning", tags=["planning"])

_TEACHER_OR_ADMIN = require_any_role(["teacher", "admin"])

_SNAPSHOT_ASSIGNMENT_FIELDS = frozenset(
    {"ue_node_id", "stunde_node_id", "thema", "kategorie"}
)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_or_create_jahresplan(
    db: AsyncSession,
    group_id: int,
    group_subject_id: int | None,
    user: JwtPayload,
) -> ContextNode:
    """Lazy: Jahresplan-Knoten pro Gruppe×Schuljahr, wird bei Bedarf erzeugt."""
    from app.planning.calendar import load_school_year

    cfg = load_school_year()
    schuljahr = cfg.schuljahr

    existing = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "jahresplan",
            ContextNode.write_scope == "group",
            ContextNode.write_scope_group_id == group_id,
            ContextNode.metadata_["schuljahr"].astext == schuljahr,
            ContextNode.status == "active",
        )
    )
    node = existing.scalar_one_or_none()
    if node:
        return node

    node = ContextNode(
        category="knowledge",
        content_type="jahresplan",
        title=f"Jahresplan {schuljahr}",
        read_scope="group",
        write_scope="group",
        read_scope_group_id=group_id,
        write_scope_group_id=group_id,
        owner_pseudonym=user.sub,
        subject_id=group_subject_id,
        metadata_={"schuljahr": schuljahr},
        status="active",
    )
    db.add(node)
    await db.flush()
    return node


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
        zugewiesen = len(ue_slots)
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
        halbjahreswechsel=cfg.halbjahreswechsel,
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

    from app.planning.calendar import load_school_year
    cfg = load_school_year()

    jahresplan = await _get_or_create_jahresplan(
        db, group_id, group.subject_id, user
    )

    meta: dict = {"schuljahr": cfg.schuljahr}
    if payload.farbe is not None:
        meta["farbe"] = payload.farbe

    ue_node = ContextNode(
        category="artifact",
        content_type="unterrichtseinheit",
        title=payload.titel,
        read_scope="group",
        write_scope="group",
        read_scope_group_id=group_id,
        write_scope_group_id=group_id,
        owner_pseudonym=user.sub,
        subject_id=group.subject_id,
        metadata_=meta,
        status="active",
    )
    db.add(ue_node)
    await db.flush()

    part_of_edge = ContextEdge(
        from_node_id=ue_node.id,
        to_node_id=jahresplan.id,
        relation="part_of",
        metadata_={},
    )
    db.add(part_of_edge)

    if payload.kapitel_node_id:
        ref_edge = ContextEdge(
            from_node_id=ue_node.id,
            to_node_id=payload.kapitel_node_id,
            relation="references",
            metadata_={},
        )
        db.add(ref_edge)

    await db.commit()
    await db.refresh(ue_node)

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
