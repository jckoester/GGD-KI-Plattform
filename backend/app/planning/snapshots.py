"""Snapshot-Service: Undo-Verlauf für den Unterrichtsplan.

create_snapshot: serialisiert alle Slots + Phasen-Arrays der verknüpften Stunden.
restore_snapshot: schreibt Zuordnungsfelder zurück (Redo-Snapshot wird vorab angelegt).
Pruning: max. 50 Snapshots pro Gruppe.
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import JwtPayload
from app.db.models import ContextNode, LessonSlot, SlotPlanSnapshot

SNAPSHOT_LIMIT = 50


async def create_snapshot(
    db: AsyncSession,
    group_id: int,
    *,
    reason: str,
    label: str | None = None,
    created_by: str | None = None,
) -> SlotPlanSnapshot:
    """Legt einen Snapshot aller Slots + Phasen-Status der Gruppe an."""
    slots_result = await db.execute(
        sa.select(LessonSlot).where(LessonSlot.group_id == group_id)
    )
    slots = slots_result.scalars().all()

    stunden_phasen: dict[str, list] = {}
    stunde_ids = [s.stunde_node_id for s in slots if s.stunde_node_id is not None]
    if stunde_ids:
        nodes_result = await db.execute(
            sa.select(ContextNode).where(ContextNode.id.in_(stunde_ids))
        )
        for node in nodes_result.scalars().all():
            phasen = (node.metadata_ or {}).get("phasen", [])
            if phasen:
                stunden_phasen[str(node.id)] = phasen

    payload = {
        "slots": [
            {
                "slot_id": str(s.id),
                "date": s.date.isoformat(),
                "kategorie": s.kategorie,
                "ue_node_id": str(s.ue_node_id) if s.ue_node_id else None,
                "stunde_node_id": str(s.stunde_node_id) if s.stunde_node_id else None,
                "thema": s.thema,
                "pinned": s.pinned,
                "anpassung_noetig": s.anpassung_noetig,
            }
            for s in slots
        ],
        "stunden_phasen": stunden_phasen,
    }

    snapshot = SlotPlanSnapshot(
        group_id=group_id,
        reason=reason,
        label=label,
        created_by=created_by,
        payload=payload,
    )
    db.add(snapshot)
    await db.flush()

    # Pruning: älteste Einträge über Limit löschen
    count_result = await db.scalar(
        sa.select(sa.func.count()).where(SlotPlanSnapshot.group_id == group_id)
    )
    if count_result and count_result > SNAPSHOT_LIMIT:
        oldest = await db.execute(
            sa.select(SlotPlanSnapshot.id)
            .where(SlotPlanSnapshot.group_id == group_id)
            .order_by(SlotPlanSnapshot.created_at.asc())
            .limit(count_result - SNAPSHOT_LIMIT)
        )
        ids_to_delete = [row[0] for row in oldest.all()]
        if ids_to_delete:
            await db.execute(
                sa.delete(SlotPlanSnapshot).where(SlotPlanSnapshot.id.in_(ids_to_delete))
            )

    await db.commit()
    await db.refresh(snapshot)
    return snapshot


async def restore_snapshot(
    db: AsyncSession,
    snapshot_id: UUID,
    user: JwtPayload,
) -> dict:
    """Stellt den Plan-Zustand eines Snapshots wieder her.

    Legt vorher einen 'restore'-Snapshot an (Redo-Fähigkeit).
    Slots die nicht mehr existieren (nach Regenerierung) werden übersprungen.
    """
    snapshot = await db.get(SlotPlanSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot nicht gefunden")

    await create_snapshot(
        db,
        snapshot.group_id,
        reason="restore",
        created_by=user.sub,
    )

    payload = snapshot.payload
    skipped: list[str] = []

    for slot_data in payload.get("slots", []):
        slot = await db.get(LessonSlot, slot_data["slot_id"])
        if slot is None:
            skipped.append(slot_data["slot_id"])
            continue
        slot.kategorie = slot_data["kategorie"]
        slot.ue_node_id = slot_data.get("ue_node_id")
        slot.stunde_node_id = slot_data.get("stunde_node_id")
        slot.thema = slot_data.get("thema")
        slot.pinned = slot_data.get("pinned", False)
        slot.anpassung_noetig = slot_data.get("anpassung_noetig", False)

    for node_id_str, phasen in payload.get("stunden_phasen", {}).items():
        try:
            nid = UUID(node_id_str)
        except ValueError:
            continue
        node = await db.get(ContextNode, nid)
        if node:
            meta = dict(node.metadata_ or {})
            meta["phasen"] = phasen
            node.metadata_ = meta

    await db.commit()
    return {"restored": True, "skipped_slot_ids": skipped}
