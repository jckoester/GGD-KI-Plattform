"""Planungs-Tools für den Jahresplan-Assistenten.

Registriert sich beim Import in TOOL_REGISTRY.
Alle Tools erfordern eine group_id im ToolContext.
Schreib-Tools erzeugen Auto-Snapshots (reason='assistant').
"""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.tools import ChatTool, ToolContext, register_tool
from app.db.models import ContextEdge, ContextNode, LessonSlot
from app.planning.permissions import require_group_teacher

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
            ContextNode.write_scope == "group",
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
    return balance.model_dump()


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
    group="planning",
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


async def _handle_get_curriculum_chapters(args: dict, ctx: ToolContext) -> list[dict]:
    group_id = ctx.group_id
    if group_id is None:
        return {"error": "Kein Gruppenkontext"}

    db = ctx.db

    # Gruppe → subject_id + ggf. Lehrplan
    from app.db.models import Group
    group = await db.get(Group, group_id)
    if group is None or group.subject_id is None:
        return []

    # Kapitel des Fachs (Bildungsplan-Knoten)
    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "kapitel",
            ContextNode.subject_id == group.subject_id,
            ContextNode.status == "active",
        ).order_by(ContextNode.metadata_["position"].astext.cast(sa.Integer).nullslast())
    )
    chapters = result.scalars().all()

    # Welche UEs referenzieren welches Kapitel?
    ue_result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "unterrichtseinheit",
            ContextNode.write_scope_group_id == group_id,
            ContextNode.status == "active",
        )
    )
    ues = ue_result.scalars().all()

    # kapitel_id → [ue_titel]
    ue_by_kapitel: dict[UUID, list[str]] = {}
    for ue in ues:
        edges = await db.execute(
            sa.select(ContextEdge).where(
                ContextEdge.from_node_id == ue.id,
                ContextEdge.relation == "references",
            )
        )
        for edge in edges.scalars().all():
            ue_by_kapitel.setdefault(edge.to_node_id, []).append(ue.title)

    return [
        {
            "id": str(c.id),
            "titel": c.title,
            "std": (c.metadata_ or {}).get("std"),
            "lernsequenzen": (c.metadata_ or {}).get("lernsequenzen", []),
            "ues": ue_by_kapitel.get(c.id, []),
        }
        for c in chapters
    ]


register_tool(ChatTool(
    name="get_curriculum_chapters",
    group="planning",
    writes=False,
    definition={
        "type": "function",
        "function": {
            "name": "get_curriculum_chapters",
            "description": (
                "Gibt die Kapitel des Fachlehrplans für die Gruppe zurück. "
                "Enthält Titel, Soll-Stunden (std), Lernsequenzen und bereits "
                "angelegte UE-Verknüpfungen."
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
    group="planning",
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
    group="planning",
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
    group="planning",
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
    group="planning",
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
    group="planning",
    writes=True,
    definition={
        "type": "function",
        "function": {
            "name": "set_slot_category",
            "description": (
                "Setzt die Kategorie eines Slots auf pruefung, puffer, vertretung "
                "oder zurück auf unterricht. "
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
