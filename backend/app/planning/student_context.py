"""UP-7 Schritt 1+3: Planungsdaten für den Schüler-/Lehrkraft-Kontext.

Liefert datenschutzkonform (Whitelist, siehe UP-Phase-7-Plan) das „aktuelle Thema"
einer Unterrichtsgruppe (zuletzt behandelt / nächste Stunden) und den
Klassenarbeits-Scope. Nur lesend; keine internen Planungsfelder
(`note`, `anpassung_noetig`, Pin, Phasen-Details, Reflexion) verlassen das Backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode, LessonSlot

# Kategorien, die als „behandelter/geplanter Unterricht" gelten (Prüfungen separat).
BEHANDELT_KATEGORIEN: tuple[str, ...] = ("unterricht", "vertretung")


@dataclass
class TopicSlot:
    """Ein einzelner Slot in der Whitelist-Sicht (kein internes Planungsfeld)."""

    datum: date
    kategorie: str
    thema: str | None
    stundenziel: str | None
    ue_titel: str | None
    auto_bestaetigt: bool = False  # vergangene Slots: per Auto-Cron bestätigt ("vermutlich")


@dataclass
class CurrentTopic:
    zuletzt: TopicSlot | None
    naechste: list[TopicSlot] = field(default_factory=list)


def _belegt_filter():
    """Slot ist „belegt": Unterricht/Vertretung mit Thema oder verknüpfter Stunde."""
    return sa.and_(
        LessonSlot.kategorie.in_(BEHANDELT_KATEGORIEN),
        sa.or_(LessonSlot.thema.isnot(None), LessonSlot.stunde_node_id.isnot(None)),
    )


async def _resolve_nodes(db: AsyncSession, slots: list[LessonSlot]) -> dict[UUID, ContextNode]:
    node_ids: set[UUID] = set()
    for s in slots:
        if s.ue_node_id:
            node_ids.add(s.ue_node_id)
        if s.stunde_node_id:
            node_ids.add(s.stunde_node_id)
    if not node_ids:
        return {}
    rows = (
        await db.execute(sa.select(ContextNode).where(ContextNode.id.in_(node_ids)))
    ).scalars().all()
    return {n.id: n for n in rows}


def _to_topic_slot(slot: LessonSlot, nodes: dict[UUID, ContextNode]) -> TopicSlot:
    stunde = nodes.get(slot.stunde_node_id) if slot.stunde_node_id else None
    ue = nodes.get(slot.ue_node_id) if slot.ue_node_id else None
    stundenziel = None
    if stunde is not None and isinstance(stunde.metadata_, dict):
        stundenziel = stunde.metadata_.get("stundenziel") or None
    return TopicSlot(
        datum=slot.date,
        kategorie=slot.kategorie,
        thema=slot.thema or (stunde.title if stunde else None),
        stundenziel=stundenziel,
        ue_titel=ue.title if ue else None,
        auto_bestaetigt=slot.nachbereitet_auto,
    )


@dataclass
class ExamScopeRef:
    node_id: str
    titel: str | None = None
    code: str | None = None


@dataclass
class ExamScope:
    exam_date: date
    unit_titles: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    refs: list[ExamScopeRef] = field(default_factory=list)

    @property
    def ref_node_ids(self) -> list[str]:
        return [r.node_id for r in self.refs]


async def get_exam_scope(
    db: AsyncSession, group_id: int, *, today: date, exam_slot_id: UUID | None = None
) -> ExamScope | None:
    """Umfang der nächsten Klassenarbeit (oder eines expliziten Prüfungs-Slots).

    Umfang = UE des Prüfungs-Slots; fehlt sie, die UEs der belegten Slots seit der
    letzten Prüfung. `ref_node_ids` (Kompetenzen für Lernplan/Übungsauswahl) stammen
    nur aus **nachbereiteten** Stunden der UE bis zum Prüfungstermin, abzüglich der als
    offen markierten Refs (`refs_offen`, UP-5). Gibt None zurück, wenn keine Prüfung
    geplant ist.
    """
    if exam_slot_id is not None:
        exam = await db.get(LessonSlot, exam_slot_id)
        if exam is None or exam.group_id != group_id or exam.kategorie != "pruefung":
            return None
    else:
        exam = (
            await db.execute(
                sa.select(LessonSlot)
                .where(
                    LessonSlot.group_id == group_id,
                    LessonSlot.kategorie == "pruefung",
                    LessonSlot.date >= today,
                )
                .order_by(LessonSlot.date.asc(), LessonSlot.start_period.asc().nullsfirst())
                .limit(1)
            )
        ).scalar_one_or_none()
    if exam is None:
        return None

    # Scope-UEs bestimmen.
    if exam.ue_node_id is not None:
        scope_ue_ids = [exam.ue_node_id]
    else:
        prev_exam_date = (
            await db.execute(
                sa.select(LessonSlot.date)
                .where(
                    LessonSlot.group_id == group_id,
                    LessonSlot.kategorie == "pruefung",
                    LessonSlot.date < exam.date,
                )
                .order_by(LessonSlot.date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        q = sa.select(LessonSlot.ue_node_id).where(
            LessonSlot.group_id == group_id,
            LessonSlot.ue_node_id.isnot(None),
            LessonSlot.date < exam.date,
        )
        if prev_exam_date is not None:
            q = q.where(LessonSlot.date > prev_exam_date)
        scope_ue_ids = list((await db.execute(q.distinct())).scalars().all())

    if not scope_ue_ids:
        return ExamScope(exam_date=exam.date)

    in_scope = list(
        (
            await db.execute(
                sa.select(LessonSlot)
                .where(
                    LessonSlot.group_id == group_id,
                    LessonSlot.ue_node_id.in_(scope_ue_ids),
                    LessonSlot.date <= exam.date,
                )
                .order_by(LessonSlot.date.asc())
            )
        ).scalars().all()
    )

    nodes = await _resolve_nodes(db, in_scope)
    ue_nodes = (
        await db.execute(sa.select(ContextNode).where(ContextNode.id.in_(scope_ue_ids)))
    ).scalars().all()
    unit_titles = [n.title for n in ue_nodes]

    topics: list[str] = []
    refs: dict[str, ExamScopeRef] = {}
    for slot in in_scope:
        stunde = nodes.get(slot.stunde_node_id) if slot.stunde_node_id else None
        thema = slot.thema or (stunde.title if stunde else None)
        if thema and thema not in topics:
            topics.append(thema)
        # Refs nur aus nachbereiteten Stunden, abzüglich refs_offen.
        if (
            stunde is not None
            and slot.nachbereitet_at is not None
            and isinstance(stunde.metadata_, dict)
        ):
            offen = {str(x) for x in (stunde.metadata_.get("refs_offen") or [])}
            for r in stunde.metadata_.get("refs") or []:
                nid = str(r.get("node_id")) if r.get("node_id") else None
                if nid and nid not in offen and nid not in refs:
                    refs[nid] = ExamScopeRef(node_id=nid, titel=r.get("titel"), code=r.get("code"))

    return ExamScope(
        exam_date=exam.date, unit_titles=unit_titles, topics=topics, refs=list(refs.values())
    )


_WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _fmt_datum(d: date) -> str:
    return f"{_WOCHENTAGE[d.weekday()]} {d.day}.{d.month}."


def render_topic_block(
    topic: CurrentTopic | None, group_label: str, exam: ExamScope | None = None
) -> str:
    """Token-kompakter Markdown-Block „Aktueller Unterricht" für den Chat-Kontext."""
    lines = [f"## Aktueller Unterricht ({group_label})"]
    if topic is not None:
        if topic.zuletzt is not None:
            z = topic.zuletzt
            ue = f' (UE „{z.ue_titel}")' if z.ue_titel else ""
            prefix = "Vermutlich behandelt" if z.auto_bestaetigt else "Zuletzt behandelt"
            lines.append(f"- {prefix} ({_fmt_datum(z.datum)}): {z.thema or '—'}{ue}")
        for i, s in enumerate(topic.naechste):
            label = "Nächste Stunde" if i == 0 else "Danach"
            ziel = f" — {s.stundenziel}" if s.stundenziel else ""
            lines.append(f"- {label} ({_fmt_datum(s.datum)}): {s.thema or '—'}{ziel}")
    if exam is not None:
        umfang = ", ".join(exam.unit_titles) if exam.unit_titles else "noch offen"
        lines.append(f"- Klassenarbeit: {_fmt_datum(exam.exam_date)} — Umfang: {umfang}")
    return "\n".join(lines)


async def get_current_topic(
    db: AsyncSession, group_id: int, today: date
) -> CurrentTopic | None:
    """Zuletzt behandelter + die nächsten 1–2 belegten Slots der Gruppe.

    „Zuletzt behandelt" ist der jüngste vergangene, belegte Slot, der **nachbereitet**
    ist (manuell oder per Auto-Cron) — UP-5-Grundsatz: was die Klasse nie gesehen hat,
    gilt nicht als behandelt. Gibt None zurück, wenn weder Vergangenes noch Kommendes
    belegt ist. `ausfall`/`puffer` werden über das Belegt-Kriterium übersprungen.
    """
    zuletzt_slot = (
        await db.execute(
            sa.select(LessonSlot)
            .where(
                LessonSlot.group_id == group_id,
                LessonSlot.date < today,
                LessonSlot.nachbereitet_at.isnot(None),
                _belegt_filter(),
            )
            .order_by(LessonSlot.date.desc(), LessonSlot.start_period.desc().nullslast())
            .limit(1)
        )
    ).scalar_one_or_none()

    naechste_slots = list(
        (
            await db.execute(
                sa.select(LessonSlot)
                .where(
                    LessonSlot.group_id == group_id,
                    LessonSlot.date >= today,
                    _belegt_filter(),
                )
                .order_by(LessonSlot.date.asc(), LessonSlot.start_period.asc().nullsfirst())
                .limit(2)
            )
        ).scalars().all()
    )

    if zuletzt_slot is None and not naechste_slots:
        return None

    nodes = await _resolve_nodes(db, [s for s in [zuletzt_slot, *naechste_slots] if s])
    return CurrentTopic(
        zuletzt=_to_topic_slot(zuletzt_slot, nodes) if zuletzt_slot else None,
        naechste=[_to_topic_slot(s, nodes) for s in naechste_slots],
    )
