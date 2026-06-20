"""UP-6 Schritt 3: Tool-Roundtrip (get_reflow_context → apply_plan_operations → undo)."""

import unittest.mock as m
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import psycopg2
import pytest

from app.chat.tools import ToolContext
from app.db.models import LessonSlot
from app.planning.assistant_tools import (
    _handle_apply_plan_operations,
    _handle_get_reflow_context,
    _handle_undo_last_change,
)

GROUP_ID = 203
D0 = date(2026, 9, 1)


@pytest.fixture(scope="module")
def seed_rtool_group(db_url, run_migrations):
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) "
                    "VALUES (203, 'rt-test', 'RT Test', 0) ON CONFLICT (id) DO NOTHING")
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                    "VALUES (203, 'RT 7a', 'rt-7a', 'teaching_group', 203) "
                    "ON CONFLICT (id) DO NOTHING")
    conn.commit()
    conn.close()


def _ctx(db_session):
    return ToolContext(
        db=db_session, user=SimpleNamespace(sub="teach-rt"),
        group_id=GROUP_ID, conversation_id=None,
    )


def _slot(d, **kw):
    return LessonSlot(id=uuid4(), group_id=GROUP_ID, date=d, halbjahr=1, periods=1,
                      start_period=3, kategorie=kw.get("kategorie", "unterricht"),
                      thema=kw.get("thema"), pinned=kw.get("pinned", False))


def _patch_commit(db_session):
    async def _commit_as_flush():
        await db_session.flush()
    return m.patch.object(db_session, "commit", new=_commit_as_flush)


@pytest.mark.asyncio
async def test_tool_get_reflow_context(db_session, seed_rtool_group):
    s = _slot(D0, thema="Auslöser")
    db_session.add_all([s, _slot(D0 + timedelta(days=1), thema="Folge")])
    await db_session.flush()

    out = await _handle_get_reflow_context(
        {"trigger": "ausfall", "slot_ids": [str(s.id)]}, _ctx(db_session)
    )
    assert out["trigger"] == "ausfall"
    assert [b["thema"] for b in out["betroffene"]] == ["Auslöser"]
    assert "fixpunkte" in out and "bilanz" in out


@pytest.mark.asyncio
async def test_tool_apply_and_undo(db_session, seed_rtool_group):
    s = _slot(D0, thema="Original")
    db_session.add(s)
    await db_session.flush()

    with _patch_commit(db_session):
        applied = await _handle_apply_plan_operations({
            "operations": [{"op": "set_topic", "slot_id": str(s.id), "thema": "Geändert"}],
            "summary": "Thema geschoben",
        }, _ctx(db_session))
    assert applied["ok"] is True and applied["applied"] == 1
    assert s.thema == "Geändert"

    with _patch_commit(db_session):
        undone = await _handle_undo_last_change({}, _ctx(db_session))
    assert undone["ok"] is True
    assert undone["restored_label"] == "Thema geschoben"
    await db_session.refresh(s)
    assert s.thema == "Original"


@pytest.mark.asyncio
async def test_undo_restores_phases(db_session, seed_rtool_group):
    from app.db.models import ContextNode

    stunde = ContextNode(
        id=uuid4(), category="artifact", content_type="unterrichtsstunde", title="S",
        metadata_={"phasen": [
            {"id": "p1", "name": "Vertiefung", "prio": "vertiefung", "dauer_min": 10, "status": "geplant"}
        ], "refs_offen": []},
        read_scope="group", read_scope_group_id=GROUP_ID, status="active",
    )
    db_session.add(stunde)
    s = _slot(D0, thema="X")
    s.stunde_node_id = stunde.id
    db_session.add(s)
    await db_session.flush()

    with _patch_commit(db_session):
        await _handle_apply_plan_operations({
            "operations": [{"op": "strike_phase", "lesson_id": str(stunde.id), "phase_id": "p1"}],
            "summary": "Vertiefung gestrichen",
        }, _ctx(db_session))
    assert stunde.metadata_["phasen"][0]["status"] == "gestrichen"

    with _patch_commit(db_session):
        await _handle_undo_last_change({}, _ctx(db_session))
    await db_session.refresh(stunde)
    assert stunde.metadata_["phasen"][0]["status"] == "geplant"


@pytest.mark.asyncio
async def test_tool_apply_invalid_returns_errors(db_session, seed_rtool_group):
    pin = _slot(D0, thema="Fix", pinned=True)
    db_session.add(pin)
    await db_session.flush()

    with _patch_commit(db_session):
        out = await _handle_apply_plan_operations({
            "operations": [{"op": "set_topic", "slot_id": str(pin.id), "thema": "X"}],
            "summary": "versuch",
        }, _ctx(db_session))
    assert out["ok"] is False
    assert any("gepinnt" in e for e in out["errors"])
