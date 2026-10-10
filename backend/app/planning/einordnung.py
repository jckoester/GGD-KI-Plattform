"""Der Entwurf eines Termins gehört zur Einheit des Termins (0.15).

Zwei Stellen sagen, zu welcher Einheit eine Stunde gehört: der Termin (`lesson_slots.
ue_node_id`, gesetzt im Jahresplan) und der Entwurf (Kante `part_of` zur Einheit). Gelesen
wird die Kante — von der Entwurfsansicht, der Stundennavigation und dem Zusammenhang, den
`get_lesson_detail` dem Stundenassistenten mitgibt.

Bis 0.15 zog nur das **Anlegen** eines Entwurfs die Kante mit. Wer einem Termin, der schon
einen Entwurf hatte, nachträglich eine Einheit zuwies — im Jahresplan, über den
Jahresplan-Assistenten, per Operation oder durch Wiederherstellen eines Snapshots —, änderte
nur den Termin. Der Entwurf blieb ohne Einheit oder hing an der alten: Die Entwurfsansicht
zeigte keine Einheit, und der Stundenassistent bekam weder Einheit noch Kapitel (gemessen
10.10.2026 auf Dev: 1 von 12 Terminen mit Entwurf und Einheit).

**Der Termin entscheidet.** Der Jahresplan legt fest, welche Einheit an einem Datum
unterrichtet wird; der Entwurf folgt. Die `follows`-Kette der Navigation bleibt unberührt.
"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextEdge, ContextNode, LessonSlot


async def ordne_entwurf_ein(db: AsyncSession, slot: LessonSlot) -> None:
    """Hängt den Entwurf des Termins an die Einheit des Termins — und nur an sie.

    Ohne Entwurf tut die Funktion nichts. Eine Kante zu einer anderen Einheit fällt weg,
    ebenso jede Einheitskante, wenn der Termin keine Einheit mehr hat. Ein No-op, wenn
    beides schon stimmt; schreibt nicht selbst fest (der Aufrufer committet).
    """
    if slot.stunde_node_id is None:
        return
    # ⚠️ Typunabhängig vergleichen: Das Wiederherstellen eines Snapshots setzt die Kennungen
    # als Zeichenketten aus dem JSON, die Kanten tragen UUIDs. Mit `!=` hielt die Funktion die
    # vorhandene Kante für falsch, löschte sie und legte dieselbe neu an — beides in einem
    # Flush, das INSERT zuerst: Verletzung von `idx_context_edges_unique`.
    einheit = str(slot.ue_node_id) if slot.ue_node_id else None
    kanten = (await db.execute(
        sa.select(ContextEdge)
        .join(ContextNode, ContextNode.id == ContextEdge.to_node_id)
        .where(
            ContextEdge.from_node_id == slot.stunde_node_id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "unterrichtseinheit",
        )
    )).scalars().all()
    for kante in kanten:
        if str(kante.to_node_id) != einheit:
            await db.delete(kante)
    if einheit is not None and not any(str(k.to_node_id) == einheit for k in kanten):
        db.add(ContextEdge(
            from_node_id=slot.stunde_node_id,
            to_node_id=UUID(einheit),
            relation="part_of",
            metadata_={},
        ))
