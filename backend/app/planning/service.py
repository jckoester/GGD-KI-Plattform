"""Wiederverwendbare Planungs-Logik, geteilt von Router und Assistent-Tools."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import JwtPayload
from app.db.models import ContextEdge, ContextNode, LessonSlot
from app.planning.snapshots import create_snapshot


async def _get_or_create_jahresplan(
    db: AsyncSession,
    group_id: int,
    group_subject_id: int | None,
    user: JwtPayload,
) -> ContextNode:
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


async def create_unit_node(
    db: AsyncSession,
    group_id: int,
    group_subject_id: int | None,
    user: JwtPayload,
    titel: str,
    farbe: int | None = None,
    kapitel_node_id: UUID | None = None,
) -> ContextNode:
    """Legt eine Unterrichtseinheit an und gibt den ContextNode zurück (committed)."""
    from app.planning.calendar import load_school_year

    cfg = load_school_year()
    jahresplan = await _get_or_create_jahresplan(db, group_id, group_subject_id, user)

    meta: dict = {"schuljahr": cfg.schuljahr}
    if farbe is not None:
        meta["farbe"] = farbe

    ue_node = ContextNode(
        category="artifact",
        content_type="unterrichtseinheit",
        title=titel,
        read_scope="group",
        write_scope="group",
        read_scope_group_id=group_id,
        write_scope_group_id=group_id,
        owner_pseudonym=user.sub,
        subject_id=group_subject_id,
        metadata_=meta,
        status="active",
    )
    db.add(ue_node)
    await db.flush()

    db.add(
        ContextEdge(
            from_node_id=ue_node.id,
            to_node_id=jahresplan.id,
            relation="part_of",
            metadata_={},
        )
    )

    if kapitel_node_id:
        db.add(
            ContextEdge(
                from_node_id=ue_node.id,
                to_node_id=kapitel_node_id,
                relation="references",
                metadata_={},
            )
        )

    await db.commit()
    await db.refresh(ue_node)
    return ue_node


async def assign_slots_to_unit(
    db: AsyncSession,
    group_id: int,
    user: JwtPayload,
    unit_node_id: UUID,
    slot_ids: list[UUID],
) -> list[LessonSlot]:
    """Setzt ue_node_id auf allen angegebenen Slots (eine Transaktion, ein Snapshot)."""
    # Snapshot vor Änderung
    await create_snapshot(db, group_id, reason="assistant", created_by=user.sub)

    now = datetime.now(timezone.utc)
    updated = []
    for slot_id in slot_ids:
        slot = await db.get(LessonSlot, slot_id)
        if slot is None or slot.group_id != group_id:
            continue
        slot.ue_node_id = unit_node_id
        slot.updated_at = now
        updated.append(slot)

    await db.commit()
    for s in updated:
        await db.refresh(s)
    return updated


async def set_slot_topics(
    db: AsyncSession,
    group_id: int,
    user: JwtPayload,
    items: list[dict],
) -> list[LessonSlot]:
    """Setzt thema auf mehreren Slots (Bulk; ein Snapshot)."""
    await create_snapshot(db, group_id, reason="assistant", created_by=user.sub)

    now = datetime.now(timezone.utc)
    updated = []
    for item in items:
        slot_id = item.get("slot_id")
        thema = item.get("thema")
        if not slot_id:
            continue
        slot = await db.get(LessonSlot, slot_id)
        if slot is None or slot.group_id != group_id:
            continue
        slot.thema = thema
        slot.updated_at = now
        updated.append(slot)

    await db.commit()
    for s in updated:
        await db.refresh(s)
    return updated


async def set_slot_category(
    db: AsyncSession,
    group_id: int,
    user: JwtPayload,
    slot_id: UUID,
    kategorie: str,
) -> LessonSlot:
    """Setzt die Kategorie eines einzelnen Slots (ein Snapshot)."""
    valid = {"unterricht", "pruefung", "ausfall", "puffer", "vertretung"}
    if kategorie not in valid:
        raise ValueError(f"Ungültige Kategorie: {kategorie}")

    slot = await db.get(LessonSlot, slot_id)
    if slot is None or slot.group_id != group_id:
        raise ValueError(f"Slot {slot_id} nicht in Gruppe {group_id}")

    await create_snapshot(db, group_id, reason="assistant", created_by=user.sub)

    slot.kategorie = kategorie
    slot.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(slot)
    return slot
