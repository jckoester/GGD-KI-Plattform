"""UP-6 Schritt 2: Tests für den Plan-Operationen-Executor."""

from uuid import uuid4

import psycopg2
import pytest

from app.db.models import ContextNode, LessonSlot
from app.planning import operations as ops_mod
from app.planning.operations import (
    MoveContent, SetCategory, SetTopic, StrikePhase, TransferPhases,
    apply_operations, parse_operations,
)
from datetime import date, timedelta

GROUP_ID = 202
D0 = date(2026, 9, 1)


@pytest.fixture(scope="module")
def seed_ops_group(db_url, run_migrations):
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) "
                    "VALUES (202, 'op-test', 'OP Test', 0) ON CONFLICT (id) DO NOTHING")
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                    "VALUES (202, 'OP 8a', 'op-8a', 'teaching_group', 202) "
                    "ON CONFLICT (id) DO NOTHING")
    conn.commit()
    conn.close()


def _slot(d, *, kategorie="unterricht", thema=None, ue_id=None, stunde_id=None, pinned=False):
    return LessonSlot(
        id=uuid4(), group_id=GROUP_ID, date=d, halbjahr=1, periods=1, start_period=3,
        kategorie=kategorie, thema=thema, ue_node_id=ue_id, stunde_node_id=stunde_id, pinned=pinned,
    )


def _stunde(title, phasen=None, refs_offen=None):
    return ContextNode(
        id=uuid4(), category="artifact", content_type="unterrichtsstunde", title=title,
        metadata_={"phasen": phasen or [], "refs_offen": refs_offen or []},
        read_scope="group", read_scope_group_id=GROUP_ID, status="active",
    )


async def _apply(db_session, ops, summary="t"):
    """apply_operations mit commit→flush, damit das Rollback-Fixture greift."""
    async def _commit_as_flush():
        await db_session.flush()
    import unittest.mock as m
    with m.patch.object(db_session, "commit", new=_commit_as_flush):
        return await apply_operations(db_session, GROUP_ID, ops, summary=summary)


def test_parse_operations_discriminated_union():
    ops = parse_operations([
        {"op": "set_topic", "slot_id": str(uuid4()), "thema": "X"},
        {"op": "strike_phase", "lesson_id": str(uuid4()), "phase_id": "p1"},
    ])
    assert isinstance(ops[0], SetTopic) and isinstance(ops[1], StrikePhase)


@pytest.mark.asyncio
async def test_apply_set_topic_and_category(db_session, seed_ops_group):
    s = _slot(D0)
    db_session.add(s)
    await db_session.flush()
    res = await _apply(db_session, [
        SetTopic(op="set_topic", slot_id=s.id, thema="Neues Thema"),
        SetCategory(op="set_category", slot_id=s.id, kategorie="puffer"),
    ])
    assert res.errors == [] and res.applied == 2
    assert s.thema == "Neues Thema" and s.kategorie == "puffer"
    assert res.snapshot_id is not None


@pytest.mark.asyncio
async def test_apply_move_content(db_session, seed_ops_group):
    ue = ContextNode(id=uuid4(), category="artifact", content_type="unterrichtseinheit",
                     title="UE", metadata_={}, read_scope="group",
                     read_scope_group_id=GROUP_ID, status="active")
    db_session.add(ue)
    src = _slot(D0, thema="Inhalt", ue_id=ue.id)
    dst = _slot(D0 + timedelta(days=1))
    db_session.add_all([src, dst])
    await db_session.flush()

    res = await _apply(db_session, [
        MoveContent(op="move_content", from_slot_id=src.id, to_slot_id=dst.id)
    ])
    assert res.errors == []
    assert dst.thema == "Inhalt" and dst.ue_node_id == ue.id
    assert src.thema is None and src.ue_node_id is None


@pytest.mark.asyncio
async def test_apply_atomicity_pinned_rejected(db_session, seed_ops_group):
    pin = _slot(D0, thema="Fix", pinned=True)
    other = _slot(D0 + timedelta(days=1), thema="A")
    db_session.add_all([pin, other])
    await db_session.flush()

    # Zweite Op ist invalid (gepinnt) → gar nichts wird angewendet.
    res = await _apply(db_session, [
        SetTopic(op="set_topic", slot_id=other.id, thema="Geändert"),
        SetTopic(op="set_topic", slot_id=pin.id, thema="Verboten"),
    ])
    assert res.applied == 0 and res.snapshot_id is None
    assert any("gepinnt" in e for e in res.errors)
    assert other.thema == "A"  # nicht verändert


@pytest.mark.asyncio
async def test_apply_move_to_occupied_rejected(db_session, seed_ops_group):
    a = _slot(D0, thema="A")
    b = _slot(D0 + timedelta(days=1), thema="B")
    db_session.add_all([a, b])
    await db_session.flush()
    res = await _apply(db_session, [
        MoveContent(op="move_content", from_slot_id=a.id, to_slot_id=b.id)
    ])
    assert res.applied == 0
    assert any("belegt" in e for e in res.errors)


@pytest.mark.asyncio
async def test_apply_transfer_phases(db_session, seed_ops_group):
    R = str(uuid4())
    src = _stunde("Quelle", phasen=[
        {"id": "p1", "name": "Übertrag", "prio": "uebung", "dauer_min": 15, "status": "offen"},
        {"id": "p2", "name": "Bleibt", "prio": "kern", "dauer_min": 10, "status": "erledigt"},
    ], refs_offen=[R])
    dst = _stunde("Ziel", phasen=[{"id": "q1", "name": "Vorhanden", "prio": "kern", "dauer_min": 20, "status": "geplant"}])
    db_session.add_all([src, dst])
    await db_session.flush()

    res = await _apply(db_session, [
        TransferPhases(op="transfer_phases", from_lesson_id=src.id, to_lesson_id=dst.id, phase_ids=["p1"])
    ])
    assert res.errors == []
    dst_phasen = dst.metadata_["phasen"]
    assert dst_phasen[0]["name"] == "Übertrag"          # an den Anfang
    assert dst_phasen[0]["uebertrag_von"] == str(src.id)
    assert dst_phasen[0]["status"] == "geplant"
    assert [p["id"] for p in src.metadata_["phasen"]] == ["p2"]  # aus Quelle entfernt
    assert any(r["node_id"] == R for r in dst.metadata_["refs"])  # refs_offen mitgeführt
