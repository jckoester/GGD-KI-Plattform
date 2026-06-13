"""Unit-Tests für app.planning.review_service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.planning.review_service import ReviewResult, complete_review, undo_review


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _make_slot(
    slot_id=None,
    group_id=10,
    stunde_node_id=None,
    nachbereitet_at=None,
    nachbereitet_auto=False,
):
    slot = MagicMock()
    slot.id = slot_id or uuid4()
    slot.group_id = group_id
    slot.stunde_node_id = stunde_node_id or uuid4()
    slot.nachbereitet_at = nachbereitet_at
    slot.nachbereitet_auto = nachbereitet_auto
    return slot


def _make_stunde(node_id=None, phasen=None, refs=None):
    node = MagicMock()
    node.id = node_id or uuid4()
    node.metadata_ = {
        "phasen": phasen or [],
        "refs": refs or [],
    }
    return node


def _make_db(slot, stunde):
    db = AsyncMock()

    async def db_get(model, pk):
        from app.db.models import ContextNode, LessonSlot
        if model is LessonSlot:
            return slot
        if model is ContextNode:
            return stunde
        return None

    db.get.side_effect = db_get
    db.commit = AsyncMock()
    return db


# ── ReviewResult-Datenklasse ─────────────────────────────────────────────────

def test_review_result_defaults():
    r = ReviewResult()
    assert r.engagements_written == 0
    assert r.engagements_skipped == 0
    assert r.refs_offen == []
    assert r.open_phases == []


def test_review_result_fields():
    r = ReviewResult(engagements_written=3, engagements_skipped=1, refs_offen=["abc"], open_phases=["Erarbeitung"])
    assert r.engagements_written == 3
    assert r.refs_offen == ["abc"]


# ── complete_review: Fehlerbehandlung ────────────────────────────────────────

@pytest.mark.asyncio
async def test_complete_review_slot_not_found():
    db = AsyncMock()
    db.get.return_value = None
    with pytest.raises(ValueError, match="Slot nicht gefunden"):
        await complete_review(db, uuid4(), group_id=1, phasen_status={})


@pytest.mark.asyncio
async def test_complete_review_slot_no_stunde():
    slot = _make_slot(stunde_node_id=None)
    slot.stunde_node_id = None

    db = AsyncMock()

    async def db_get(model, pk):
        from app.db.models import LessonSlot
        if model is LessonSlot:
            return slot
        return None

    db.get.side_effect = db_get

    with pytest.raises(ValueError, match="Slot hat keine Stunde"):
        await complete_review(db, slot.id, group_id=slot.group_id, phasen_status={})


# ── complete_review: Phasen-Status ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_complete_review_sets_phasen_status():
    phase_id = str(uuid4())
    phasen = [{"id": phase_id, "name": "Erarbeitung", "dauer_min": 20}]
    slot = _make_slot()
    stunde = _make_stunde(phasen=phasen)

    with patch("app.planning.review_service.pg_insert") as mock_insert:
        mock_stmt = MagicMock()
        mock_stmt.on_conflict_do_nothing.return_value = mock_stmt
        mock_insert.return_value = mock_stmt

        db = _make_db(slot, stunde)
        mock_execute_result = MagicMock()
        mock_execute_result.rowcount = 0
        db.execute = AsyncMock(return_value=mock_execute_result)

        await complete_review(db, slot.id, group_id=slot.group_id,
                              phasen_status={phase_id: "offen"})

    written_meta = stunde.metadata_
    assert written_meta["phasen"][0]["status"] == "offen"


@pytest.mark.asyncio
async def test_complete_review_default_status_erledigt():
    phase_id = str(uuid4())
    phasen = [{"id": phase_id, "name": "Einstieg", "dauer_min": 10}]
    slot = _make_slot()
    stunde = _make_stunde(phasen=phasen)

    with patch("app.planning.review_service.pg_insert") as mock_insert:
        mock_stmt = MagicMock()
        mock_stmt.on_conflict_do_nothing.return_value = mock_stmt
        mock_insert.return_value = mock_stmt

        db = _make_db(slot, stunde)
        mock_execute_result = MagicMock()
        mock_execute_result.rowcount = 0
        db.execute = AsyncMock(return_value=mock_execute_result)

        # Kein Eintrag für diese Phase → Default 'erledigt'
        await complete_review(db, slot.id, group_id=slot.group_id, phasen_status={})

    assert stunde.metadata_["phasen"][0]["status"] == "erledigt"


# ── complete_review: refs_offen ausgenommen ───────────────────────────────────

@pytest.mark.asyncio
async def test_complete_review_refs_offen_excluded():
    ref_id = uuid4()
    other_ref_id = uuid4()
    refs = [
        {"node_id": str(ref_id), "typ": "ik"},
        {"node_id": str(other_ref_id), "typ": "ik"},
    ]
    slot = _make_slot()
    stunde = _make_stunde(refs=refs)

    inserted_nodes = []

    with patch("app.planning.review_service.pg_insert") as mock_insert:
        def capture_insert(model):
            stmt = MagicMock()
            def capture_values(**kwargs):
                inserted_nodes.append(kwargs.get("node_id"))
                return stmt
            stmt.values = MagicMock(side_effect=lambda **kw: (inserted_nodes.append(kw.get("node_id")), stmt)[1])
            stmt.on_conflict_do_nothing.return_value = stmt
            return stmt

        mock_insert.side_effect = capture_insert

        db = _make_db(slot, stunde)
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db.execute = AsyncMock(return_value=mock_result)

        result = await complete_review(
            db, slot.id, group_id=slot.group_id,
            phasen_status={},
            refs_offen=[ref_id],
        )

    assert str(ref_id) in result.refs_offen
    assert str(ref_id) not in [str(n) for n in inserted_nodes]


# ── complete_review: Methoden-Knoten einbezogen ───────────────────────────────

@pytest.mark.asyncio
async def test_complete_review_methode_node_included():
    methode_node_id = uuid4()
    phasen = [
        {
            "id": str(uuid4()),
            "name": "Erarbeitung",
            "dauer_min": 25,
            "methode": {"typ": "node", "node_id": str(methode_node_id)},
            "material": [],
        }
    ]
    slot = _make_slot()
    stunde = _make_stunde(phasen=phasen)

    inserted_nodes = []

    with patch("app.planning.review_service.pg_insert") as mock_insert:
        def capture(model):
            stmt = MagicMock()

            def capture_vals(**kw):
                inserted_nodes.append(kw.get("node_id"))
                return stmt

            stmt.values = MagicMock(side_effect=lambda **kw: (inserted_nodes.append(kw.get("node_id")), stmt)[1])
            stmt.on_conflict_do_nothing.return_value = stmt
            return stmt

        mock_insert.side_effect = capture

        db = _make_db(slot, stunde)
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db.execute = AsyncMock(return_value=mock_result)

        await complete_review(db, slot.id, group_id=slot.group_id, phasen_status={})

    assert methode_node_id in inserted_nodes


# ── complete_review: offene Phase, Methoden-Knoten ausgeschlossen ─────────────

@pytest.mark.asyncio
async def test_complete_review_open_phase_node_excluded():
    phase_id = str(uuid4())
    methode_node_id = uuid4()
    phasen = [
        {
            "id": phase_id,
            "name": "Vertiefung",
            "dauer_min": 15,
            "methode": {"typ": "node", "node_id": str(methode_node_id)},
            "material": [],
        }
    ]
    slot = _make_slot()
    stunde = _make_stunde(phasen=phasen)

    inserted_nodes = []

    with patch("app.planning.review_service.pg_insert") as mock_insert:
        def capture(model):
            stmt = MagicMock()
            stmt.values = MagicMock(side_effect=lambda **kw: (inserted_nodes.append(kw.get("node_id")), stmt)[1])
            stmt.on_conflict_do_nothing.return_value = stmt
            return stmt

        mock_insert.side_effect = capture

        db = _make_db(slot, stunde)
        mock_result = MagicMock()
        mock_result.rowcount = 0
        db.execute = AsyncMock(return_value=mock_result)

        result = await complete_review(
            db, slot.id, group_id=slot.group_id,
            phasen_status={phase_id: "offen"},
        )

    assert methode_node_id not in inserted_nodes
    assert "Vertiefung" in result.open_phases


# ── complete_review: open_phases in Ergebnis ─────────────────────────────────

@pytest.mark.asyncio
async def test_complete_review_open_phases_in_result():
    p1_id, p2_id = str(uuid4()), str(uuid4())
    phasen = [
        {"id": p1_id, "name": "Einstieg", "dauer_min": 10},
        {"id": p2_id, "name": "Sicherung", "dauer_min": 10},
    ]
    slot = _make_slot()
    stunde = _make_stunde(phasen=phasen)

    with patch("app.planning.review_service.pg_insert") as mock_insert:
        stmt = MagicMock()
        stmt.on_conflict_do_nothing.return_value = stmt
        mock_insert.return_value = stmt

        db = _make_db(slot, stunde)
        mock_result = MagicMock()
        mock_result.rowcount = 0
        db.execute = AsyncMock(return_value=mock_result)

        result = await complete_review(
            db, slot.id, group_id=slot.group_id,
            phasen_status={p1_id: "erledigt", p2_id: "gestrichen"},
        )

    assert "Sicherung" in result.open_phases
    assert "Einstieg" not in result.open_phases


# ── complete_review: Slot-Stempel ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_complete_review_stamps_slot():
    slot = _make_slot()
    stunde = _make_stunde()

    with patch("app.planning.review_service.pg_insert") as mock_insert:
        stmt = MagicMock()
        stmt.on_conflict_do_nothing.return_value = stmt
        mock_insert.return_value = stmt

        db = _make_db(slot, stunde)
        mock_result = MagicMock()
        mock_result.rowcount = 0
        db.execute = AsyncMock(return_value=mock_result)

        await complete_review(db, slot.id, group_id=slot.group_id, phasen_status={})

    assert slot.nachbereitet_at is not None
    assert slot.nachbereitet_auto is False


@pytest.mark.asyncio
async def test_complete_review_auto_flag():
    slot = _make_slot()
    stunde = _make_stunde()

    with patch("app.planning.review_service.pg_insert") as mock_insert:
        stmt = MagicMock()
        stmt.on_conflict_do_nothing.return_value = stmt
        mock_insert.return_value = stmt

        db = _make_db(slot, stunde)
        mock_result = MagicMock()
        mock_result.rowcount = 0
        db.execute = AsyncMock(return_value=mock_result)

        await complete_review(db, slot.id, group_id=slot.group_id, phasen_status={}, auto=True)

    assert slot.nachbereitet_auto is True


# ── undo_review ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_undo_review_resets_slot():
    from datetime import datetime, timezone

    slot = _make_slot(nachbereitet_at=datetime.now(timezone.utc), nachbereitet_auto=False)
    stunde = _make_stunde(phasen=[{"id": "p1", "name": "Einstieg", "status": "erledigt"}])

    db = _make_db(slot, stunde)

    delete_result = MagicMock()
    delete_result.fetchall.return_value = []
    db.execute = AsyncMock(return_value=delete_result)

    deleted = await undo_review(db, slot.id, group_id=slot.group_id)

    assert slot.nachbereitet_at is None
    assert slot.nachbereitet_auto is False


@pytest.mark.asyncio
async def test_undo_review_clears_phase_status():
    from datetime import datetime, timezone

    phase_id = str(uuid4())
    slot = _make_slot(nachbereitet_at=datetime.now(timezone.utc))
    stunde = _make_stunde(phasen=[{"id": phase_id, "name": "Erarbeitung", "status": "offen"}])

    db = _make_db(slot, stunde)
    delete_result = MagicMock()
    delete_result.fetchall.return_value = []
    db.execute = AsyncMock(return_value=delete_result)

    await undo_review(db, slot.id, group_id=slot.group_id)

    assert "status" not in stunde.metadata_["phasen"][0]
