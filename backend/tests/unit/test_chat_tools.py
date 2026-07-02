"""Tests für Tool-Registry und Mehrrunden-Loop-Logik (chat/tools.py)."""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.config import settings
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


# ── get_operatoren (Operatoren-Zugriff für Assistenten) ───────────────────────


def test_get_operatoren_registered_as_context_search():
    """get_operatoren ist immer aktiv (Gruppe context_search) und read-only."""
    from app.chat import router  # noqa: F401 — registriert das Tool
    tool = TOOL_REGISTRY.get("get_operatoren")
    assert tool is not None
    assert tool.group == "context_search"
    assert tool.writes is False


async def test_get_operatoren_no_subject_returns_empty():
    """Ohne Fachbezug (kein group_id / keine conversation) → leere Liste, kein DB-Zugriff."""
    from app.chat import router
    db = MagicMock()
    db.get = AsyncMock()  # darf nicht aufgerufen werden
    ctx = ToolContext(db=db, user=None, group_id=None, conversation_id=None)
    result = await router._exec_get_operatoren(ctx)
    assert result == []
    db.get.assert_not_called()


async def test_get_operatoren_current_edition_only_and_mapping():
    """Liefert nur die neueste Edition, alphabetisch, mit operator/afb/bedeutung/synonyme."""
    from app.chat import router

    nodes = [
        SimpleNamespace(title="anwenden", content="alte Fassung",
                        metadata_={"bp_version": "2016", "afb": ["II"], "aliase": []}),
        SimpleNamespace(title="beurteilen", content="def-b",
                        metadata_={"bp_version": "2016.V2", "afb": ["III"], "aliase": ["bewerten"]}),
        SimpleNamespace(title="analysieren", content="def-a",
                        metadata_={"bp_version": "2016.V2", "afb": ["II", "III"]}),
    ]
    exec_result = MagicMock()
    exec_result.scalars.return_value.all.return_value = nodes

    db = MagicMock()
    db.get = AsyncMock(return_value=SimpleNamespace(subject_id=6))  # Group → Fach
    db.execute = AsyncMock(return_value=exec_result)

    ctx = ToolContext(db=db, user=None, group_id=2, conversation_id=None)
    result = await router._exec_get_operatoren(ctx)

    # Nur 2016.V2-Operatoren, alphabetisch nach Titel
    assert [r["operator"] for r in result] == ["analysieren", "beurteilen"]
    assert result[0]["afb"] == "II, III"
    assert "synonyme" not in result[0]           # keine aliase → Feld weggelassen
    assert result[1]["afb"] == "III"
    assert result[1]["bedeutung"] == "def-b"
    assert result[1]["synonyme"] == ["bewerten"]


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


# ── generate_image (Bildgenerierung Phase 16) ─────────────────────────────────


def test_generate_image_registered_as_image_generation():
    """generate_image ist registriert und in der Gruppe image_generation."""
    from app.chat import router  # noqa: F401 — registriert das Tool
    tool = TOOL_REGISTRY.get("generate_image")
    assert tool is not None
    assert tool.group == "image_generation"


def test_generate_image_gated_by_tool_group():
    """Nur aktiv, wenn 'image_generation' in assistant.tool_groups — sonst (auch ohne
    Assistent) nicht."""
    mod, saved = _swap_registry(generate_image=_make_tool("generate_image", "image_generation"))
    try:
        enabled = MagicMock()
        enabled.tool_groups = ["image_generation"]
        assert any(t.name == "generate_image"
                   for t in tools_for(enabled, group_id=None, is_group_teacher=False))

        disabled = MagicMock()
        disabled.tool_groups = []
        assert all(t.name != "generate_image"
                   for t in tools_for(disabled, group_id=None, is_group_teacher=False))

        assert all(t.name != "generate_image"
                   for t in tools_for(None, group_id=None, is_group_teacher=False))
    finally:
        mod.TOOL_REGISTRY.clear()
        mod.TOOL_REGISTRY.update(saved)


async def test_generate_image_handler_happy_path():
    """Prompt → Bild-Bytes; generate_image mit User-Key + Pseudonym + Default-Modell; persistiert."""
    from app.chat import router
    instance = MagicMock()
    instance.generate_image = AsyncMock(return_value=b"\x89PNG-bytes")
    instance.close = AsyncMock()
    conv_id, img_id = uuid4(), uuid4()
    ctx = ToolContext(
        db=MagicMock(), user=SimpleNamespace(sub="pseudo-9"),
        group_id=None, conversation_id=conv_id, litellm_key="sk-user",
    )
    with patch.object(router, "LiteLLMClient", return_value=instance), \
         patch.object(router, "save_generated_image", new=AsyncMock(return_value=img_id)) as save:
        result = await router._exec_generate_image(
            {"prompt": "ein roter Würfel", "size": "1024x1024"}, ctx,
        )

    assert result["status"] == "ok"
    assert result["size"] == "1024x1024"
    assert result["image_id"] == str(img_id)
    call = instance.generate_image.await_args
    assert call.kwargs["api_key"] == "sk-user"
    assert call.kwargs["user"] == "pseudo-9"
    assert call.kwargs["model"] == settings.image_default_model
    assert call.kwargs["response_format"] is None  # gpt-image-1 lehnt den Param ab
    instance.close.assert_awaited_once()
    save_call = save.await_args
    assert save_call.kwargs["pseudonym"] == "pseudo-9"
    assert save_call.kwargs["conversation_id"] == conv_id


async def test_generate_image_invalid_size_falls_back_to_default():
    """Nicht-Standard-Größe → settings.image_default_size (Spend=0-Schutz)."""
    from app.chat import router
    instance = MagicMock()
    instance.generate_image = AsyncMock(return_value=b"img")
    instance.close = AsyncMock()
    ctx = ToolContext(
        db=MagicMock(), user=SimpleNamespace(sub="p"),
        group_id=None, conversation_id=uuid4(), litellm_key="k",
    )
    with patch.object(router, "LiteLLMClient", return_value=instance), \
         patch.object(router, "save_generated_image", new=AsyncMock(return_value=uuid4())):
        result = await router._exec_generate_image({"prompt": "x", "size": "999x999"}, ctx)

    assert result["size"] == settings.image_default_size
    assert instance.generate_image.await_args.kwargs["size"] == settings.image_default_size


async def test_generate_image_no_conversation_returns_error():
    """Ohne conversation_id kein Persistenzziel → Fehler, kein Proxy-Aufruf."""
    from app.chat import router
    ctx = ToolContext(
        db=MagicMock(), user=SimpleNamespace(sub="p"),
        group_id=None, conversation_id=None, litellm_key="k",
    )
    with patch.object(router, "LiteLLMClient") as cls:
        result = await router._exec_generate_image({"prompt": "x"}, ctx)
    assert result["status"] == "error"
    cls.assert_not_called()


async def test_generate_image_no_key_returns_error():
    """Kein Virtual Key im Kontext → Fehler, kein Proxy-Aufruf."""
    from app.chat import router
    ctx = ToolContext(
        db=MagicMock(), user=SimpleNamespace(sub="p"),
        group_id=None, conversation_id=None, litellm_key=None,
    )
    with patch.object(router, "LiteLLMClient") as cls:
        result = await router._exec_generate_image({"prompt": "x"}, ctx)
    assert result["status"] == "error"
    cls.assert_not_called()


async def test_generate_image_empty_prompt_returns_error():
    """Leerer Prompt → Fehler, kein Proxy-Aufruf."""
    from app.chat import router
    ctx = ToolContext(
        db=MagicMock(), user=SimpleNamespace(sub="p"),
        group_id=None, conversation_id=None, litellm_key="k",
    )
    with patch.object(router, "LiteLLMClient") as cls:
        result = await router._exec_generate_image({"prompt": "   "}, ctx)
    assert result["status"] == "error"
    cls.assert_not_called()


async def test_generate_image_blocked_by_moderation(monkeypatch):
    """Moderations-Stub liefert Grund → status blocked, kein Proxy-Aufruf."""
    from app.chat import router
    monkeypatch.setattr(router, "_image_prompt_block_reason", lambda p: "unzulässiger Inhalt")
    ctx = ToolContext(
        db=MagicMock(), user=SimpleNamespace(sub="p"),
        group_id=None, conversation_id=None, litellm_key="k",
    )
    with patch.object(router, "LiteLLMClient") as cls:
        result = await router._exec_generate_image({"prompt": "x"}, ctx)
    assert result["status"] == "blocked"
    assert "unzulässig" in result["error"]
    cls.assert_not_called()
