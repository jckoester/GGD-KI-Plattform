"""Snapshot-Service: Undo-Verlauf für den Unterrichtsplan.

create_snapshot: serialisiert alle Slots und von jeder verknüpften Stunde Titel,
Stundenziel, Phasen, `refs` und `refs_offen`.
restore_snapshot: schreibt Zuordnungsfelder zurück (Redo-Snapshot wird vorab angelegt).
Pruning: max. 50 Snapshots pro Gruppe.
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import JwtPayload
from app.context.embedding import eingabe_ohne_aliase, enqueue_embedding_job, vektor_veraltet
from app.db.models import ContextNode, LessonSlot, SlotPlanSnapshot
from app.planning.ausfall import setze_kategorie
from app.planning.einordnung import ordne_entwurf_ein
from app.planning.material_edges import synchronisiere_materialkanten

SNAPSHOT_LIMIT = 50


async def create_snapshot(
    db: AsyncSession,
    group_id: int,
    *,
    reason: str,
    label: str | None = None,
    created_by: str | None = None,
) -> SlotPlanSnapshot:
    """Legt einen Snapshot aller Slots und der Entwürfe ihrer Stunden an."""
    slots_result = await db.execute(
        sa.select(LessonSlot).where(LessonSlot.group_id == group_id)
    )
    slots = slots_result.scalars().all()

    # ⚠️ **Jede verknüpfte Stunde, auch eine leere** (0.17). Bis dahin stand hier nur
    # `stunden_phasen`, und nur für Stunden mit Phasen: „Rückgängig" nahm weder `refs` noch
    # Titel oder Stundenziel zurück — schrieb der Assistent Kompetenzen oder Begriffe, blieben
    # sie —, und Phasen, die eine bis dahin leere Stunde bekommen hatte, ebenso wenig. Ein
    # leerer Stand muss mit, sonst ist „war leer" nicht von „nicht erfasst" zu unterscheiden.
    stunden: dict[str, dict] = {}
    stunde_ids = [s.stunde_node_id for s in slots if s.stunde_node_id is not None]
    if stunde_ids:
        nodes_result = await db.execute(
            sa.select(ContextNode).where(ContextNode.id.in_(stunde_ids))
        )
        for node in nodes_result.scalars().all():
            meta = node.metadata_ or {}
            stunden[str(node.id)] = {
                "titel": node.title,
                "stundenziel": meta.get("stundenziel"),
                "phasen": meta.get("phasen", []),
                "refs": meta.get("refs", []),
                # Eine Übertragung leert sie in der Quelle und trägt sie als `refs` ins Ziel —
                # ohne sie hier stünde nach „Rückgängig" nichts mehr als offen da.
                "refs_offen": meta.get("refs_offen", []),
            }

    payload = {
        "slots": [
            {
                "slot_id": str(s.id),
                "date": s.date.isoformat(),
                "kategorie": s.kategorie,
                # Seit 0.15: Herkunft und Vorher gehören zur Kategorie (`ausfall.setze_kategorie`).
                "ausfall_herkunft": s.ausfall_herkunft,
                "ausfall_vorher": s.ausfall_vorher,
                "ue_node_id": str(s.ue_node_id) if s.ue_node_id else None,
                "stunde_node_id": str(s.stunde_node_id) if s.stunde_node_id else None,
                "thema": s.thema,
                "pinned": s.pinned,
                "anpassung_noetig": s.anpassung_noetig,
            }
            for s in slots
        ],
        "stunden": stunden,
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
        # Als Zeichenketten vergleichen: Im Snapshot stehen sie so, am Slot als UUID.
        vorher = tuple(str(x) if x else None for x in (slot.ue_node_id, slot.stunde_node_id))
        # ⚠️ **Kategorie, Herkunft und Vorher zusammen** (0.15). Bis dahin setzte der Restore
        # nur die Kategorie: Nach „Rückgängig" auf einen Ausfall des Assistenten stand der
        # Termin wieder auf `unterricht`, trug aber noch `ausfall_herkunft` — genau die
        # Inkonsistenz, vor der `setze_kategorie` warnt; umgekehrt verlor ein wiederhergestellter
        # Ausfall seine Herkunft und war für den Stundenplan-Abgleich ungeschützt.
        if "ausfall_herkunft" in slot_data:
            slot.kategorie = slot_data["kategorie"]
            slot.ausfall_herkunft = slot_data["ausfall_herkunft"]
            slot.ausfall_vorher = slot_data.get("ausfall_vorher")
        elif slot_data["kategorie"] != slot.kategorie:
            # Ältere Snapshots kennen beides nicht. Zurück aus dem Ausfall leert
            # `setze_kategorie` die Felder; zurück in den Ausfall bekommt er die Herkunft
            # `eigen` — „Rückgängig" ist eine Handlung der Lehrkraft, kein Abgleich.
            setze_kategorie(slot, slot_data["kategorie"], herkunft="eigen")
        slot.ue_node_id = slot_data.get("ue_node_id")
        slot.stunde_node_id = slot_data.get("stunde_node_id")
        if tuple(str(x) if x else None for x in (slot.ue_node_id, slot.stunde_node_id)) != vorher:
            await ordne_entwurf_ein(db, slot)
        slot.thema = slot_data.get("thema")
        slot.pinned = slot_data.get("pinned", False)
        slot.anpassung_noetig = slot_data.get("anpassung_noetig", False)

    # Termine, die es beim Snapshot noch nicht gab (etwa die zweite Hälfte einer geteilten
    # Doppelstunde), bleiben unberührt — und könnten einen Entwurf tragen, den der Snapshot
    # wieder an seinen alten Termin hängt. Ein Entwurf gehört an höchstens einen Termin
    # (0087): Der Snapshot gewinnt, der neuere Termin wird gelöst.
    zurueck = {d["stunde_node_id"] for d in payload.get("slots", []) if d.get("stunde_node_id")}
    if zurueck:
        await db.execute(
            sa.update(LessonSlot)
            .where(
                LessonSlot.group_id == snapshot.group_id,
                LessonSlot.stunde_node_id.in_([UUID(s) for s in zurueck]),
                LessonSlot.id.not_in([UUID(d["slot_id"]) for d in payload.get("slots", [])]),
            )
            .values(stunde_node_id=None, updated_at=sa.func.now())
            .execution_options(synchronize_session=False)
        )

    stunden = payload.get("stunden")
    if stunden is None:
        # Snapshots vor 0.17 kennen nur die Phasen — der Rest der Stunde bleibt, wie er ist.
        stunden = {nid: {"phasen": phasen} for nid, phasen in payload.get("stunden_phasen", {}).items()}
    neu_einbetten: list[UUID] = []
    for node_id_str, stand in stunden.items():
        try:
            nid = UUID(node_id_str)
        except ValueError:
            continue
        node = await db.get(ContextNode, nid)
        if node is None or node.content_type != "unterrichtsstunde":
            continue
        vektor_vorher = eingabe_ohne_aliase(node)
        meta = dict(node.metadata_ or {})
        for feld in ("phasen", "refs", "refs_offen"):
            if feld in stand:
                meta[feld] = stand[feld]
        if "stundenziel" in stand:
            if stand["stundenziel"] is None:
                meta.pop("stundenziel", None)
            else:
                meta["stundenziel"] = stand["stundenziel"]
        if stand.get("titel"):
            node.title = stand["titel"]
        node.metadata_ = meta
        # Ein Rückweg tauscht die Phasen vollständig aus — mit ihnen das
        # Material. Ohne diesen Aufruf zeigten die Kanten auf den Stand vor
        # der Wiederherstellung.
        await synchronisiere_materialkanten(db, node.id, meta)
        # Titel und `refs` stehen im Vektor der Stunde.
        if vektor_veraltet(node, vektor_vorher):
            neu_einbetten.append(node.id)

    await db.commit()
    for nid in neu_einbetten:
        await enqueue_embedding_job(nid, db)
    return {"restored": True, "skipped_slot_ids": skipped}
