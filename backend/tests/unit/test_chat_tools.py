"""Tests für Tool-Registry und Mehrrunden-Loop-Logik (chat/tools.py)."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.chat.tools import ChatTool, ToolContext, TOOL_REGISTRY, register_tool, tools_for


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_tool(name: str, group: str, writes: bool = False) -> ChatTool:
    async def _handler(args, ctx):
        return {"ok": True}

    return ChatTool(
        name=name,
        group=group,
        definition={"type": "function", "function": {"name": name, "parameters": {}}},
        handler=_handler,
        writes=writes,
    )


# ── tools_for ─────────────────────────────────────────────────────────────────


def test_context_search_always_included():
    """context_search Tools sind immer aktiv — kein Assistent, kein group_id."""
    tool = _make_tool("dummy_search", "context_search")
    # Direkt in eine lokale Map für den Test — nicht in TOOL_REGISTRY
    from app.chat.tools import ChatTool, ToolContext
    import app.chat.tools as tools_mod

    saved = dict(tools_mod.TOOL_REGISTRY)
    tools_mod.TOOL_REGISTRY.clear()
    tools_mod.TOOL_REGISTRY["dummy_search"] = tool
    try:
        result = tools_for(None, None, False)
        assert any(t.name == "dummy_search" for t in result)
    finally:
        tools_mod.TOOL_REGISTRY.clear()
        tools_mod.TOOL_REGISTRY.update(saved)


def test_planning_tool_not_included_without_group():
    """Planning Tools ohne group_id nicht aktiv."""
    import app.chat.tools as tools_mod

    tool = _make_tool("get_lesson_slots", "planning")
    saved = dict(tools_mod.TOOL_REGISTRY)
    tools_mod.TOOL_REGISTRY.clear()
    tools_mod.TOOL_REGISTRY["get_lesson_slots"] = tool

    assistant = MagicMock()
    assistant.tool_groups = ["planning"]

    try:
        result = tools_for(assistant, group_id=None, is_group_teacher=True)
        assert all(t.name != "get_lesson_slots" for t in result)
    finally:
        tools_mod.TOOL_REGISTRY.clear()
        tools_mod.TOOL_REGISTRY.update(saved)


def test_planning_tool_not_included_for_non_teacher():
    """Planning Tools ohne Lehrkraft-Mitgliedschaft nicht aktiv."""
    import app.chat.tools as tools_mod

    tool = _make_tool("get_lesson_slots", "planning")
    saved = dict(tools_mod.TOOL_REGISTRY)
    tools_mod.TOOL_REGISTRY.clear()
    tools_mod.TOOL_REGISTRY["get_lesson_slots"] = tool

    assistant = MagicMock()
    assistant.tool_groups = ["planning"]

    try:
        result = tools_for(assistant, group_id=42, is_group_teacher=False)
        assert all(t.name != "get_lesson_slots" for t in result)
    finally:
        tools_mod.TOOL_REGISTRY.clear()
        tools_mod.TOOL_REGISTRY.update(saved)


def test_planning_tool_not_included_without_tool_group_flag():
    """Planning Tools ohne 'planning' in assistant.tool_groups nicht aktiv."""
    import app.chat.tools as tools_mod

    tool = _make_tool("get_lesson_slots", "planning")
    saved = dict(tools_mod.TOOL_REGISTRY)
    tools_mod.TOOL_REGISTRY.clear()
    tools_mod.TOOL_REGISTRY["get_lesson_slots"] = tool

    assistant = MagicMock()
    assistant.tool_groups = []  # kein planning

    try:
        result = tools_for(assistant, group_id=42, is_group_teacher=True)
        assert all(t.name != "get_lesson_slots" for t in result)
    finally:
        tools_mod.TOOL_REGISTRY.clear()
        tools_mod.TOOL_REGISTRY.update(saved)


def test_planning_tool_included_when_all_conditions_met():
    """Planning Tools aktiv wenn assistant.tool_groups=['planning'], group_id gesetzt, Lehrkraft."""
    import app.chat.tools as tools_mod

    tool = _make_tool("get_lesson_slots", "planning")
    saved = dict(tools_mod.TOOL_REGISTRY)
    tools_mod.TOOL_REGISTRY.clear()
    tools_mod.TOOL_REGISTRY["get_lesson_slots"] = tool

    assistant = MagicMock()
    assistant.tool_groups = ["planning"]

    try:
        result = tools_for(assistant, group_id=42, is_group_teacher=True)
        assert any(t.name == "get_lesson_slots" for t in result)
    finally:
        tools_mod.TOOL_REGISTRY.clear()
        tools_mod.TOOL_REGISTRY.update(saved)


def test_tools_for_no_assistant():
    """tools_for mit assistant=None liefert nur context_search."""
    import app.chat.tools as tools_mod

    cs_tool = _make_tool("search_ctx", "context_search")
    pl_tool = _make_tool("plan_tool", "planning")
    saved = dict(tools_mod.TOOL_REGISTRY)
    tools_mod.TOOL_REGISTRY.clear()
    tools_mod.TOOL_REGISTRY["search_ctx"] = cs_tool
    tools_mod.TOOL_REGISTRY["plan_tool"] = pl_tool

    try:
        result = tools_for(None, group_id=42, is_group_teacher=True)
        names = [t.name for t in result]
        assert "search_ctx" in names
        assert "plan_tool" not in names
    finally:
        tools_mod.TOOL_REGISTRY.clear()
        tools_mod.TOOL_REGISTRY.update(saved)


# ── MAX_TOOL_ROUNDS Abbruch-Logik ─────────────────────────────────────────────


def test_max_tool_rounds_constant():
    from app.chat.router import _MAX_TOOL_ROUNDS
    assert _MAX_TOOL_ROUNDS >= 3, "MAX_TOOL_ROUNDS muss mindestens 3 betragen"


# ── student_planning (UP-7) ───────────────────────────────────────────────────


def _swap_registry(**tools):
    """Hilfskontext: TOOL_REGISTRY temporär durch die übergebenen Tools ersetzen."""
    import app.chat.tools as tools_mod

    saved = dict(tools_mod.TOOL_REGISTRY)
    tools_mod.TOOL_REGISTRY.clear()
    tools_mod.TOOL_REGISTRY.update(tools)
    return tools_mod, saved


def test_student_planning_included_for_non_teacher_with_group():
    """get_exam_scope ist auch für Nicht-Lehrkräfte aktiv (nur Gruppenbezug nötig)."""
    mod, saved = _swap_registry(get_exam_scope=_make_tool("get_exam_scope", "student_planning"))
    assistant = MagicMock()
    assistant.tool_groups = ["student_planning"]
    try:
        result = tools_for(assistant, group_id=5, is_group_teacher=False)
        assert any(t.name == "get_exam_scope" for t in result)
    finally:
        mod.TOOL_REGISTRY.clear()
        mod.TOOL_REGISTRY.update(saved)


def test_student_planning_not_included_without_group():
    mod, saved = _swap_registry(get_exam_scope=_make_tool("get_exam_scope", "student_planning"))
    assistant = MagicMock()
    assistant.tool_groups = ["student_planning"]
    try:
        result = tools_for(assistant, group_id=None, is_group_teacher=False)
        assert all(t.name != "get_exam_scope" for t in result)
    finally:
        mod.TOOL_REGISTRY.clear()
        mod.TOOL_REGISTRY.update(saved)


def test_student_sees_only_student_planning_not_planning_tools():
    """Schüler-Assistent erhält get_exam_scope, aber keine schreibenden planning-Tools."""
    mod, saved = _swap_registry(
        get_exam_scope=_make_tool("get_exam_scope", "student_planning"),
        get_lesson_slots=_make_tool("get_lesson_slots", "planning"),
    )
    assistant = MagicMock()
    assistant.tool_groups = ["student_planning"]
    try:
        names = {t.name for t in tools_for(assistant, group_id=5, is_group_teacher=False)}
        assert "get_exam_scope" in names
        assert "get_lesson_slots" not in names
    finally:
        mod.TOOL_REGISTRY.clear()
        mod.TOOL_REGISTRY.update(saved)
