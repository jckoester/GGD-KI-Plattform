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
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.tools import ChatTool, ToolContext, register_tool
from app.db.models import ContextEdge, ContextNode, LessonSlot, SlotPlanSnapshot
from app.planning.curriculum_resolver import resolve_group_curricula
from app.planning.operations import apply_operations, parse_operations
from app.planning.permissions import require_group_teacher
from app.planning.reflow_service import build_reflow_context
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
    group="planning",
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


# ── get_unit_detail ───────────────────────────────────────────────────────────


async def _handle_get_unit_detail(args: dict, ctx: ToolContext) -> dict:
    group_id = ctx.group_id
    if group_id is None:
        return {"error": "Kein Gruppenkontext"}

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

    # Kapitel-Verknüpfung
    chapter_info = None
    ref_edge = (
        await db.execute(
            sa.select(ContextEdge).where(
                ContextEdge.from_node_id == unit_id,
                ContextEdge.relation == "references",
            )
        )
    ).scalar_one_or_none()
    if ref_edge:
        ch = await db.get(ContextNode, ref_edge.to_node_id)
        if ch:
            chapter_info = {
                "id": str(ch.id),
                "titel": ch.title,
                "std": (ch.metadata_ or {}).get("std"),
                "lernsequenzen": (ch.metadata_ or {}).get("lernsequenzen", []),
            }

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
    group="planning",
    writes=False,
    definition={
        "type": "function",
        "function": {
            "name": "get_unit_detail",
            "description": (
                "Gibt Detailinfos zu einer Unterrichtseinheit: "
                "Kapitel mit Lernsequenzen, zugewiesene Slots und bereits angelegte Stunden."
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
            read_scope="group",
            write_scope="group",
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
    group="planning",
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


async def _handle_get_lesson_detail(args: dict, ctx: ToolContext) -> dict:
    group_id = ctx.group_id
    if group_id is None:
        return {"error": "Kein Gruppenkontext"}

    node_str = args.get("node_id", "")
    if not node_str:
        return {"error": "node_id erforderlich"}

    db = ctx.db
    node = await db.get(ContextNode, UUID(node_str))
    if node is None or node.status != "active" or node.content_type != "unterrichtsstunde":
        return {"error": "Stunde nicht gefunden"}
    if node.write_scope_group_id != group_id:
        return {"error": "Stunde gehört nicht zur Gruppe"}

    meta = node.metadata_ or {}
    slot_result = await db.execute(
        sa.select(LessonSlot).where(LessonSlot.stunde_node_id == node.id)
    )
    slot = slot_result.scalar_one_or_none()

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
    }


register_tool(ChatTool(
    name="get_lesson_detail",
    group="planning",
    writes=False,
    definition={
        "type": "function",
        "function": {
            "name": "get_lesson_detail",
            "description": (
                "Gibt den vollständigen Stundenentwurf zurück: "
                "Titel, Stundenziel, Phasen-Array, Kompetenzen und Slot-Kontext."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "UUID der Unterrichtsstunde",
                    },
                },
                "required": ["node_id"],
            },
        },
    },
    handler=_handle_get_lesson_detail,
))


# ── update_lesson_phases ──────────────────────────────────────────────────────


async def _handle_update_lesson_phases(args: dict, ctx: ToolContext) -> dict:
    group_id = ctx.group_id
    if group_id is None:
        return {"error": "Kein Gruppenkontext"}

    node_str = args.get("node_id", "")
    phasen = args.get("phasen")
    if not node_str or phasen is None:
        return {"error": "node_id und phasen erforderlich"}

    db = ctx.db
    node = await db.get(ContextNode, UUID(node_str))
    if node is None or node.status != "active" or node.content_type != "unterrichtsstunde":
        return {"error": "Stunde nicht gefunden"}
    if node.write_scope_group_id != group_id:
        return {"error": "Stunde gehört nicht zur Gruppe"}

    from app.planning.schemas import VALID_PRIOS
    from app.planning.snapshots import create_snapshot
    from datetime import datetime, timezone

    for p in phasen:
        if p.get("prio", "kern") not in VALID_PRIOS:
            return {"error": f"Ungültige Prio: {p.get('prio')}"}

    await create_snapshot(db, group_id, reason="assistant", created_by=ctx.user.sub)

    meta = dict(node.metadata_ or {})
    meta["phasen"] = phasen
    stundenziel = args.get("stundenziel")
    if stundenziel is not None:
        meta["stundenziel"] = stundenziel
    refs = args.get("refs")
    if refs is not None:
        meta["refs"] = refs

    node.metadata_ = meta
    node.updated_at = datetime.now(timezone.utc)
    await db.commit()

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
                if comp and comp.content_type in ("ik_kompetenz", "pk_kompetenz", "concept"):
                    comp_id = str(comp.id)
                    if comp_id not in existing_ref_ids and comp_id not in dismissed:
                        suggested_refs.append({
                            "node_id": comp_id,
                            "typ": "ik" if comp.content_type == "ik_kompetenz" else
                                   "pk" if comp.content_type == "pk_kompetenz" else "concept",
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
    group="planning",
    writes=True,
    definition={
        "type": "function",
        "function": {
            "name": "update_lesson_phases",
            "description": (
                "Schreibt das Phasen-Array einer Stunde. Jede Phase kann sozialform und "
                "methode tragen (je {typ:'text',wert} oder {typ:'node',node_id,titel}). "
                "Gibt suggested_refs zurück: Kompetenzen aus verknüpften Material-Knoten, "
                "die noch nicht in refs stehen. Nur nach Bestätigung durch die Lehrkraft übernehmen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "UUID der Unterrichtsstunde"},
                    "phasen": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "dauer_min": {"type": "integer", "minimum": 1},
                                "beschreibung": {"type": "string"},
                                "prio": {"type": "string", "enum": ["kern", "uebung", "vertiefung"]},
                                "sozialform": {"type": "object"},
                                "methode": {"type": "object"},
                                "material": {"type": "array", "items": {"type": "object"}},
                            },
                            "required": ["name", "dauer_min"],
                        },
                        "description": "Vollständiges Phasen-Array (überschreibt bestehende Phasen)",
                    },
                    "stundenziel": {"type": "string", "description": "Stundenziel (optional)"},
                    "refs": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Kompetenz-Refs (optional; nur setzen wenn Lehrkraft bestätigt)",
                    },
                },
                "required": ["node_id", "phasen"],
            },
        },
    },
    handler=_handle_update_lesson_phases,
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
            {"node_id": r.node_id, "titel": r.titel, "code": r.code}
            for r in scope.refs
        ],
    }


register_tool(ChatTool(
    name="get_exam_scope",
    group="student_planning",
    writes=False,
    definition={
        "type": "function",
        "function": {
            "name": "get_exam_scope",
            "description": (
                "Liefert Termin und Umfang der nächsten Klassenarbeit der Gruppe: "
                "betroffene UE(s), Themenliste und die zu lernenden Kompetenzen "
                "(refs mit node_id/titel/code) für Lernplan und Übungsauswahl. "
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
    group="planning",
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
    return {"ok": True, "applied": res.applied, "snapshot_id": res.snapshot_id, "summary": summary}


register_tool(ChatTool(
    name="apply_plan_operations",
    group="planning",
    writes=True,
    definition={
        "type": "function",
        "function": {
            "name": "apply_plan_operations",
            "description": (
                "Wendet eine Liste typisierter Plan-Operationen atomar an (Snapshot davor). "
                "summary wird als Undo-Label gespeichert (z. B. 'KW43-Ausfall: 2 Themen "
                "geschoben, Vertiefung gestrichen'). Bei Validierungsfehler wird nichts "
                "angewendet (errors zurück). Nur nach Bestätigung der Lehrkraft."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operations": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": (
                            "Operationen, je mit 'op': move_content{from_slot_id,to_slot_id}, "
                            "swap_content{slot_a,slot_b}, set_topic{slot_id,thema}, "
                            "set_unit{slot_id,unit_node_id}, set_category{slot_id,kategorie}, "
                            "mark_needs_adjustment{slot_id,value}, "
                            "transfer_phases{from_lesson_id,to_lesson_id,phase_ids}, "
                            "shorten_phase{lesson_id,phase_id,dauer_min}, "
                            "strike_phase{lesson_id,phase_id}"
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
    group="planning",
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
