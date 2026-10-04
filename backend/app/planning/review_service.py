"""Nachbereitungs-Pipeline: Phasen-Status, Engagement-Schreibung, Undo."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode, LessonSlot, NodeEngagement

#: Was eine Nachbereitung über eine Phase sagen kann. Andere gespeicherte Werte — etwa
#: „geplant" aus einer Übertragung — heißen „noch nicht nachbereitet".
NACHBEREITUNG_STATI = ("erledigt", "offen", "gestrichen")


def vorbelegung(phase: dict) -> str:
    """Der Status einer Phase, wenn die Nachbereitung nichts über sie sagt.

    Ein schon gespeicherter Status bleibt — eine vorab gestrichene Phase wird nicht
    „erledigt", nur weil die Nachbereitung sie nicht erwähnt. Bis 0.13.0 galt pauschal
    „erledigt"; die Auto-Nachbereitung schickt gar keine Stati und überschrieb damit jede
    Streichung. Dieselbe Regel belegt die Knöpfe im Stundeneditor vor.
    """
    status = phase.get("status")
    return status if status in NACHBEREITUNG_STATI else "erledigt"


@dataclass
class ReviewResult:
    engagements_written: int = 0
    engagements_skipped: int = 0
    refs_offen: list[str] = field(default_factory=list)
    open_phases: list[str] = field(default_factory=list)


async def complete_review(
    db: AsyncSession,
    slot_id: UUID,
    *,
    group_id: int,
    phasen_status: dict[str, str],
    reflexion: str | None = None,
    refs_offen: list[UUID] | None = None,
    auto: bool = False,
) -> ReviewResult:
    """Schreibt Phasen-Status + Engagement-Zeilen und stempelt den Slot."""
    slot = await db.get(LessonSlot, slot_id)
    if slot is None:
        raise ValueError("Slot nicht gefunden")
    if slot.stunde_node_id is None:
        raise ValueError("Slot hat keine Stunde")

    stunde = await db.get(ContextNode, slot.stunde_node_id)
    if stunde is None:
        raise ValueError("Stunde nicht gefunden")

    meta = dict(stunde.metadata_ or {})
    # ⚠️ Kopien, nicht die gespeicherten Phasen selbst: Wer sie in place ändert, ändert
    # auch den Vergleichswert, an dem SQLAlchemy erkennt, ob es etwas zu schreiben gibt —
    # dann schien alles gleich, und der neue Status kam nie in die Datenbank (gemessen
    # 04.10.2026: nach „Rückgängig" und erneuter Nachbereitung). Wie `_mutate_phases`.
    phasen = [dict(p) for p in meta.get("phasen", [])]
    refs_offen_ids = [str(r) for r in (refs_offen or [])]
    refs_offen_set = set(refs_offen_ids)

    # 1. Phasen-Status schreiben — den bisherigen merken, damit „Rückgängig" ihn
    #    zurückgibt, statt etwa eine vorab gestrichene Phase stillschweigend zu entstreichen.
    for phase in phasen:
        phase_id = str(phase.get("id") or "")
        vorher = phase.get("status")
        if vorher is None:
            phase.pop("status_vorher", None)
        else:
            phase["status_vorher"] = vorher
        phase["status"] = phasen_status.get(phase_id) or vorbelegung(phase)

    if reflexion is not None:
        meta["reflexion"] = reflexion
    meta["phasen"] = phasen
    meta["refs_offen"] = refs_offen_ids
    stunde.metadata_ = meta
    stunde.updated_at = datetime.now(timezone.utc)

    # 2. Engagement-Ziele: refs minus refs_offen + Knoten aus erledigten Phasen
    all_refs: list[dict] = meta.get("refs", [])
    target_node_ids: list[UUID] = []

    for ref in all_refs:
        node_id_raw = ref.get("node_id")
        if node_id_raw and str(node_id_raw) not in refs_offen_set:
            target_node_ids.append(UUID(str(node_id_raw)))

    for phase in phasen:
        if phase.get("status") in ("offen", "gestrichen"):
            continue
        methode = phase.get("methode") or {}
        if methode.get("typ") == "node" and methode.get("node_id"):
            target_node_ids.append(UUID(str(methode["node_id"])))
        for mat in phase.get("material") or []:
            if mat.get("typ") == "node" and mat.get("node_id"):
                target_node_ids.append(UUID(str(mat["node_id"])))

    # Deduplizieren
    seen: set[UUID] = set()
    unique_targets: list[UUID] = []
    for n in target_node_ids:
        if n not in seen:
            seen.add(n)
            unique_targets.append(n)

    # 3. Upsert NodeEngagement idempotent via ON CONFLICT DO NOTHING
    written = 0
    skipped = 0
    engagement_meta = {
        "slot_id": str(slot_id),
        "stunde_node_id": str(stunde.id),
        "auto": auto,
    }

    for node_id in unique_targets:
        stmt = (
            pg_insert(NodeEngagement)
            .values(
                group_id=group_id,
                node_id=node_id,
                relation="introduced",
                source="lesson_plan",
                metadata_=engagement_meta,
            )
            .on_conflict_do_nothing()
        )
        result = await db.execute(stmt)
        if result.rowcount and result.rowcount > 0:
            written += 1
        else:
            skipped += 1

    # 4. Slot stempeln
    now = datetime.now(timezone.utc)
    slot.nachbereitet_at = now
    slot.nachbereitet_auto = auto
    slot.updated_at = now

    await db.commit()

    open_phases = [
        p.get("name", "")
        for p in phasen
        if p.get("status") in ("offen", "gestrichen")
    ]
    return ReviewResult(
        engagements_written=written,
        engagements_skipped=skipped,
        refs_offen=refs_offen_ids,
        open_phases=open_phases,
    )


async def undo_review(db: AsyncSession, slot_id: UUID, *, group_id: int) -> int:
    """Löscht Engagement-Zeilen dieser Nachbereitung, setzt Slot zurück."""
    result = await db.execute(
        sa.delete(NodeEngagement)
        .where(
            NodeEngagement.group_id == group_id,
            NodeEngagement.source == "lesson_plan",
            NodeEngagement.metadata_["slot_id"].astext == str(slot_id),
        )
        .returning(NodeEngagement.id)
    )
    deleted_count = len(result.fetchall())

    slot = await db.get(LessonSlot, slot_id)
    if slot:
        slot.nachbereitet_at = None
        slot.nachbereitet_auto = False
        slot.updated_at = datetime.now(timezone.utc)

        if slot.stunde_node_id:
            stunde = await db.get(ContextNode, slot.stunde_node_id)
            if stunde:
                meta = dict(stunde.metadata_ or {})
                # Kopien — aus demselben Grund wie in `complete_review`.
                meta["phasen"] = [dict(p) for p in meta.get("phasen", [])]
                for phase in meta["phasen"]:
                    # Zurück auf den Stand vor der Nachbereitung, nicht auf „kein Status".
                    vorher = phase.pop("status_vorher", None)
                    if vorher is None:
                        phase.pop("status", None)
                    else:
                        phase["status"] = vorher
                meta.pop("reflexion", None)
                meta["refs_offen"] = []
                stunde.metadata_ = meta
                stunde.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return deleted_count
