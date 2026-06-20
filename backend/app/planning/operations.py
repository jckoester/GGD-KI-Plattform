"""UP-6 Schritt 2: Typisierte Plan-Operationen + atomarer Executor.

Der Verschiebe-Assistent (UP-6 Schritt 3) und spätere UI-Bulk-Aktionen wenden eine
Liste typisierter Operationen an. Validierung ist all-or-nothing: schlägt eine Prüfung
fehl, wird **nichts** geschrieben (Fehlerliste zurück). Andernfalls: ein Snapshot
(`reason='reflow'`) davor, dann alle Operationen in **einer** Transaktion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Literal, Union
from uuid import UUID

import sqlalchemy as sa
from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode, LessonSlot
from app.planning.snapshots import create_snapshot

VALID_KATEGORIEN: frozenset[str] = frozenset(
    {"unterricht", "pruefung", "puffer", "ausfall", "vertretung"}
)


# ── Operationstypen (Discriminated Union über 'op') ──────────────────────────


class MoveContent(BaseModel):
    op: Literal["move_content"]
    from_slot_id: UUID
    to_slot_id: UUID


class SwapContent(BaseModel):
    op: Literal["swap_content"]
    slot_a: UUID
    slot_b: UUID


class SetTopic(BaseModel):
    op: Literal["set_topic"]
    slot_id: UUID
    thema: str | None = None


class SetUnit(BaseModel):
    op: Literal["set_unit"]
    slot_id: UUID
    unit_node_id: UUID | None = None


class SetCategory(BaseModel):
    op: Literal["set_category"]
    slot_id: UUID
    kategorie: str


class MarkNeedsAdjustment(BaseModel):
    op: Literal["mark_needs_adjustment"]
    slot_id: UUID
    value: bool = True


class TransferPhases(BaseModel):
    op: Literal["transfer_phases"]
    from_lesson_id: UUID
    to_lesson_id: UUID
    phase_ids: list[str]


class ShortenPhase(BaseModel):
    op: Literal["shorten_phase"]
    lesson_id: UUID
    phase_id: str
    dauer_min: int = Field(..., ge=1, le=480)


class StrikePhase(BaseModel):
    op: Literal["strike_phase"]
    lesson_id: UUID
    phase_id: str


PlanOperation = Annotated[
    Union[
        MoveContent, SwapContent, SetTopic, SetUnit, SetCategory,
        MarkNeedsAdjustment, TransferPhases, ShortenPhase, StrikePhase,
    ],
    Field(discriminator="op"),
]

_OPS_ADAPTER: TypeAdapter[list[PlanOperation]] = TypeAdapter(list[PlanOperation])


def parse_operations(raw: list[dict]) -> list[PlanOperation]:
    """Parst rohe Dicts in typisierte Operationen (wirft pydantic ValidationError)."""
    return _OPS_ADAPTER.validate_python(raw)


@dataclass
class ExecutionResult:
    applied: int
    errors: list[str] = field(default_factory=list)
    snapshot_id: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _has_content(slot: LessonSlot) -> bool:
    return bool(slot.ue_node_id or slot.stunde_node_id or slot.thema)


def _slot_ids(op: BaseModel) -> list[UUID]:
    return [getattr(op, f) for f in ("from_slot_id", "to_slot_id", "slot_a", "slot_b", "slot_id")
            if getattr(op, f, None) is not None]


def _lesson_ids(op: BaseModel) -> list[UUID]:
    return [getattr(op, f) for f in ("from_lesson_id", "to_lesson_id", "lesson_id")
            if getattr(op, f, None) is not None]


async def _validate(
    db: AsyncSession, group_id: int, ops: list[PlanOperation],
    slots: dict[UUID, LessonSlot], lessons: dict[UUID, ContextNode],
) -> list[str]:
    errors: list[str] = []

    def slot_ok(sid: UUID, ctx: str) -> LessonSlot | None:
        s = slots.get(sid)
        if s is None:
            errors.append(f"{ctx}: Slot {sid} gehört nicht zur Gruppe")
        return s

    # Simulierte Belegung für move/swap (Reihenfolge berücksichtigt).
    occ = {sid: _has_content(s) for sid, s in slots.items()}

    for i, op in enumerate(ops):
        ctx = f"op[{i}] {op.op}"
        for sid in _slot_ids(op):
            s = slot_ok(sid, ctx)
            if s is not None and s.pinned:
                errors.append(f"{ctx}: Slot {sid} ist gepinnt (unantastbar)")
        for lid in _lesson_ids(op):
            if lid not in lessons:
                errors.append(f"{ctx}: Stunde {lid} nicht gefunden")

        if isinstance(op, MoveContent):
            src, dst = slots.get(op.from_slot_id), slots.get(op.to_slot_id)
            if dst is not None and dst.kategorie == "ausfall":
                errors.append(f"{ctx}: Ziel ist Ausfall — nimmt keinen Inhalt auf")
            if dst is not None and occ.get(op.to_slot_id):
                errors.append(f"{ctx}: Ziel-Slot ist belegt")
            if src is not None and not occ.get(op.from_slot_id):
                errors.append(f"{ctx}: Quell-Slot hat keinen Inhalt")
            if src is not None and dst is not None:
                occ[op.from_slot_id] = False
                occ[op.to_slot_id] = True
        elif isinstance(op, SwapContent):
            a, b = slots.get(op.slot_a), slots.get(op.slot_b)
            for s, other in ((a, b), (b, a)):
                if s is not None and s.kategorie == "ausfall" and other is not None and occ.get(other.id):
                    errors.append(f"{ctx}: Ausfall-Slot {s.id} nimmt keinen Inhalt auf")
            if a is not None and b is not None:
                occ[op.slot_a], occ[op.slot_b] = occ.get(op.slot_b), occ.get(op.slot_a)
        elif isinstance(op, SetUnit):
            s = slots.get(op.slot_id)
            if s is not None and s.kategorie == "ausfall" and op.unit_node_id is not None:
                errors.append(f"{ctx}: Ausfall-Slot nimmt keine UE auf")
        elif isinstance(op, SetTopic):
            s = slots.get(op.slot_id)
            if s is not None and s.kategorie == "ausfall" and op.thema:
                errors.append(f"{ctx}: Ausfall-Slot nimmt kein Thema auf")
        elif isinstance(op, SetCategory):
            if op.kategorie not in VALID_KATEGORIEN:
                errors.append(f"{ctx}: ungültige Kategorie {op.kategorie!r}")
        elif isinstance(op, (ShortenPhase, StrikePhase, TransferPhases)):
            _validate_phase_op(op, lessons, errors, ctx)

    return errors


def _phase_ids(lesson: ContextNode | None) -> set[str]:
    if lesson is None:
        return set()
    return {str(p.get("id")) for p in (lesson.metadata_ or {}).get("phasen", [])}


def _validate_phase_op(op, lessons, errors, ctx):
    if isinstance(op, TransferPhases):
        src = lessons.get(op.from_lesson_id)
        have = _phase_ids(src)
        for pid in op.phase_ids:
            if pid not in have:
                errors.append(f"{ctx}: Phase {pid} nicht in Quellstunde")
    else:  # Shorten/Strike
        lesson = lessons.get(op.lesson_id)
        if lesson is not None and op.phase_id not in _phase_ids(lesson):
            errors.append(f"{ctx}: Phase {op.phase_id} nicht in Stunde")


# ── Anwenden ─────────────────────────────────────────────────────────────────


def _apply_move(src: LessonSlot, dst: LessonSlot) -> None:
    dst.ue_node_id, dst.stunde_node_id, dst.thema = src.ue_node_id, src.stunde_node_id, src.thema
    src.ue_node_id = src.stunde_node_id = src.thema = None
    src.anpassung_noetig = False


def _apply_swap(a: LessonSlot, b: LessonSlot) -> None:
    a.ue_node_id, b.ue_node_id = b.ue_node_id, a.ue_node_id
    a.stunde_node_id, b.stunde_node_id = b.stunde_node_id, a.stunde_node_id
    a.thema, b.thema = b.thema, a.thema


def _mutate_phases(lesson: ContextNode, fn) -> None:
    meta = dict(lesson.metadata_ or {})
    meta["phasen"] = fn(list(meta.get("phasen", [])))
    lesson.metadata_ = meta


def _apply_transfer(src: ContextNode, dst: ContextNode, phase_ids: list[str]) -> None:
    src_meta = dict(src.metadata_ or {})
    src_phasen = list(src_meta.get("phasen", []))
    moved = [dict(p) for p in src_phasen if str(p.get("id")) in phase_ids]
    for p in moved:
        p["status"] = "geplant"
        p["uebertrag_von"] = str(src.id)
    # An den Anfang der Folgestunde.
    dst_meta = dict(dst.metadata_ or {})
    dst_meta["phasen"] = moved + list(dst_meta.get("phasen", []))
    # refs_offen der Quelle als refs der Zielstunde mitführen (dedupliziert).
    src_offen = list(src_meta.get("refs_offen", []))
    if src_offen:
        existing = {str(r.get("node_id")) for r in dst_meta.get("refs", [])}
        carried = [{"node_id": str(nid), "typ": "ik"} for nid in src_offen if str(nid) not in existing]
        dst_meta["refs"] = list(dst_meta.get("refs", [])) + carried
        src_meta["refs_offen"] = []
    # Übertragene Phasen aus der Quelle entfernen.
    src_meta["phasen"] = [p for p in src_phasen if str(p.get("id")) not in phase_ids]
    src.metadata_ = src_meta
    dst.metadata_ = dst_meta


async def apply_operations(
    db: AsyncSession, group_id: int, ops: list[PlanOperation], *,
    summary: str, created_by: str | None = None,
) -> ExecutionResult:
    """Validiert und wendet die Operationen atomar an (Snapshot davor)."""
    slot_ids = {sid for op in ops for sid in _slot_ids(op)}
    lesson_ids = {lid for op in ops for lid in _lesson_ids(op)}

    slots = {
        s.id: s
        for s in (
            await db.execute(
                sa.select(LessonSlot).where(
                    LessonSlot.group_id == group_id, LessonSlot.id.in_(slot_ids or {None})
                )
            )
        ).scalars().all()
    }
    lessons = {
        n.id: n
        for n in (
            await db.execute(
                sa.select(ContextNode).where(ContextNode.id.in_(lesson_ids or {None}))
            )
        ).scalars().all()
    }

    errors = await _validate(db, group_id, ops, slots, lessons)
    if errors:
        return ExecutionResult(applied=0, errors=errors)

    snap = await create_snapshot(db, group_id, reason="reflow", label=summary, created_by=created_by)

    for op in ops:
        if isinstance(op, MoveContent):
            _apply_move(slots[op.from_slot_id], slots[op.to_slot_id])
        elif isinstance(op, SwapContent):
            _apply_swap(slots[op.slot_a], slots[op.slot_b])
        elif isinstance(op, SetTopic):
            slots[op.slot_id].thema = op.thema
        elif isinstance(op, SetUnit):
            slots[op.slot_id].ue_node_id = op.unit_node_id
        elif isinstance(op, SetCategory):
            slots[op.slot_id].kategorie = op.kategorie
        elif isinstance(op, MarkNeedsAdjustment):
            slots[op.slot_id].anpassung_noetig = op.value
        elif isinstance(op, TransferPhases):
            _apply_transfer(lessons[op.from_lesson_id], lessons[op.to_lesson_id], op.phase_ids)
        elif isinstance(op, ShortenPhase):
            def _shorten(phasen, _op=op):
                for p in phasen:
                    if str(p.get("id")) == _op.phase_id:
                        p["dauer_min"], p["kuerzung"] = _op.dauer_min, True
                return phasen
            _mutate_phases(lessons[op.lesson_id], _shorten)
        elif isinstance(op, StrikePhase):
            def _strike(phasen, _op=op):
                for p in phasen:
                    if str(p.get("id")) == _op.phase_id:
                        p["status"], p["kuerzung"] = "gestrichen", True
                return phasen
            _mutate_phases(lessons[op.lesson_id], _strike)

    await db.commit()
    return ExecutionResult(applied=len(ops), errors=[], snapshot_id=str(snap.id))
