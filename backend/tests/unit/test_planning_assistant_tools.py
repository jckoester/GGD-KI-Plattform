"""Unit-Tests für planning/assistant_tools.py und planning/service.py."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.chat.tools import ToolContext


def _make_ctx(group_id=None):
    user = MagicMock()
    user.sub = "test-pseudonym"
    db = AsyncMock()
    return ToolContext(db=db, user=user, group_id=group_id, conversation_id=None)


# ── Tool-Registration ─────────────────────────────────────────────────────────


def test_planning_tools_registered():
    """Alle 5 Planungs-Tools sind nach Import in TOOL_REGISTRY."""
    import app.planning.assistant_tools  # noqa — stellt sicher dass importiert
    from app.chat.tools import TOOL_REGISTRY

    expected = {
        "get_lesson_slots",
        "get_curriculum_chapters",
        "get_plan_balance",
        "create_teaching_unit",
        "assign_slots_to_unit",
        "set_slot_topics",
        "set_slot_category",
    }
    registered = set(TOOL_REGISTRY.keys())
    assert expected.issubset(registered)


def test_write_tools_have_writes_flag():
    from app.chat.tools import TOOL_REGISTRY

    write_tools = {"create_teaching_unit", "assign_slots_to_unit", "set_slot_topics", "set_slot_category"}
    for name in write_tools:
        tool = TOOL_REGISTRY.get(name)
        if tool:
            assert tool.writes is True, f"{name} sollte writes=True haben"


def test_read_tools_have_no_writes_flag():
    from app.chat.tools import TOOL_REGISTRY

    read_tools = {"get_lesson_slots", "get_curriculum_chapters", "get_plan_balance"}
    for name in read_tools:
        tool = TOOL_REGISTRY.get(name)
        if tool:
            assert tool.writes is False, f"{name} sollte writes=False haben"


# ── Fehlerfall: kein group_id ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_lesson_slots_no_group():
    from app.planning.assistant_tools import _handle_get_lesson_slots

    ctx = _make_ctx(group_id=None)
    result = await _handle_get_lesson_slots({}, ctx)
    assert "error" in result


@pytest.mark.asyncio
async def test_get_plan_balance_no_group():
    from app.planning.assistant_tools import _handle_get_plan_balance

    ctx = _make_ctx(group_id=None)
    result = await _handle_get_plan_balance({}, ctx)
    assert "error" in result


@pytest.mark.asyncio
async def test_create_teaching_unit_missing_titel():
    from app.planning.assistant_tools import _handle_create_teaching_unit

    ctx = _make_ctx(group_id=1)
    result = await _handle_create_teaching_unit({"titel": ""}, ctx)
    assert "error" in result


@pytest.mark.asyncio
async def test_assign_slots_missing_args():
    from app.planning.assistant_tools import _handle_assign_slots_to_unit

    ctx = _make_ctx(group_id=1)
    result = await _handle_assign_slots_to_unit({}, ctx)
    assert "error" in result


@pytest.mark.asyncio
async def test_set_slot_category_invalid():
    from app.planning.assistant_tools import _handle_set_slot_category

    ctx = _make_ctx(group_id=1)
    result = await _handle_set_slot_category(
        {"slot_id": str(uuid4()), "kategorie": "ungueltig"}, ctx
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_set_slot_topics_empty_items():
    from app.planning.assistant_tools import _handle_set_slot_topics

    ctx = _make_ctx(group_id=1)
    result = await _handle_set_slot_topics({"items": []}, ctx)
    assert "error" in result


# ── set_slot_category — Validierung ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_slot_category_unknown_slot():
    from app.planning.assistant_tools import _handle_set_slot_category

    ctx = _make_ctx(group_id=42)
    ctx.db.get = AsyncMock(return_value=None)  # Slot nicht gefunden

    result = await _handle_set_slot_category(
        {"slot_id": str(uuid4()), "kategorie": "puffer"}, ctx
    )
    assert "error" in result
