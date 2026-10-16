"""Planungs-Tools für den Jahresplan-Assistenten.

Registriert sich beim Import in TOOL_REGISTRY.
Die Tools der Fähigkeit `planning` erfordern eine group_id im ToolContext. Die der
Stundenplanung (`lesson_planning`: `get_lesson_detail`, `update_lesson_phases`,
`get_unit_detail`, `finde_stunde`, `waehle_stunde`) nicht — sie prüfen den Zugang an der
Stunde, der Einheit bzw. über die eigenen Gruppen.
Schreib-Tools erzeugen Auto-Snapshots (reason='assistant').
"""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.embedding import eingabe_ohne_aliase, enqueue_embedding_job, vektor_veraltet
from app.context.stunden import als_stundenzahl
from app.chat.tools import ChatTool, ToolContext, register_tool
from app.planning import stunde_finden
from app.db.models import ContextEdge, ContextNode, Group, LessonSlot, SlotPlanSnapshot, Subject
from app.planning.curriculum_resolver import group_grade, resolve_group_curricula
from app.planning.material_edges import synchronisiere_materialkanten
from app.planning.operations import apply_operations, parse_operations
from app.planning.phasen import sichere_phasen_kennungen, uebernimm_zusatzfelder
from app.planning.permissions import zugang_zur_stunde
from app.planning.reflow_service import build_reflow_context
from app.planning.schemas import BEGRIFF_TYPEN
from app.planning.snapshots import restore_snapshot
from app.planning.student_context import get_exam_scope

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _slot_to_compact(slot: LessonSlot, ue_title: str | None = None) -> dict:
    return {
        "id": str(slot.id),
        "date": slot.date.isoformat(),
        "kw": _iso_week(slot.date),
        "periods": f"{slot.start_period}–{slot.start_period + slot.periods - 1}"
        if slot.start_period
        else f"{slot.periods} Std",
        "halbjahr": slot.halbjahr,
        "kategorie": slot.kategorie,
        "pinned": slot.pinned,
        "ue": ue_title,
        "thema": slot.thema,
        "anpassung": slot.anpassung_noetig,
    }


def _iso_week(d: date) -> int:
    return d.isocalendar()[1]


async def _load_ue_map(db: AsyncSession, group_id: int) -> dict[UUID, str]:
    """Gibt {ue_node_id: title} für alle UEs der Gruppe zurück."""
    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "unterrichtseinheit",
            ContextNode.write_scope.in_(("group", "group_teachers")),
            ContextNode.write_scope_group_id == group_id,
            ContextNode.status == "active",
        )
    )
    return {n.id: n.title for n in result.scalars().all()}


async def _build_compact_balance(db: AsyncSession, group_id: int) -> dict:
    """Gibt eine kompakte Bilanz zurück (Soll/Ist pro UE + unzugewiesen)."""
    from app.planning.router import _build_balance, _load_units

    slots_result = await db.execute(
        sa.select(LessonSlot)
        .where(LessonSlot.group_id == group_id)
        .order_by(LessonSlot.date)
    )
    slots = slots_result.scalars().all()
    units = await _load_units(db, group_id)
    balance = await _build_balance(db, group_id, units, slots)
    # ⚠️ `mode="json"`: `UnitBalanceItem.ue_node_id` ist eine UUID. Ohne den Modus kam sie als
    # Objekt heraus, `json.dumps` im Chat scheiterte, und der Antwortstrom riss ab — bei jeder
    # Gruppe mit Einheit, seit es den Jahresplanungs-Assistenten gibt (gefunden 11.10.2026).
    return balance.model_dump(mode="json")


async def _zugang(node: ContextNode, ctx: ToolContext) -> bool | None:
    """Darf diese Person den Knoten ändern (True), nur lesen (False) oder gar nicht (None)?

    ⚠️ **Die Zugangsprüfung der Stundenplanung.** `lesson_planning` greift ohne
    Gruppenbezug (`tools_for`); welche Stunde gemeint ist, sagt allein das Modell. Also
    entscheidet der Knoten, nicht die Konversation — mit derselben Regel wie die
    Entwurfsansicht (`zugang_zur_stunde`): Lehrkraft der Gruppe liest und ändert, die
    Eigentümerin ohne Mitgliedschaft liest nur. Eine Einheit trägt Gruppe und Eigentum
    genauso (`create_unit_node`) und folgt derselben Regel.

    Kein Zugang wird zu derselben Antwort wie „gibt es nicht" — sonst verriete das
    Werkzeug, welche Kennungen existieren.
    """
    try:
        return await zugang_zur_stunde(node, ctx.user, ctx.db)
    except HTTPException:
        return None


# ── get_lesson_slots ──────────────────────────────────────────────────────────


async def _handle_get_lesson_slots(args: dict, ctx: ToolContext) -> list[dict]:
    group_id = ctx.group_id
    if group_id is None:
        return {"error": "Kein Gruppenkontext"}

    db = ctx.db
    halbjahr = args.get("halbjahr")
    von_str = args.get("von")
    bis_str = args.get("bis")

    q = sa.select(LessonSlot).where(LessonSlot.group_id == group_id)
    if halbjahr:
        q = q.where(LessonSlot.halbjahr == halbjahr)
    if von_str:
        q = q.where(LessonSlot.date >= date.fromisoformat(von_str))
    if bis_str:
        q = q.where(LessonSlot.date <= date.fromisoformat(bis_str))
    q = q.order_by(LessonSlot.date, LessonSlot.start_period)

    result = await db.execute(q)
    slots = result.scalars().all()
    ue_map = await _load_ue_map(db, group_id)
    return [_slot_to_compact(s, ue_map.get(s.ue_node_id)) for s in slots]


register_tool(ChatTool(
    name="get_lesson_slots",
    groups=frozenset({"planning"}),
    writes=False,
    definition={
        "type": "function",
        "function": {
            "name": "get_lesson_slots",
            "description": (
                "Gibt die Unterrichtsstunden-Slots der Gruppe zurück. "
                "Enthält Datum, KW, Kategorie, zugewiesene UE und Thema. "
                "Nutze dieses Tool um das verfügbare Slot-Angebot zu lesen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "halbjahr": {
                        "type": "integer",
                        "enum": [1, 2],
                        "description": "Nur Slots eines Halbjahrs (optional)",
                    },
                    "von": {
                        "type": "string",
                        "description": "Startdatum ISO 8601 (optional, inkl.)",
                    },
                    "bis": {
                        "type": "string",
                        "description": "Enddatum ISO 8601 (optional, inkl.)",
                    },
                },
                "required": [],
            },
        },
    },
    handler=_handle_get_lesson_slots,
))


# ── get_curriculum_chapters ───────────────────────────────────────────────────


async def _handle_get_curriculum_chapters(args: dict, ctx: ToolContext) -> dict:
    if ctx.group_id is None:
        return {"error": "Kein Gruppenkontext"}

    resolved = await resolve_group_curricula(ctx.db, ctx.group_id)
    return {
        "grade_unbekannt": resolved.grade_unbekannt,
        "curricula": [
            {
                "curriculum": c.titel,
                "jahrgangsstufe": c.jahrgangsstufe,
                "kapitel": [
                    {
                        "id": str(k.id),
                        "titel": k.titel,
                        "std": k.std,
                        "ues": k.ues,
                    }
                    for k in c.kapitel
                ],
            }
            for c in resolved.curricula
        ],
    }


register_tool(ChatTool(
    name="get_curriculum_chapters",
    groups=frozenset({"planning"}),
    writes=False,
    definition={
        "type": "function",
        "function": {
            "name": "get_curriculum_chapters",
            "description": (
                "Gibt die Kapitel des/der zur Gruppe passenden Curriculum(s) zurück "
                "(gefiltert nach Fach und Jahrgang). Gruppiert je Curriculum; pro Kapitel "
                "Titel, Soll-Stunden (std) und bereits angelegte UE-Verknüpfungen. "
                "grade_unbekannt=true bedeutet: Jahrgang nicht ableitbar, alle Curricula "
                "des Fachs enthalten."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    handler=_handle_get_curriculum_chapters,
))


# ── get_plan_balance ──────────────────────────────────────────────────────────


async def _handle_get_plan_balance(args: dict, ctx: ToolContext) -> dict:
    group_id = ctx.group_id
    if group_id is None:
        return {"error": "Kein Gruppenkontext"}
    return await _build_compact_balance(ctx.db, group_id)


register_tool(ChatTool(
    name="get_plan_balance",
    groups=frozenset({"planning"}),
    writes=False,
    definition={
        "type": "function",
        "function": {
            "name": "get_plan_balance",
            "description": (
                "Gibt die aktuelle Soll/Ist-Bilanz des Jahresplans zurück: "
                "pro UE zugewiesene vs. geplante Stunden, Pufferstand, "
                "Gesamtzahl Slots und unzugewiesene Slots. "
                "Niemals selbst rechnen — immer dieses Tool für Bilanzzahlen nutzen."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    handler=_handle_get_plan_balance,
))


# ── create_teaching_unit ──────────────────────────────────────────────────────


async def _handle_create_teaching_unit(args: dict, ctx: ToolContext) -> dict:
    group_id = ctx.group_id
    if group_id is None:
        return {"error": "Kein Gruppenkontext"}

    titel = args.get("titel", "").strip()
    if not titel:
        return {"error": "Titel fehlt"}

    farbe = args.get("farbe")
    kapitel_str = args.get("kapitel_node_id")
    kapitel_id = UUID(kapitel_str) if kapitel_str else None

    from app.db.models import Group
    from app.planning.service import create_unit_node

    db = ctx.db
    group = await db.get(Group, group_id)
    if group is None:
        return {"error": "Gruppe nicht gefunden"}

    ue = await create_unit_node(
        db=db,
        group_id=group_id,
        group_subject_id=group.subject_id,
        user=ctx.user,
        titel=titel,
        farbe=farbe,
        kapitel_node_id=kapitel_id,
    )
    balance = await _build_compact_balance(db, group_id)
    return {"ue_node_id": str(ue.id), "titel": ue.title, "balance": balance}


register_tool(ChatTool(
    name="create_teaching_unit",
    groups=frozenset({"planning"}),
    writes=True,
    definition={
        "type": "function",
        "function": {
            "name": "create_teaching_unit",
            "description": (
                "Legt eine neue Unterrichtseinheit (UE) für den Jahresplan an. "
                "Gibt die neue ue_node_id zurück. "
                "Erstelle erst alle UEs, bevor du Slots zuweist."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "titel": {
                        "type": "string",
                        "description": "Titel der Unterrichtseinheit",
                    },
                    "kapitel_node_id": {
                        "type": "string",
                        "description": "UUID des verknüpften Lehrplan-Kapitels (optional)",
                    },
                    "farbe": {
                        "type": "integer",
                        "description": "Farb-Index 0–7 aus der UE-Palette (optional)",
                    },
                },
                "required": ["titel"],
            },
        },
    },
    handler=_handle_create_teaching_unit,
))


# ── assign_slots_to_unit ──────────────────────────────────────────────────────


async def _handle_assign_slots_to_unit(args: dict, ctx: ToolContext) -> dict:
    group_id = ctx.group_id
    if group_id is None:
        return {"error": "Kein Gruppenkontext"}

    unit_str = args.get("unit_node_id", "")
    slot_strs = args.get("slot_ids", [])
    if not unit_str or not slot_strs:
        return {"error": "unit_node_id und slot_ids erforderlich"}

    from app.planning.service import assign_slots_to_unit

    unit_id = UUID(unit_str)
    slot_ids = [UUID(s) for s in slot_strs]

    # Die ID kommt vom Modell — nur Einheiten dieser Gruppe (`zuordnung.py`).
    from app.planning.zuordnung import fehler_fuer
    fehler = await fehler_fuer(ctx.db, group_id, "ue_node_id", unit_id)
    if fehler:
        return {"error": fehler}

    updated = await assign_slots_to_unit(
        ctx.db, group_id, ctx.user, unit_id, slot_ids
    )
    balance = await _build_compact_balance(ctx.db, group_id)
    return {
        "assigned": len(updated),
        "slot_ids": [str(s.id) for s in updated],
        "balance": balance,
    }


register_tool(ChatTool(
    name="assign_slots_to_unit",
    groups=frozenset({"planning"}),
    writes=True,
    definition={
        "type": "function",
        "function": {
            "name": "assign_slots_to_unit",
            "description": (
                "Weist mehrere Slots einer UE zu (setzt ue_node_id). "
                "Löst einen Snapshot aus. Gibt aktualisierte Bilanz zurück."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "unit_node_id": {
                        "type": "string",
                        "description": "UUID der Unterrichtseinheit",
                    },
                    "slot_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Liste der Slot-UUIDs",
                    },
                },
                "required": ["unit_node_id", "slot_ids"],
            },
        },
    },
    handler=_handle_assign_slots_to_unit,
))


# ── set_slot_topics ───────────────────────────────────────────────────────────


async def _handle_set_slot_topics(args: dict, ctx: ToolContext) -> dict:
    group_id = ctx.group_id
    if group_id is None:
        return {"error": "Kein Gruppenkontext"}

    items = args.get("items", [])
    if not items:
        return {"error": "items erforderlich"}

    from app.planning.service import set_slot_topics

    updated = await set_slot_topics(ctx.db, group_id, ctx.user, items)
    return {"updated": len(updated)}


register_tool(ChatTool(
    name="set_slot_topics",
    groups=frozenset({"planning"}),
    writes=True,
    definition={
        "type": "function",
        "function": {
            "name": "set_slot_topics",
            "description": (
                "Setzt grobe Themen für mehrere Slots (Jahresplan-Stufe). "
                "Löst einen Snapshot aus."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "slot_id": {"type": "string"},
                                "thema": {"type": "string"},
                            },
                            "required": ["slot_id", "thema"],
                        },
                        "description": "Liste aus {slot_id, thema}",
                    },
                },
                "required": ["items"],
            },
        },
    },
    handler=_handle_set_slot_topics,
))


# ── set_slot_category ─────────────────────────────────────────────────────────


async def _handle_set_slot_category(args: dict, ctx: ToolContext) -> dict:
    group_id = ctx.group_id
    if group_id is None:
        return {"error": "Kein Gruppenkontext"}

    slot_str = args.get("slot_id", "")
    kategorie = args.get("kategorie", "")
    if not slot_str or not kategorie:
        return {"error": "slot_id und kategorie erforderlich"}

    from app.planning.service import set_slot_category

    try:
        slot = await set_slot_category(
            ctx.db, group_id, ctx.user, UUID(slot_str), kategorie
        )
    except ValueError as e:
        return {"error": str(e)}

    return {"slot_id": str(slot.id), "kategorie": slot.kategorie}


register_tool(ChatTool(
    name="set_slot_category",
    groups=frozenset({"planning"}),
    writes=True,
    definition={
        "type": "function",
        "function": {
            "name": "set_slot_category",
            "description": (
                "Setzt die Kategorie eines Slots auf pruefung, puffer, vertretung "
                "oder zurück auf unterricht. "
                "Einen Ausfall trägt apply_plan_operations mit cancel_lesson ein — "
                "puffer ist eine Reservestunde, die stattfindet, kein Ausfall. "
                "Pinned-Status wird vom Assistenten nie gesetzt."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slot_id": {"type": "string", "description": "UUID des Slots"},
                    "kategorie": {
                        "type": "string",
                        "enum": ["unterricht", "pruefung", "puffer", "vertretung"],
                    },
                },
                "required": ["slot_id", "kategorie"],
            },
        },
    },
    handler=_handle_set_slot_category,
))


# ── Kapitel und Zusammenhang einer Stunde (0.15) ──────────────────────────────


async def _kapitel_der_einheit(db: AsyncSession, unit_id: UUID) -> UUID | None:
    """Das Curriculum-Kapitel, auf das die Einheit verweist (UE↔Kapitel-Picker)."""
    return (await db.execute(
        sa.select(ContextEdge.to_node_id)
        .join(ContextNode, ContextNode.id == ContextEdge.to_node_id)
        .where(
            ContextEdge.from_node_id == unit_id,
            ContextEdge.relation == "references",
            ContextNode.content_type == "kapitel",
        )
    )).scalars().first()


async def _kapitel(ctx: ToolContext, kapitel_id: UUID) -> dict | None:
    """Ein Kapitel des Schulcurriculums: Curriculum, Bildungsplan-Fassung und die
    Lernsequenzen samt ihren inhaltsbezogenen Kompetenzen.

    Die Kompetenzen stehen in der Form von `refs` am Stundenentwurf (`LessonRefItem`), damit
    sie sich nach Zustimmung unverändert übernehmen lassen. Gelesen wie in
    `load_curriculum_tree`: über die Kanten `references`, archivierte IK-Knoten
    eingeschlossen — ein Curriculum verweist teils auf Knoten eines älteren Imports.

    ⚠️ Bis 0.15 las `get_unit_detail` die Lernsequenzen aus `metadata.lernsequenzen` am
    Kapitel. Das Feld gibt es nicht — Lernsequenzen sind eigene Knoten —, geliefert wurde
    immer eine leere Liste.
    """
    from app.context.visibility import read_scope_clause

    db = ctx.db
    kap = (await db.execute(
        sa.select(ContextNode).where(
            ContextNode.id == kapitel_id,
            ContextNode.content_type == "kapitel",
            ContextNode.status == "active",
            read_scope_clause(ctx.user.sub, getattr(ctx.user, "roles", None) or ()),
        )
    )).scalar_one_or_none()
    if kap is None:
        return None

    curriculum = (await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.to_node_id == ContextNode.id)
        .where(
            ContextEdge.from_node_id == kap.id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "curriculum",
            ContextNode.status == "active",
        )
    )).scalars().first()
    sequenzen = (await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(
            ContextEdge.to_node_id == kap.id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "lernsequenz",
            ContextNode.status == "active",
        )
        .order_by(ContextNode.metadata_["reihenfolge"].as_integer().nullslast(), ContextNode.title)
    )).scalars().all()

    kompetenzen: dict[UUID, list[dict]] = {}
    if sequenzen:
        for ls_id, k_id, titel, nr, partiell in (await db.execute(
            sa.select(
                ContextEdge.from_node_id, ContextNode.id, ContextNode.title,
                ContextNode.metadata_["kompetenz_nr"].as_string(),
                ContextEdge.metadata_["partiell"].as_string(),
            )
            .join(ContextNode, ContextNode.id == ContextEdge.to_node_id)
            .where(
                ContextEdge.from_node_id.in_([s.id for s in sequenzen]),
                ContextEdge.relation == "references",
                ContextNode.content_type == "ik_kompetenz",
            )
            .order_by(ContextNode.title)
        )).all():
            eintrag = {"node_id": str(k_id), "typ": "ik", "code": nr, "titel": titel}
            if partiell == "true":
                eintrag["partiell"] = True
            kompetenzen.setdefault(ls_id, []).append(eintrag)

    cur_meta = (curriculum.metadata_ or {}) if curriculum else {}
    return {
        "id": str(kap.id),
        "titel": kap.title,
        "std": als_stundenzahl((kap.metadata_ or {}).get("std")),
        "curriculum": curriculum.title if curriculum else None,
        "bildungsplan": cur_meta.get("bp_version"),
        "jahrgangsstufe": cur_meta.get("jahrgangsstufe"),
        "lernsequenzen": [
            {
                "titel": s.title,
                "std": als_stundenzahl((s.metadata_ or {}).get("std")),
                "kompetenzen": kompetenzen.get(s.id, []),
            }
            for s in sequenzen
        ],
    }


async def _zusammenhang(ctx: ToolContext, stunde: ContextNode) -> dict:
    """Wo die Stunde steht: Fach, Gruppe, Jahrgang, Einheit und — über deren Kapitel — das
    Curriculum mit Bildungsplan-Fassung, Lernsequenzen und Kompetenzen. Ohne Kapitel die
    Curricula, die zu Fach und Jahrgang der Gruppe passen.

    Ohne das suchte das Modell blind (Untersuchung „Kompetenz vorschlagen", 10.10.2026):
    Der Entwurf nannte weder Fach noch Jahrgang noch Einheit; das Modell riet die Stufe,
    mischte Kurs- und Mittelstufe und konnte `get_unit_detail` aus der Stunde heraus gar
    nicht rufen. Die Einheit kommt über `part_of`, wie in der Entwurfsansicht.
    """
    db = ctx.db
    gruppe = await db.get(Group, stunde.write_scope_group_id) if stunde.write_scope_group_id else None
    fach = await db.get(Subject, stunde.subject_id) if stunde.subject_id else None
    einheit = (await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.to_node_id == ContextNode.id)
        .where(
            ContextEdge.from_node_id == stunde.id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "unterrichtseinheit",
            ContextNode.status == "active",
        )
    )).scalars().first()
    kapitel_id = await _kapitel_der_einheit(db, einheit.id) if einheit else None
    kapitel = await _kapitel(ctx, kapitel_id) if kapitel_id else None

    zusammenhang: dict = {
        "fach": fach.name if fach else None,
        "gruppe": (gruppe.display_name or gruppe.name) if gruppe else None,
        "jahrgang": None,
        "einheit": {"id": str(einheit.id), "titel": einheit.title} if einheit else None,
        "kapitel": kapitel,
    }
    if gruppe is not None and kapitel is None:
        aufgeloest = await resolve_group_curricula(db, gruppe.id)
        zusammenhang["jahrgang"] = aufgeloest.grade
        zusammenhang["curricula"] = [
            {"titel": c.titel, "jahrgangsstufe": c.jahrgangsstufe, "bildungsplan": c.bildungsplan}
            for c in aufgeloest.curricula
        ]
    elif gruppe is not None:
        zusammenhang["jahrgang"] = await group_grade(db, gruppe.id)
    return zusammenhang


# ── get_unit_detail ───────────────────────────────────────────────────────────


async def _handle_get_unit_detail(args: dict, ctx: ToolContext) -> dict:
    unit_str = args.get("unit_node_id", "")
    if not unit_str:
        return {"error": "unit_node_id erforderlich"}

    db = ctx.db
    try:
        unit_id = UUID(unit_str)
    except ValueError:
        return {"error": "Ungültige unit_node_id"}

    unit = await db.get(ContextNode, unit_id)
    if unit is None or unit.status != "active" or unit.content_type != "unterrichtseinheit":
        return {"error": "UE nicht gefunden"}
    # Am Knoten geprüft, nicht an der Gruppe der Konversation: Die Stundenplanung hat
    # keine, und mit Gruppe galt bisher jede Einheit, deren Kennung das Modell nannte.
    if await _zugang(unit, ctx) is None:
        return {"error": "UE nicht gefunden"}
    group_id = unit.write_scope_group_id

    # Kapitel-Verknüpfung
    kapitel_id = await _kapitel_der_einheit(db, unit_id)
    chapter_info = await _kapitel(ctx, kapitel_id) if kapitel_id else None

    # Zugewiesene Slots
    slots_result = await db.execute(
        sa.select(LessonSlot)
        .where(LessonSlot.ue_node_id == unit_id, LessonSlot.group_id == group_id)
        .order_by(LessonSlot.date)
    )
    slots = slots_result.scalars().all()

    # Stunden
    lessons_result = await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(
            ContextEdge.to_node_id == unit_id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "unterrichtsstunde",
            ContextNode.status == "active",
        )
    )
    lessons = lessons_result.scalars().all()

    return {
        "id": str(unit.id),
        "titel": unit.title,
        "kapitel": chapter_info,
        "slots": [
            {
                "id": str(s.id),
                "date": s.date.isoformat(),
                "periods": s.periods,
                "thema": s.thema,
                "stunde_node_id": str(s.stunde_node_id) if s.stunde_node_id else None,
            }
            for s in slots
        ],
        "stunden": [
            {"id": str(l.id), "titel": l.title}
            for l in lessons
        ],
    }


register_tool(ChatTool(
    name="get_unit_detail",
    groups=frozenset({"planning", "lesson_planning"}),
    writes=False,
    definition={
        "type": "function",
        "function": {
            "name": "get_unit_detail",
            "description": (
                "Gibt Detailinfos zu einer Unterrichtseinheit: Kapitel des "
                "Schulcurriculums mit Bildungsplan-Fassung und Lernsequenzen samt "
                "Kompetenzen, zugewiesene Slots und bereits angelegte Stunden."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "unit_node_id": {
                        "type": "string",
                        "description": "UUID der Unterrichtseinheit",
                    },
                },
                "required": ["unit_node_id"],
            },
        },
    },
    handler=_handle_get_unit_detail,
))


# ── create_lessons ────────────────────────────────────────────────────────────


async def _handle_create_lessons(args: dict, ctx: ToolContext) -> dict:
    group_id = ctx.group_id
    if group_id is None:
        return {"error": "Kein Gruppenkontext"}

    unit_str = args.get("unit_node_id", "")
    items = args.get("items", [])
    if not unit_str or not items:
        return {"error": "unit_node_id und items erforderlich"}

    db = ctx.db
    unit_id = UUID(unit_str)
    unit = await db.get(ContextNode, unit_id)
    if unit is None or unit.status != "active" or unit.content_type != "unterrichtseinheit":
        return {"error": "UE nicht gefunden"}

    from app.planning.snapshots import create_snapshot
    from datetime import datetime, timezone

    await create_snapshot(db, group_id, reason="assistant", created_by=ctx.user.sub)

    # Letzten vorhandenen Vorgänger ermitteln
    last_result = await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(
            ContextEdge.to_node_id == unit_id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "unterrichtsstunde",
            ContextNode.status == "active",
        )
        .order_by(ContextNode.created_at.desc())
        .limit(1)
    )
    predecessor = last_result.scalar_one_or_none()

    created = []
    now = datetime.now(timezone.utc)
    for item in items:
        titel = (item.get("titel") or "").strip()
        if not titel:
            continue

        stunde = ContextNode(
            category="artifact",
            content_type="unterrichtsstunde",
            title=titel,
            read_scope="group_teachers",
            write_scope="group_teachers",
            read_scope_group_id=group_id,
            write_scope_group_id=group_id,
            owner_pseudonym=ctx.user.sub,
            subject_id=unit.subject_id,
            metadata_={"phasen": [], "refs": item.get("refs", [])},
            status="active",
        )
        db.add(stunde)
        await db.flush()

        db.add(ContextEdge(
            from_node_id=stunde.id, to_node_id=unit_id, relation="part_of", metadata_={}
        ))
        if predecessor:
            db.add(ContextEdge(
                from_node_id=stunde.id, to_node_id=predecessor.id, relation="follows", metadata_={}
            ))

        slot_str = item.get("slot_id")
        if slot_str:
            slot = await db.get(LessonSlot, UUID(slot_str))
            if slot and slot.group_id == group_id:
                slot.stunde_node_id = stunde.id
                slot.updated_at = now

        predecessor = stunde
        created.append({"id": str(stunde.id), "titel": stunde.title})

    await db.commit()
    return {"created": len(created), "stunden": created}


register_tool(ChatTool(
    name="create_lessons",
    groups=frozenset({"planning"}),
    writes=True,
    definition={
        "type": "function",
        "function": {
            "name": "create_lessons",
            "description": (
                "Legt Stunden-Knoten für eine UE an und verknüpft sie optional mit Slots. "
                "Erstellt eine follows-Kette. Löst einen Snapshot aus."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "unit_node_id": {
                        "type": "string",
                        "description": "UUID der Unterrichtseinheit",
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "titel": {"type": "string"},
                                "slot_id": {"type": "string", "description": "UUID des Slots (optional)"},
                                "refs": {
                                    "type": "array",
                                    "items": {"type": "object"},
                                    "description": "IK/PK-Refs (optional)",
                                },
                            },
                            "required": ["titel"],
                        },
                        "description": "Liste der anzulegenden Stunden",
                    },
                },
                "required": ["unit_node_id", "items"],
            },
        },
    },
    handler=_handle_create_lessons,
))


# ── get_lesson_detail ─────────────────────────────────────────────────────────


_OHNE_STUNDE = "node_id erforderlich — die Unterhaltung hat keine Bezugsstunde"


def _stunden_kennung(args: dict, ctx: ToolContext) -> str:
    """Die genannte Kennung, sonst die Bezugsstunde der Konversation, sonst leer."""
    if args.get("node_id"):
        return args["node_id"]
    return str(ctx.stunde_node_id) if ctx.stunde_node_id else ""


async def _vokabular(ctx: ToolContext, fach_id: int | None) -> dict:
    """Sozialformen und Methoden, die diese Person lesen darf — samt Aliasen.

    Kommt mit dem Entwurf, damit das Modell nicht jeden Begriff einzeln nachschlägt: In der
    Messung zu Schritt 6 (10.10.2026) suchte es nach dem Lesen fünfmal mit
    `search_context_nodes`, und die sechs Werkzeugrunden des Chats waren verbraucht, bevor
    es schreiben konnte — die Lehrkraft bekam eine leere Antwort. Das Vokabular ist klein
    (heute 20 Einträge). Fachgebundene Einträge nur aus dem Fach der Stunde; was andere
    Fachschaften pflegen, wäre hier Rauschen.
    """
    from app.context.visibility import read_scope_clause
    from app.db.models import NodeAlias

    zeilen = (await ctx.db.execute(
        sa.select(ContextNode.id, ContextNode.title, ContextNode.content_type)
        .where(
            ContextNode.content_type.in_(("sozialform", "methode")),
            ContextNode.status == "active",
            read_scope_clause(ctx.user.sub, getattr(ctx.user, "roles", None) or ()),
            sa.or_(ContextNode.subject_id.is_(None), ContextNode.subject_id == fach_id),
        )
        .order_by(ContextNode.title)
    )).all()
    aliase: dict = {}
    if zeilen:
        for node_id, alias in (await ctx.db.execute(
            sa.select(NodeAlias.node_id, NodeAlias.alias)
            .where(NodeAlias.node_id.in_([z[0] for z in zeilen]))
        )).all():
            aliase.setdefault(node_id, []).append(alias)
    vokabular: dict = {"sozialformen": [], "methoden": []}
    for node_id, titel, art in zeilen:
        eintrag = {"node_id": str(node_id), "titel": titel}
        if aliase.get(node_id):
            eintrag["aliase"] = sorted(aliase[node_id])
        vokabular["sozialformen" if art == "sozialform" else "methoden"].append(eintrag)
    return vokabular


#: So viele Begriffe kommen nach Ähnlichkeit mit dem Entwurf (Plan F3). Bewusst ohne
#: Schwelle: Das Modell wählt aus, und ob ein Band wie bei der Vorab-Suche nötig ist, zeigt
#: erst die Messung. Kosten: rund 3 000 Zeichen je Aufruf (vier Dev-Stunden, 16.10.2026:
#: 2 800–3 300), rund ein Viertel davon Kennungen — so viel wie `zusammenhang`.
BEGRIFFE_ANZAHL = 15

#: Je Phasenbeschreibung höchstens so viel Text im Vergleich — eine lange Beschreibung
#: soll die Auswahl nicht allein bestimmen.
_BESCHREIBUNG_MAX = 300


def _vergleichstext(stunde: ContextNode, meta: dict, zusammenhang: dict) -> str:
    """Womit die Begriffe der Stunde verglichen werden: der Entwurf, wie er gerade ist.

    Titel, Stundenziel, Phasen (Name und gekürzte Beschreibung), Einheit und Kapitel.
    **Nicht der gespeicherte Stundenvektor:** Eine neue Stunde hat noch keinen, und er trägt
    das Thema ohne die Phasen (`embedding_input`). Welche Begriffe eine Stunde einführt, steht
    aber gerade in den Phasen.
    """
    teile = [stunde.title, meta.get("stundenziel")]
    for phase in meta.get("phasen") or []:
        if isinstance(phase, dict):
            teile.append(phase.get("name"))
            beschreibung = phase.get("beschreibung")
            if isinstance(beschreibung, str):
                teile.append(beschreibung[:_BESCHREIBUNG_MAX])
    teile.append((zusammenhang.get("einheit") or {}).get("titel"))
    teile.append((zusammenhang.get("kapitel") or {}).get("titel"))
    return "\n".join(t.strip() for t in teile if isinstance(t, str) and t.strip())


async def _begriffe(ctx: ToolContext, stunde: ContextNode, meta: dict, zusammenhang: dict) -> dict:
    """Die Fachbegriffe, die zum Entwurf passen — aus dem Fach und seinen Bezugsfächern.

    Kommt mit dem Entwurf wie `vokabular`, aber nicht vollständig: Chemie allein hat über
    hundert Begriffe. Ausgewählt wird nach Ähnlichkeit mit :func:`_vergleichstext`; die
    nächsten :data:`BEGRIFFE_ANZAHL`, die die Person lesen darf. Bezugsfächer gehören dazu
    (seit 0.16 pflegt das Leitfach einen geteilten Begriff): Eine NwT-Stunde zur
    Chromatografie führt einen Begriff der Chemie ein.

    Was schon als Begriff in `refs` steht, steht **immer** vorn (``eingetragen``) — das Modell
    schreibt `refs` als ganze Liste und soll es behalten, auch wenn es nicht unter den
    nächsten ist. Ohne Vektor (Einbettungsdienst nicht erreichbar) kommen nur diese, mit
    ``hinweis``: Dann bleibt die Suche.
    """
    from app.context.search import vektor_oder_none
    from app.context.service import bezugsfaecher_von
    from app.context.visibility import read_scope_clause
    from app.db.models import NodeAlias

    db = ctx.db
    eintraege: list[dict] = []
    gesehen: set[str] = set()
    for ref in meta.get("refs") or []:
        if isinstance(ref, dict) and ref.get("typ") == "concept" and ref.get("node_id"):
            node_id = str(ref["node_id"])
            if node_id not in gesehen:
                gesehen.add(node_id)
                eintraege.append({"node_id": node_id, "titel": ref.get("titel"), "eingetragen": True})

    if stunde.subject_id is None:
        return {"eintraege": eintraege,
                "hinweis": "Die Stunde hat kein Fach — Begriffe nur über search_context_nodes."}
    vektor = await vektor_oder_none(_vergleichstext(stunde, meta, zusammenhang))
    if vektor is None:
        return {"eintraege": eintraege,
                "hinweis": ("Die Auswahl nach Ähnlichkeit ist gerade nicht verfügbar — "
                            "Begriffe über search_context_nodes suchen.")}

    bezug = await bezugsfaecher_von(db, stunde.subject_id)
    bedingungen = [
        ContextNode.content_type.in_(BEGRIFF_TYPEN),
        ContextNode.status == "active",
        read_scope_clause(ctx.user.sub, getattr(ctx.user, "roles", None) or ()),
        ContextNode.subject_id.in_((stunde.subject_id, *bezug)),
        ContextNode.embedding.is_not(None),
    ]
    if gesehen:
        bedingungen.append(ContextNode.id.not_in([UUID(i) for i in gesehen]))
    treffer = (await db.execute(
        sa.select(ContextNode.id, ContextNode.title, ContextNode.subject_id,
                  ContextNode.metadata_["fassung"].as_string())
        .where(*bedingungen)
        .order_by(ContextNode.embedding.cosine_distance(vektor), ContextNode.id)
        .limit(BEGRIFFE_ANZAHL)
    )).all()

    aliase: dict = {}
    faecher: dict = {}
    if treffer:
        for node_id, alias in (await db.execute(
            sa.select(NodeAlias.node_id, NodeAlias.alias)
            .where(NodeAlias.node_id.in_([t[0] for t in treffer]))
        )).all():
            aliase.setdefault(node_id, []).append(alias)
        if bezug:
            faecher = dict((await db.execute(
                sa.select(Subject.id, Subject.name).where(Subject.id.in_(bezug))
            )).all())
    for node_id, titel, fach_id, fassung in treffer:
        eintrag = {"node_id": str(node_id), "titel": titel}
        # Gleichnamige Begriffe gibt es je Stufe zweimal („Oxidation" in Klasse 8 und 10).
        if fassung:
            eintrag["fassung"] = fassung
        if aliase.get(node_id):
            eintrag["aliase"] = sorted(aliase[node_id])
        if fach_id != stunde.subject_id:
            eintrag["fach"] = faecher.get(fach_id)
        eintraege.append(eintrag)
    return {"eintraege": eintraege}


async def _handle_get_lesson_detail(args: dict, ctx: ToolContext) -> dict:
    node_str = _stunden_kennung(args, ctx)
    if not node_str:
        return {"error": _OHNE_STUNDE}

    db = ctx.db
    node = await db.get(ContextNode, UUID(node_str))
    if node is None or node.status != "active" or node.content_type != "unterrichtsstunde":
        return {"error": "Stunde nicht gefunden"}
    if await _zugang(node, ctx) is None:
        return {"error": "Stunde nicht gefunden"}

    meta = node.metadata_ or {}
    slot_result = await db.execute(
        sa.select(LessonSlot).where(LessonSlot.stunde_node_id == node.id)
    )
    slot = slot_result.scalar_one_or_none()

    zusammenhang = await _zusammenhang(ctx, node)
    return {
        "id": str(node.id),
        "titel": node.title,
        "stundenziel": meta.get("stundenziel", ""),
        "phasen": meta.get("phasen", []),
        "refs": meta.get("refs", []),
        "slot": {
            "date": slot.date.isoformat(),
            "periods": slot.periods,
            "verfuegbare_min": slot.periods * 45,
        } if slot else None,
        "zusammenhang": zusammenhang,
        "vokabular": await _vokabular(ctx, node.subject_id),
        "begriffe": await _begriffe(ctx, node, meta, zusammenhang),
    }


register_tool(ChatTool(
    name="get_lesson_detail",
    groups=frozenset({"lesson_planning"}),
    writes=False,
    definition={
        "type": "function",
        "function": {
            "name": "get_lesson_detail",
            "description": (
                "Gibt den vollständigen Stundenentwurf zurück: Titel, Stundenziel, "
                "Phasen-Array, Kompetenzen und Slot-Kontext. Dazu zusammenhang: Fach, "
                "Gruppe, jahrgang (null = unbekannt), die Unterrichtseinheit und — wenn sie "
                "auf ein Kapitel des Schulcurriculums verweist — dessen Curriculum, "
                "Bildungsplan-Fassung und Lernsequenzen mit ihren Kompetenzen (in der Form "
                "von refs); ohne Kapitel die Curricula, die zu Fach und Jahrgang der Gruppe "
                "passen. Und das Vokabular der Sozialformen und Methoden (node_id, titel, "
                "aliase), aus dem sozialform und methode als Knoten eingetragen werden. Und "
                "begriffe: die zur Stunde passenden Fachbegriffe des Fachs und seiner "
                "Bezugsfächer (node_id, titel, aliase, fach nur beim Bezugsfach; eingetragen = "
                "steht schon in refs), aus denen Begriffe der Stunde als refs mit "
                "typ 'concept' eingetragen werden."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": (
                            "UUID der Unterrichtsstunde; ohne Angabe die Bezugsstunde "
                            "der Unterhaltung"
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    handler=_handle_get_lesson_detail,
))


# ── update_lesson_phases ──────────────────────────────────────────────────────


def _phasen_pruefen(phasen) -> tuple[list[dict] | None, str | None]:
    """Die Phasen des Modells nach der Regel des Planers (`LessonPhaseItem`). → (Phasen, Fehler)

    Bis 0.15 prüfte das Werkzeug nur `prio`; `"minimum": 1` für die Dauer stand allein im
    Schema, als Bitte an das Modell. Ein `dauer_min: 0` oder `"zehn"` landete so in den
    Metadaten. Jetzt gilt dasselbe wie beim Speichern im Planer: Dauer fehlt oder `null`
    (offen) oder 1–480, Name nicht leer, bekannte Prio.

    Zurück kommen die Phasen **so, wie der Planer sie speichert** (`model_dump`, alle
    Schemafelder): Eine weggelassene Dauer steht dann als `null` da, nicht als fehlender
    Schlüssel — zwei Wege, eine Form.
    """
    from app.planning.schemas import LessonPhaseItem

    if not isinstance(phasen, list):
        return None, "phasen muss eine Liste von Phasen sein"
    geprueft: list[dict] = []
    for nr, phase in enumerate(phasen, 1):
        name = phase.get("name") if isinstance(phase, dict) else None
        wo = f"Phase {nr}" + (f" („{name}“)" if name else "")
        try:
            item = LessonPhaseItem.model_validate(phase)
            item.validate_prio()
        except ValidationError as e:
            fehler = e.errors()[0]
            feld = ".".join(str(t) for t in fehler["loc"]) or "Phase"
            if feld == "dauer_min":
                return None, (f"{wo}: dauer_min muss zwischen 1 und 480 liegen — ohne Dauer "
                              "das Feld weglassen, nie 0.")
            return None, f"{wo}: {feld} — {fehler['msg']}"
        except ValueError as e:
            return None, f"{wo}: {e}"
        geprueft.append(item.model_dump(exclude_none=False, mode="json"))
    return geprueft, None


def _nachbereitete_fehlen(gespeichert, neu: list[dict]) -> str | None:
    """Fehlt im neuen Array eine nachbereitete Phase? → Fehlertext, sonst None.

    Eine Phase mit Nachbereitungsstatus („erledigt", „offen", „gestrichen") ist Geschichte:
    Reflow, Übertrag und Kompetenzverlauf hängen an ihrem Status, und der reist über die
    Kennung (`uebernimm_zusatzfelder`). Schreibt das Modell sie ohne Kennung neu — beim
    Zusammenlegen tat es das in 10 von 10 Läufen, auch gegen ausdrückliche Anweisung
    (Messung zu Schritt 3, 10.10.2026) —, wäre der Status still weg. Deshalb wird der Aufruf
    abgewiesen. Ändern bleibt erlaubt, mit Kennung; entfernen geht in der Entwurfsansicht.
    Übertragene Phasen („geplant") sind nicht geschützt: Sie zu streichen ist Planung.
    """
    from app.planning.review_service import NACHBEREITUNG_STATI

    neue_ids = {p.get("id") for p in neu if isinstance(p, dict) and p.get("id")}
    fehlend = [
        p for p in (gespeichert or [])
        if isinstance(p, dict) and p.get("status") in NACHBEREITUNG_STATI
        and p.get("id") not in neue_ids
    ]
    if not fehlend:
        return None
    namen = ", ".join(f"„{p.get('name')}“ ({p.get('status')})" for p in fehlend)
    return (f"Nicht gespeichert: Nachbereitete Phasen fehlen — {namen}. Sie lassen sich "
            "ändern (mit ihrer id aus get_lesson_detail), aber nicht entfernen, ersetzen oder "
            "zusammenlegen. Nimm eine zusammengelegte oder ersetzende neue Phase wieder heraus "
            "und ändere die nachbereiteten einzeln — oder sag der Lehrkraft, dass sich eine "
            "nachbereitete Phase nur in der Entwurfsansicht entfernen lässt.")


# typ → welche Bausteinarten der Knoten dazu sein darf.
_REF_TYPEN = {"ik": ("ik_kompetenz",), "pk": ("pk_kompetenz",), "concept": BEGRIFF_TYPEN}

# Bausteinart → typ des Eintrags in `refs` (Umkehrung von `_REF_TYPEN`).
_REF_TYP_ZU = {art: typ for typ, arten in _REF_TYPEN.items() for art in arten}


async def _refs_pruefen(ctx: ToolContext, refs) -> tuple[list[dict] | None, str | None]:
    """Kompetenzen und Begriffe des Modells nach der Regel des Planers (`LessonRefItem`).
    → (Refs, Fehler)

    Bis 0.15 schrieb das Werkzeug `refs` ungeprüft in die Metadaten — anders als die Phasen.
    Ein unbekannter `typ` verschwand dann still aus der Kompetenzleiste, die nach ik/pk
    filtert; eine erfundene Kennung stand als Kompetenz ohne Knoten da.

    Geprüft wird die Form, ein bekannter `typ` und dass es den Knoten gibt, passend zum Typ
    und für die Person lesbar. Ein Begriff (`concept`) ist ein Knoten aus `BEGRIFF_TYPEN` —
    bis 0.17 galt die ganze Kategorie, samt Bauteil und Arduino-Funktion. **Titel und Nummer
    kommen aus dem Knoten**, nicht vom Modell: In der Leiste steht der Wortlaut des
    Bildungsplans. Doppelte entfallen. Archivierte Knoten zählen — ein Curriculum verweist
    teils auf Knoten eines älteren Imports.
    """
    from app.context.visibility import read_scope_clause
    from app.planning.schemas import LessonRefItem

    if not isinstance(refs, list):
        return None, "refs muss eine Liste von Kompetenzen und Begriffen sein"
    items = []
    for nr, ref in enumerate(refs, 1):
        try:
            item = LessonRefItem.model_validate(ref)
        except ValidationError as e:
            fehler = e.errors()[0]
            feld = ".".join(str(t) for t in fehler["loc"]) or "Eintrag"
            return None, f"refs, Eintrag {nr}: {feld} — {fehler['msg']}"
        if item.typ not in _REF_TYPEN:
            return None, f"refs, Eintrag {nr}: typ muss ik, pk oder concept sein"
        items.append(item)

    knoten = {}
    if items:
        knoten = {n.id: n for n in (await ctx.db.execute(
            sa.select(ContextNode).where(
                ContextNode.id.in_([i.node_id for i in items]),
                read_scope_clause(ctx.user.sub, getattr(ctx.user, "roles", None) or ()),
            )
        )).scalars()}

    geprueft: list[dict] = []
    gesehen: set = set()
    for nr, item in enumerate(items, 1):
        n = knoten.get(item.node_id)
        if n is None or n.content_type not in _REF_TYPEN[item.typ]:
            if item.typ == "concept":
                return None, (f"refs, Eintrag {nr}: kein passender Begriff mit node_id "
                              f"{item.node_id} — übernimm Begriffe aus begriffe oder einem "
                              "Treffer; fehlt ein Begriff im Wissensspeicher, trag ihn nicht ein")
            return None, (f"refs, Eintrag {nr}: keine passende Kompetenz mit node_id "
                          f"{item.node_id} — übernimm Kompetenzen so, wie sie im Kapitel "
                          "oder im Treffer stehen")
        if item.node_id in gesehen:
            continue
        gesehen.add(item.node_id)
        item.titel = n.title
        if item.typ == "concept":
            # Ein Begriff hat keine Nummer; eine vom Modell mitgeschickte stünde sonst in der
            # Leiste an seiner Stelle.
            item.code = None
            item.content_type = n.content_type
        else:
            item.code = (n.metadata_ or {}).get("kompetenz_nr") or item.code
        geprueft.append(item.model_dump(mode="json"))
    return geprueft, None


async def _handle_update_lesson_phases(args: dict, ctx: ToolContext) -> dict:
    node_str = _stunden_kennung(args, ctx)
    phasen = args.get("phasen")
    if phasen is None:
        return {"error": "phasen erforderlich"}
    if not node_str:
        return {"error": _OHNE_STUNDE}

    db = ctx.db
    node = await db.get(ContextNode, UUID(node_str))
    if node is None or node.status != "active" or node.content_type != "unterrichtsstunde":
        return {"error": "Stunde nicht gefunden"}
    darf_aendern = await _zugang(node, ctx)
    if darf_aendern is None:
        return {"error": "Stunde nicht gefunden"}
    if not darf_aendern:
        return {"error": "Stunde nur lesbar: keine Lehrkraft der Gruppe"}
    # Snapshot und Rückgängig gehören der Gruppe der Stunde, nicht der Konversation.
    group_id = node.write_scope_group_id

    from app.planning.snapshots import create_snapshot
    from datetime import datetime, timezone

    # Vor dem Snapshot: Ein abgewiesener Aufruf hinterlässt keinen Rückgängig-Schritt.
    phasen, fehler = _phasen_pruefen(phasen)
    if fehler:
        return {"error": fehler}
    fehler = _nachbereitete_fehlen((node.metadata_ or {}).get("phasen"), phasen)
    if fehler:
        return {"error": fehler}
    refs = args.get("refs")
    if refs is not None:
        refs, fehler = await _refs_pruefen(ctx, refs)
        if fehler:
            return {"error": fehler}

    await create_snapshot(db, group_id, reason="assistant", created_by=ctx.user.sub)

    vektor_vorher = eingabe_ohne_aliase(node)
    meta = dict(node.metadata_ or {})
    # Der Assistent liefert Roh-Dicts aus den Werkzeug-Argumenten und geht nicht
    # durch `LessonPhaseItem` — ohne diesen Schritt hätten seine Phasen nie eine
    # Kennung, und `phasen_status`, Übertragung und Materialkanten liefen still
    # ins Leere.
    # Dieselbe Regel wie beim Speichern im Planer: Was die Nachbereitung und die
    # Operationen an einer Phase vermerkt haben, überlebt (`uebernimm_zusatzfelder`).
    phasen = sichere_phasen_kennungen(uebernimm_zusatzfelder(phasen, meta.get("phasen")))
    meta["phasen"] = phasen
    stundenziel = args.get("stundenziel")
    if stundenziel is not None:
        meta["stundenziel"] = stundenziel
    if refs is not None:
        meta["refs"] = refs

    node.metadata_ = meta
    node.updated_at = datetime.now(timezone.utc)
    await synchronisiere_materialkanten(db, node.id, meta)
    # `refs` stehen im Vektor der Stunde, die Phasen nicht (`embedding_input`).
    veraltet = vektor_veraltet(node, vektor_vorher)
    await db.commit()
    if veraltet:
        await enqueue_embedding_job(node.id, db)

    # Kompetenz-Sog: nur aus verknüpften Material-Knoten. Methode/Sozialform sind
    # kontrolliertes Vokabular ohne eigene Kompetenzen.
    new_node_ids = set()
    for p in phasen:
        for mat in (p.get("material") or []):
            if mat.get("typ") == "node" and mat.get("node_id"):
                new_node_ids.add(mat["node_id"])

    suggested_refs = []
    existing_ref_ids = {str(r.get("node_id")) for r in (meta.get("refs") or [])}
    dismissed = set(meta.get("refs_dismissed") or [])

    for nid_str in new_node_ids:
        if nid_str in existing_ref_ids or nid_str in dismissed:
            continue
        try:
            edges_result = await db.execute(
                sa.select(ContextEdge).where(
                    ContextEdge.from_node_id == UUID(nid_str),
                    ContextEdge.relation.in_(["references", "develops"]),
                )
            )
            for edge in edges_result.scalars().all():
                comp = await db.get(ContextNode, edge.to_node_id)
                # Bis 0.17 stand hier `"concept"` unter den Bausteinarten — das ist eine
                # Kategorie, keine Art; ein Begriff fiel durch.
                if comp and comp.content_type in _REF_TYP_ZU:
                    comp_id = str(comp.id)
                    if comp_id not in existing_ref_ids and comp_id not in dismissed:
                        suggested_refs.append({
                            "node_id": comp_id,
                            "typ": _REF_TYP_ZU[comp.content_type],
                            "titel": comp.title,
                            "partiell": False,
                            "quelle": nid_str,
                        })
        except Exception:
            pass

    return {
        "ok": True,
        "suggested_refs": suggested_refs[:10],
    }


register_tool(ChatTool(
    name="update_lesson_phases",
    groups=frozenset({"lesson_planning"}),
    writes=True,
    definition={
        "type": "function",
        "function": {
            "name": "update_lesson_phases",
            "description": (
                "Schreibt das Phasen-Array einer Stunde — immer das ganze: Eine Phase, die "
                "fehlt, ist danach gelöscht. Regeln: (1) Bestehende Phasen behalten ihre id "
                "aus get_lesson_detail unverändert; neue Phasen ohne id. Legst du Phasen "
                "zusammen, trägt die zusammengelegte die id der ersten — auch wenn sie neu "
                "heißt. Phasen mit status (nachbereitet) bleiben mit ihrer id im Array; "
                "fehlt eine, wird der Aufruf abgewiesen. (2) dauer_min nur, "
                "wenn die Dauer feststeht — eine Skizze ohne Minuten bleibt ohne, bis die "
                "Lehrkraft Minuten will; dann das Feld weglassen, nie 0. (3) sozialform und "
                "methode: Steht der Begriff im vokabular aus get_lesson_detail (Titel oder "
                "Alias), als {typ:'node',node_id,titel}, sonst als {typ:'text',wert} — nicht "
                "einzeln nachschlagen. (4) refs sind Kompetenzen und Begriffe — Begriffe mit "
                "typ 'concept' und node_id aus begriffe oder einem Treffer; refs nur setzen, "
                "wenn die Lehrkraft zugestimmt hat. Gibt suggested_refs zurück: Kompetenzen "
                "und Begriffe aus verknüpften Material-Knoten, die noch nicht in refs stehen — "
                "nur vorschlagen, nicht ungefragt übernehmen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": (
                            "UUID der Unterrichtsstunde; ohne Angabe die Bezugsstunde "
                            "der Unterhaltung"
                        ),
                    },
                    "phasen": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": (
                                        "Kennung aus get_lesson_detail — bei bestehenden "
                                        "Phasen unverändert übernehmen, sonst gehen ihr "
                                        "Nachbereitungsstatus und ihre Marken verloren. "
                                        "Neue Phasen ohne id."
                                    ),
                                },
                                "name": {"type": "string"},
                                "dauer_min": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "description": "Minuten; weglassen, solange die Dauer offen ist.",
                                },
                                "beschreibung": {"type": "string"},
                                "prio": {"type": "string", "enum": ["kern", "uebung", "vertiefung"]},
                                "sozialform": {"type": "object"},
                                "methode": {"type": "object"},
                                "material": {"type": "array", "items": {"type": "object"}},
                            },
                            # `dauer_min` optional seit 0.15 (Plan F5): Eine Skizze der
                            # Lehrkraft hat oft noch keine Minuten, und das Modell soll sie
                            # nicht erfinden müssen.
                            "required": ["name"],
                        },
                        "description": "Vollständiges Phasen-Array (überschreibt bestehende Phasen)",
                    },
                    "stundenziel": {"type": "string", "description": "Stundenziel (optional)"},
                    "refs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "node_id": {"type": "string"},
                                "typ": {"type": "string", "enum": ["ik", "pk", "concept"]},
                                "code": {"type": "string"},
                                "titel": {"type": "string"},
                                "partiell": {"type": "boolean"},
                            },
                            "required": ["node_id", "typ"],
                        },
                        "description": (
                            "Kompetenzen und Begriffe der Stunde (optional; nur setzen, wenn "
                            "die Lehrkraft zugestimmt hat). Immer die ganze Liste: bestehende "
                            "aus get_lesson_detail behalten, neue so übernehmen, wie sie im "
                            "Kapitel, in begriffe oder im Treffer stehen."
                        ),
                    },
                },
                "required": ["phasen"],
            },
        },
    },
    handler=_handle_update_lesson_phases,
))


# ── finde_stunde / waehle_stunde (0.15, Schritt 3) ────────────────────────────
#
# Die Stunde im Chat finden, ohne die Planungsansicht (Plan F9). Was die Werkzeuge tun und
# warum der Mitgliedschaftsfilter die Zugriffsregel ist: `app/planning/stunde_finden.py`.


async def _handle_finde_stunde(args: dict, ctx: ToolContext) -> dict:
    suche = stunde_finden.Suche(
        wann=(args.get("wann") or "").strip(),
        datum=args.get("datum"),
        wochentag=args.get("wochentag"),
        gruppe=args.get("gruppe"),
        fach=args.get("fach"),
        thema=args.get("thema"),
    )
    return await stunde_finden.finde_stunden(ctx.db, ctx.user.sub, suche, heute=date.today())


register_tool(ChatTool(
    name="finde_stunde",
    groups=frozenset({"lesson_planning"}),
    writes=False,
    definition={
        "type": "function",
        "function": {
            "name": "finde_stunde",
            "description": (
                "Sucht Termine in den eigenen Unterrichtsgruppen der Lehrkraft — für "
                "Anliegen wie 'meine Stunde morgen in der 9d' oder 'die Chemie-Stunde am "
                "Donnerstag', wenn die Unterhaltung noch keine Bezugsstunde hat. Das Datum "
                "rechnet die Plattform; gib selbst nur eines an, wenn die Lehrkraft es nennt "
                "(dann wann='datum'). Genau ein Treffer → waehle_stunde. Mehrere → frage, "
                "welcher gemeint ist. Keiner → sage, wonach gesucht wurde ('gesucht')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "wann": {
                        "type": "string",
                        "enum": list(stunde_finden.WANN),
                        "description": (
                            "naechste = je Gruppe der nächste Termin ab heute; morgen = der "
                            "Kalendertag nach heute; datum = das Datum aus 'datum'."
                        ),
                    },
                    "datum": {
                        "type": "string",
                        "description": "Nur mit wann='datum': wie genannt, z. B. '15.10.' oder '2026-10-15'.",
                    },
                    "wochentag": {
                        "type": "string",
                        "enum": list(stunde_finden.WOCHENTAGE),
                        "description": "Nur Termine an diesem Wochentag — 'am Donnerstag' = wann 'naechste' mit 'do'.",
                    },
                    "gruppe": {
                        "type": "string",
                        "description": "Name oder Klasse der Gruppe; ein Teil genügt ('9d').",
                    },
                    "fach": {"type": "string", "description": "Fachname; ein Teil genügt."},
                    "thema": {
                        "type": "string",
                        "description": "Stichwort aus Thema, Stundentitel oder Unterrichtseinheit.",
                    },
                },
                "required": ["wann"],
            },
        },
    },
    handler=_handle_finde_stunde,
))


async def _handle_waehle_stunde(args: dict, ctx: ToolContext) -> dict:
    try:
        slot_id = UUID(str(args.get("slot_id") or ""))
    except ValueError:
        return {"error": "Ungültige slot_id"}
    wahl = await stunde_finden.waehle(
        ctx.db, ctx.user, ctx.conversation_id, slot_id, anlegen=bool(args.get("anlegen")),
    )
    if wahl.stunde is None:
        return wahl.antwort
    # Gilt sofort, nicht erst ab der nächsten Nachricht: Der Router übernimmt beides nach
    # dem Aufruf für die folgenden Werkzeuge dieser Anfrage.
    ctx.stunde_node_id = wahl.stunde.id
    ctx.group_id = wahl.group_id
    entwurf = await _handle_get_lesson_detail({"node_id": str(wahl.stunde.id)}, ctx)
    return {**entwurf, "bezugsstunde_gesetzt": True, "neu_angelegt": wahl.neu}


register_tool(ChatTool(
    name="waehle_stunde",
    groups=frozenset({"lesson_planning"}),
    writes=True,
    definition={
        "type": "function",
        "function": {
            "name": "waehle_stunde",
            "description": (
                "Macht einen Termin aus finde_stunde zur Bezugsstunde dieser Unterhaltung und "
                "liefert seinen Stundenentwurf wie get_lesson_detail. Hat der Termin noch "
                "keinen Entwurf, legt es nur mit anlegen=true einen an — frage die Lehrkraft "
                "vorher."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slot_id": {"type": "string", "description": "slot_id aus finde_stunde"},
                    "anlegen": {
                        "type": "boolean",
                        "description": "Entwurf anlegen, falls keiner da ist — nur nach Zustimmung.",
                    },
                },
                "required": ["slot_id"],
            },
        },
    },
    handler=_handle_waehle_stunde,
))


# ── get_exam_scope (student_planning, read-only) ──────────────────────────────


async def _handle_get_exam_scope(args: dict, ctx: ToolContext) -> dict:
    if ctx.group_id is None:
        return {"error": "Kein Gruppenbezug — Tool nur in Gruppen-Conversations."}
    scope = await get_exam_scope(ctx.db, ctx.group_id, today=date.today())
    if scope is None:
        return {"exam": None}
    return {
        "exam_date": scope.exam_date.isoformat(),
        "unit_titles": scope.unit_titles,
        "topics": scope.topics,
        "refs": [
            {"node_id": r.node_id, "titel": r.titel, "code": r.code, "typ": r.typ}
            for r in scope.refs
        ],
    }


register_tool(ChatTool(
    name="get_exam_scope",
    groups=frozenset({"student_planning"}),
    writes=False,
    definition={
        "type": "function",
        "function": {
            "name": "get_exam_scope",
            "description": (
                "Liefert Termin und Umfang der nächsten Klassenarbeit der Gruppe: "
                "betroffene UE(s), Themenliste und die zu lernenden Kompetenzen und "
                "Fachbegriffe (refs mit node_id/titel/code/typ; typ 'concept' ist ein "
                "Fachbegriff) für Lernplan und Übungsauswahl. "
                "Read-only. Gibt {exam: null} zurück, wenn keine Prüfung geplant ist."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    handler=_handle_get_exam_scope,
))


# ── UP-6 Verschiebe-Dialog: get_reflow_context / apply_plan_operations / undo ──


async def _handle_get_reflow_context(args: dict, ctx: ToolContext) -> dict:
    if ctx.group_id is None:
        return {"error": "Kein Gruppenkontext"}
    trigger = args.get("trigger", "manual")
    slot_ids = [UUID(s) for s in (args.get("slot_ids") or [])]
    try:
        rc = await build_reflow_context(
            ctx.db, ctx.group_id, trigger=trigger, slot_ids=slot_ids or None
        )
    except ValueError as e:
        return {"error": str(e)}
    return rc.model_dump()


register_tool(ChatTool(
    name="get_reflow_context",
    groups=frozenset({"planning"}),
    writes=False,
    definition={
        "type": "function",
        "function": {
            "name": "get_reflow_context",
            "description": (
                "Liefert die Datengrundlage für eine Umverteilung: betroffene Slots, "
                "Folge-Slots bis zum nächsten Fixpunkt, Fixpunkte mit verbleibendem "
                "Slot-Vorrat, UE-Bilanz, bei trigger='open_phases' die offenen Phasen "
                "der Quellstunde, bei 'regeneration' alte Zuordnung + neue Tranche. "
                "Immer zuerst aufrufen; Zahlen nur von hier zitieren."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "trigger": {
                        "type": "string",
                        "enum": ["ausfall", "drag_drop", "open_phases", "regeneration", "manual"],
                    },
                    "slot_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Auslöser-Slot-UUIDs (optional je nach Trigger)",
                    },
                },
                "required": ["trigger"],
            },
        },
    },
    handler=_handle_get_reflow_context,
))


async def _handle_apply_plan_operations(args: dict, ctx: ToolContext) -> dict:
    if ctx.group_id is None:
        return {"error": "Kein Gruppenkontext"}
    summary = args.get("summary") or "Plan-Änderung"
    try:
        ops = parse_operations(args.get("operations") or [])
    except ValidationError as e:
        return {"ok": False, "errors": [f"Ungültige Operationen: {e.errors()[:3]}"]}
    res = await apply_operations(
        ctx.db, ctx.group_id, ops, summary=summary, created_by=ctx.user.sub
    )
    if res.errors:
        return {"ok": False, "errors": res.errors}
    antwort = {"ok": True, "applied": res.applied, "snapshot_id": res.snapshot_id,
               "summary": summary}
    if res.hinweise:
        # Kein Fehler — angewandt ist angewandt. Aber das Modell soll es lesen.
        antwort["hinweise"] = res.hinweise
    return antwort


register_tool(ChatTool(
    name="apply_plan_operations",
    groups=frozenset({"planning"}),
    writes=True,
    definition={
        "type": "function",
        "function": {
            "name": "apply_plan_operations",
            "description": (
                "Wendet eine Liste typisierter Plan-Operationen atomar an (Snapshot davor). "
                "summary wird als Undo-Label gespeichert (z. B. 'KW43-Ausfall: 2 Themen "
                "geschoben, Vertiefung gestrichen'). Bei Validierungsfehler wird nichts "
                "angewendet (errors zurück). Nur nach Bestätigung der Lehrkraft.\n"
                "WICHTIG: Eine geplante Stunde verlegt man mit move_content — es nimmt "
                "Thema, Unterrichtseinheit UND Stundenentwurf mit. set_topic setzt nur "
                "die Überschrift und lässt Einheit und Entwurf am alten Termin zurück; "
                "es ist für Termine ohne Entwurf gedacht.\n"
                "WICHTIG: Fällt eine Stunde aus (Wandertag, Fortbildung, Klassenfahrt, "
                "Studientag, Krankheit), trägt cancel_lesson{slot_id} den Ausfall ein. "
                "Soll der Stoff weiter — 'alles eine Stunde nach hinten' —, setze "
                "nachruecken:true: Dann rückt der Inhalt mit allen folgenden Stunden bis "
                "zum nächsten freien Termin eins weiter, in einer einzigen Operation. Soll "
                "nur dieses Thema auf einen bestimmten Termin, nimm stattdessen move_content "
                "im selben Stapel. move_content allein räumt den Termin nur leer; er bliebe "
                "'unterricht' und zählte weiter als gehaltene Stunde. Ein Ausfall ist kein "
                "Puffer: puffer ist eine Reservestunde, die stattfindet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operations": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": (
                            "Operationen, je mit 'op'. Was sie bewirken:\n"
                            "- move_content{from_slot_id,to_slot_id}: verlegt eine Stunde "
                            "vollständig — Thema, Unterrichtseinheit und Stundenentwurf "
                            "wandern zum Ziel, die Quelle bleibt leer zurück. Das ist die "
                            "Operation für 'Stunde verschieben'. Die **Kategorie** der "
                            "Quelle ändert sie NICHT: Ein ausgefallener Termin bleibt "
                            "sonst 'unterricht' und zählt weiter mit — dafür zusätzlich "
                            "cancel_lesson.\n"
                            "- cancel_lesson{slot_id,nachruecken}: trägt einen Ausfall ein — "
                            "die Stunde findet nicht statt und zählt nicht mehr in der "
                            "Stundenbilanz. Ohne nachruecken bleiben Thema, Einheit und "
                            "Entwurf am Termin. nachruecken:true (nur, wenn die Lehrkraft "
                            "den Stoff weiterschieben will) rückt sie und alle folgenden "
                            "Unterrichtsstunden eins weiter, bis zum ersten freien Termin "
                            "(leere Stunde oder Puffer) — nie über eine Prüfung oder einen "
                            "gepinnten Termin hinweg; reicht der Platz nicht, wird nichts "
                            "angewandt. Was gerückt ist, steht danach in 'hinweise'.\n"
                            "- swap_content{slot_a,slot_b}: tauscht den Inhalt zweier "
                            "Termine vollständig.\n"
                            "- set_topic{slot_id,thema}: setzt NUR die Überschrift eines "
                            "Termins. Einheit und Entwurf bleiben, wo sie sind — für eine "
                            "Verlegung ist das falsch.\n"
                            "- set_unit{slot_id,unit_node_id}: ordnet einem Termin eine "
                            "Unterrichtseinheit zu (null löst die Zuordnung).\n"
                            "- set_category{slot_id,kategorie}: unterricht | pruefung | "
                            "puffer | vertretung. puffer ist eine Reservestunde, die "
                            "stattfindet und mitzählt — für einen Ausfall cancel_lesson. "
                            "unterricht hebt auch einen Ausfall wieder auf.\n"
                            "- mark_needs_adjustment{slot_id,value}: markiert, dass an "
                            "diesem Termin noch etwas zu entscheiden ist.\n"
                            "- transfer_phases{from_lesson_id,to_lesson_id,phase_ids}: "
                            "verschiebt einzelne Verlaufsphasen zwischen zwei Entwürfen.\n"
                            "- shorten_phase{lesson_id,phase_id,dauer_min}: kürzt eine "
                            "Phase auf die angegebene Dauer.\n"
                            "- strike_phase{lesson_id,phase_id}: streicht eine Phase. "
                            "Sie bleibt im Verlaufsplan sichtbar (als gestrichen "
                            "markiert), zählt aber nicht mehr zur Zeit — gelöscht wird "
                            "nichts."
                        ),
                    },
                    "summary": {"type": "string", "description": "Kurzlabel für den Undo-Verlauf"},
                },
                "required": ["operations", "summary"],
            },
        },
    },
    handler=_handle_apply_plan_operations,
))


async def _handle_undo_last_change(args: dict, ctx: ToolContext) -> dict:
    if ctx.group_id is None:
        return {"error": "Kein Gruppenkontext"}
    snap = (
        await ctx.db.execute(
            sa.select(SlotPlanSnapshot)
            .where(SlotPlanSnapshot.group_id == ctx.group_id)
            .order_by(SlotPlanSnapshot.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if snap is None:
        return {"ok": False, "error": "Kein Snapshot zum Rückgängigmachen vorhanden"}
    label = snap.label
    await restore_snapshot(ctx.db, snap.id, ctx.user)
    return {"ok": True, "restored_label": label}


register_tool(ChatTool(
    name="undo_last_change",
    groups=frozenset({"planning"}),
    writes=True,
    definition={
        "type": "function",
        "function": {
            "name": "undo_last_change",
            "description": (
                "Macht die letzte Plan-Änderung der Gruppe rückgängig (stellt den letzten "
                "Snapshot wieder her). Gibt das Label der rückgängig gemachten Änderung zurück."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    handler=_handle_undo_last_change,
))
