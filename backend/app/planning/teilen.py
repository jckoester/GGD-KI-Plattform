"""Doppelstunde in zwei Einzelstunden teilen — und wieder zusammenlegen (0.19, Schritt 3).

Anlass (Jan, 18.10.2026): eine Klassenarbeit in der ersten Stunde, Unterricht in der zweiten;
der Übergang von einer Unterrichtseinheit zur nächsten mitten in der Doppelstunde.

**Was beim Teilen wohin geht** (Plan F4, Jan 19.10.2026):

- Beide Hälften behalten **Herkunft, Kategorie, Ausfall, Einheit und Notiz** — ein Ausfall
  gilt für beide, und der Stundenplan-Abgleich ordnet jede Stunde weiter einzeln zu.
- **Entwurf und Thema bleiben an der ersten Hälfte.** Ein Entwurf hängt an höchstens einem
  Termin (Index aus 0087); einer über 90 Minuten zeigt danach 45 verfügbar und einen Überhang.
- Beide Hälften tragen `geteilt`: Der Neuaufbau aus dem Wochenmuster lässt sie stehen.

**Kein Snapshot.** Der Verlauf der Jahresplanung stellt Zuordnungen wieder her, keine Termine
(`snapshots.py`): Ein Rückgängig-Eintrag „Doppelstunde geteilt" versprach etwas, das er nicht
hält. Der Rückweg ist `zusammenlegen` — und dabei geht nichts verloren, weil es sich weigert,
solange die zweite Hälfte eigenen Inhalt trägt.
"""
from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LessonSlot

# Was die zweite Hälfte von der ersten übernimmt. Nicht dabei: Entwurf, Thema, Nachbereitung,
# „Anpassung nötig" — das gehört zur Stunde, die schon geplant war, also zur ersten.
_UEBERNOMMEN = (
    "group_id", "date", "halbjahr", "kategorie", "ue_node_id", "pinned", "note",
    "ausfall_herkunft", "ausfall_vorher", "source", "vorlaeufig", "external_uid",
)


async def teile(db: AsyncSession, slot: LessonSlot) -> tuple[LessonSlot, LessonSlot]:
    """Teilt eine Doppelstunde. → (erste Hälfte, zweite Hälfte). 409, wenn es keine ist."""
    if slot.periods != 2 or slot.start_period is None:
        raise HTTPException(status_code=409, detail="Nur eine Doppelstunde lässt sich teilen.")
    zweite = LessonSlot(
        **{feld: getattr(slot, feld) for feld in _UEBERNOMMEN},
        start_period=slot.start_period + 1,
        periods=1,
        geteilt=True,
    )
    slot.periods = 1
    slot.geteilt = True
    slot.updated_at = datetime.now(timezone.utc)
    db.add(zweite)
    await db.flush()
    return slot, zweite


async def _haelften(db: AsyncSession, slot: LessonSlot) -> tuple[LessonSlot, LessonSlot]:
    if not slot.geteilt or slot.start_period is None:
        raise HTTPException(status_code=409, detail="Diese Stunde ist keine geteilte Doppelstunde.")
    nachbarn = (
        await db.execute(
            sa.select(LessonSlot).where(
                LessonSlot.group_id == slot.group_id,
                LessonSlot.date == slot.date,
                LessonSlot.geteilt.is_(True),
                LessonSlot.periods == 1,
                LessonSlot.start_period.in_([slot.start_period - 1, slot.start_period + 1]),
                LessonSlot.id != slot.id,
            )
        )
    ).scalars().all()
    if len(nachbarn) != 1:
        raise HTTPException(
            status_code=409,
            detail="Die andere Hälfte dieser Doppelstunde ist nicht eindeutig zu finden.",
        )
    andere = nachbarn[0]
    return (slot, andere) if slot.start_period < andere.start_period else (andere, slot)


async def lege_zusammen(db: AsyncSession, slot: LessonSlot) -> LessonSlot:
    """Legt die Hälften wieder zu einer Doppelstunde zusammen — `slot` darf jede sein.

    Die erste Hälfte bleibt und bekommt beide Stunden; die zweite wird gelöscht. Trägt die
    zweite eigenen Inhalt (Entwurf, Thema oder eine andere Einheit als die erste), 409: Den
    erst woanders hin, sonst ginge er hier verloren.
    """
    erste, zweite = await _haelften(db, slot)
    eigene_einheit = zweite.ue_node_id is not None and zweite.ue_node_id != erste.ue_node_id
    if zweite.stunde_node_id or (zweite.thema or "").strip() or eigene_einheit:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Die {zweite.start_period}. Stunde trägt eigenen Inhalt. Verschieben oder "
                "entfernen Sie ihn zuerst, dann lassen sich die Hälften zusammenlegen."
            ),
        )
    erste.periods = 2
    erste.geteilt = False
    erste.updated_at = datetime.now(timezone.utc)
    await db.delete(zweite)
    await db.flush()
    return erste
