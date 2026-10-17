"""UP-7 Schritt 1+3: Planungsdaten für den Schüler-/Lehrkraft-Kontext.

Liefert datenschutzkonform (Whitelist, siehe UP-Phase-7-Plan) das „aktuelle Thema"
einer Unterrichtsgruppe (letzte und vorletzte Stunde / nächste Stunden) und den
Klassenarbeits-Scope. Nur lesend; keine internen Planungsfelder
(`note`, `anpassung_noetig`, Pin, Phasen-Details, Reflexion, Material) verlassen das Backend.
Seit 0.15 gehören die **Inhalte** der vergangenen Stunden dazu — Kompetenzen und Begriffe aus
den `refs` des Entwurfs, soweit jedes Mitglied der Gruppe sie lesen darf.
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

#: Vergangene Stunden im Block: die letzte und die vorletzte (0.15). Mit der vorletzten
#: daneben kann das Modell eine Verwechslung („letzte Stunde … Metallbindung") auflösen.
VERGANGENE_STUNDEN = 2
#: Inhalte je Stunde im Block — mehr ist eine Liste, keine Auskunft.
INHALTE_JE_STUNDE = 5
#: Länge eines Inhalts im Block; Kompetenztitel tragen Nummer und ganzen Text.
INHALT_ZEICHEN = 100


@dataclass
class TopicSlot:
    """Ein einzelner Slot in der Whitelist-Sicht (kein internes Planungsfeld)."""

    datum: date
    kategorie: str
    thema: str | None
    stundenziel: str | None
    ue_titel: str | None
    auto_bestaetigt: bool = False  # vergangene Slots: per Auto-Cron bestätigt ("vermutlich")
    # Vergangene Slots (0.15): nachbereitet oder nur „laut Plan", und ihre Inhalte —
    # eingeführt (nachbereitet, ohne `refs_offen`) bzw. geplant (alle `refs`).
    nachbereitet: bool = False
    inhalte: list[str] = field(default_factory=list)


@dataclass
class CurrentTopic:
    #: Die vergangenen Stunden, die jüngste zuerst — nachbereitet oder nicht (0.15).
    vergangene: list[TopicSlot] = field(default_factory=list)
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


def _fuer_alle_lesbar(node: ContextNode, group_id: int) -> bool:
    """Darf **jedes** Mitglied der Gruppe den Knoten lesen? Der Block ist für alle derselbe.

    Dieselben Scopes wie `context.visibility.read_scope_clause` für eine Schüler:in der
    Gruppe — ohne Eigentum, das an einer Person hängt. `private` und `group_teachers` fallen
    heraus (etwa ein privater Begriff der Lehrkraft), ebenso eine fremde Gruppe.
    """
    from app.context.visibility import OFFENE_SCOPES

    return node.read_scope in OFFENE_SCOPES or (
        node.read_scope == "group" and node.read_scope_group_id == group_id
    )


def _inhalt(node: ContextNode) -> str:
    titel = (node.title or "").strip()
    return titel if len(titel) <= INHALT_ZEICHEN else titel[: INHALT_ZEICHEN - 1].rstrip() + "…"


async def _inhalte(
    db: AsyncSession, group_id: int, slots: list[LessonSlot], nodes: dict[UUID, ContextNode]
) -> dict[UUID, list[str]]:
    """Inhalte je vergangenem Slot aus den `refs` seines Entwurfs.

    **Nachbereitet:** `refs` ohne `refs_offen` — dasselbe, was die Nachbereitung als
    „eingeführt" in den Lernstand schreibt (dort zusätzlich Material und Methode, die hier
    fehlen). **Nicht nachbereitet:** alle `refs` — „laut Plan". Kompetenzen und Begriffe,
    nur lesbare (`_fuer_alle_lesbar`).
    """
    wunsch: dict[UUID, list[UUID]] = {}
    for slot in slots:
        stunde = nodes.get(slot.stunde_node_id) if slot.stunde_node_id else None
        meta = stunde.metadata_ if stunde is not None and isinstance(stunde.metadata_, dict) else {}
        offen = {str(x) for x in (meta.get("refs_offen") or [])} if slot.nachbereitet_at else set()
        ids = []
        for ref in meta.get("refs") or []:
            nid = ref.get("node_id") if isinstance(ref, dict) else None
            if nid and str(nid) not in offen:
                try:
                    ids.append(UUID(str(nid)))
                except ValueError:
                    continue
        wunsch[slot.id] = ids
    alle = {i for ids in wunsch.values() for i in ids}
    if not alle:
        return {}
    gelesen = {
        n.id: n for n in (await db.execute(sa.select(ContextNode).where(ContextNode.id.in_(alle)))).scalars()
        if _fuer_alle_lesbar(n, group_id)
    }
    return {
        sid: [_inhalt(gelesen[i]) for i in ids if i in gelesen][:INHALTE_JE_STUNDE]
        for sid, ids in wunsch.items()
    }


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
        nachbereitet=slot.nachbereitet_at is not None,
    )


@dataclass
class ExamScopeRef:
    node_id: str
    titel: str | None = None
    code: str | None = None
    # „ik", „pk" oder „concept" (Fachbegriff, seit 0.17) — damit ein Lernplan Begriffe als
    # Begriffe nennen kann, nicht als Kompetenzen.
    typ: str | None = None
    # Bei Begriffen die Aliase, unter denen die Stunden sie genannt haben („σ-Komplex" bei
    # „elektrophile Substitution") — gesammelt über alle Stunden des Umfangs.
    aliase: list[str] = field(default_factory=list)


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
                if not nid or nid in offen:
                    continue
                if nid not in refs:
                    refs[nid] = ExamScopeRef(node_id=nid, titel=r.get("titel"), code=r.get("code"),
                                             typ=r.get("typ"))
                refs[nid].aliase = list(dict.fromkeys([*refs[nid].aliase, *(r.get("aliase") or [])]))

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
        # „Letzte" und „Vorletzte" wie in der Frage der Schüler:in. Der Stand sagt ehrlich,
        # woher das Thema stammt: nachbereitet, per Auto-Bestätigung — oder nur aus dem Plan.
        for i, z in enumerate(topic.vergangene):
            label = "Letzte Stunde" if i == 0 else "Vorletzte Stunde"
            if not z.nachbereitet:
                stand, wort = "laut Plan — noch nicht nachbereitet", "geplant"
            elif z.auto_bestaetigt:
                stand, wort = "vermutlich behandelt", "eingeführt"
            else:
                stand, wort = "behandelt", "eingeführt"
            ue = f' (UE „{z.ue_titel}")' if z.ue_titel else ""
            inhalte = f" — {wort}: {' · '.join(z.inhalte)}" if z.inhalte else ""
            lines.append(f"- {label} ({_fmt_datum(z.datum)}, {stand}): {z.thema or '—'}{ue}{inhalte}")
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
    """Die letzten zwei vergangenen + die nächsten 1–2 belegten Slots der Gruppe.

    ⚠️ **Vergangen heißt vergangen, nicht nachbereitet** (0.15, Messung „letzte Stunde",
    11.10.2026). Bis dahin zählte nur ein **nachbereiteter** Slot — UP-5: was die Klasse nie
    gesehen hat, gilt nicht als behandelt. Die Auto-Bestätigung bestätigt eine Stunde aber erst,
    wenn die nächste vorbei ist; zwischen letzter und nächster Stunde nannte der Block also die
    **vorletzte** als „Zuletzt behandelt". Auf „Ich habe die letzte Stunde nicht verstanden"
    erklärte das Modell darauf dreimal von drei das Thema der vorletzten. Jetzt steht die
    letzte vergangene Stunde da — und ob sie nachbereitet ist oder nur geplant war, sagt der
    Block (`render_topic_block`). Der UP-5-Grundsatz bleibt im Wort: „behandelt" heißt nur, was
    nachbereitet ist.

    Gibt None zurück, wenn weder Vergangenes noch Kommendes belegt ist. `ausfall`/`puffer`
    werden über das Belegt-Kriterium übersprungen.
    """
    vergangene_slots = list(
        (
            await db.execute(
                sa.select(LessonSlot)
                .where(
                    LessonSlot.group_id == group_id,
                    LessonSlot.date < today,
                    _belegt_filter(),
                )
                .order_by(LessonSlot.date.desc(), LessonSlot.start_period.desc().nullslast())
                .limit(VERGANGENE_STUNDEN)
            )
        ).scalars().all()
    )

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

    if not vergangene_slots and not naechste_slots:
        return None

    nodes = await _resolve_nodes(db, [*vergangene_slots, *naechste_slots])
    inhalte = await _inhalte(db, group_id, vergangene_slots, nodes)
    vergangene = []
    for slot in vergangene_slots:
        topic_slot = _to_topic_slot(slot, nodes)
        topic_slot.inhalte = inhalte.get(slot.id, [])
        vergangene.append(topic_slot)
    return CurrentTopic(
        vergangene=vergangene,
        naechste=[_to_topic_slot(s, nodes) for s in naechste_slots],
    )
