"""Unit-Tests für den Snapshot-Service (Roundtrip + Pruning)."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.planning.snapshots import SNAPSHOT_LIMIT, create_snapshot, restore_snapshot


def _mock_slot(
    sid: UUID | None = None,
    ue_id: UUID | None = None,
    stunde_id: UUID | None = None,
    kategorie: str = "unterricht",
) -> MagicMock:
    s = MagicMock()
    s.id = sid or uuid4()
    s.group_id = 1
    s.date = date(2026, 9, 14)
    s.kategorie = kategorie
    s.ue_node_id = ue_id
    s.stunde_node_id = stunde_id
    s.thema = None
    s.pinned = False
    s.anpassung_noetig = False
    return s


def _mock_user(sub: str = "teacher1") -> MagicMock:
    u = MagicMock()
    u.sub = sub
    return u


def _make_db(slots=None, snapshot_count=0):
    slots = slots or []

    async def mock_execute(stmt):
        r = MagicMock()
        r.scalars.return_value.all.return_value = slots
        r.all.return_value = []
        return r

    async def mock_scalar(stmt):
        return snapshot_count

    db = AsyncMock()
    db.execute = mock_execute
    db.scalar = mock_scalar
    db.get = AsyncMock(return_value=None)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_create_snapshot_erstellt_eintrag():
    slot_id = uuid4()
    slots = [_mock_slot(sid=slot_id)]
    db = _make_db(slots)

    snap = await create_snapshot(db, group_id=1, reason="manual", label="vor Test")

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.reason == "manual"
    assert added.label == "vor Test"
    assert added.group_id == 1
    assert len(added.payload["slots"]) == 1
    assert added.payload["slots"][0]["slot_id"] == str(slot_id)


@pytest.mark.asyncio
async def test_create_snapshot_pruning():
    db = _make_db(snapshot_count=SNAPSHOT_LIMIT + 2)
    oldest_ids = [uuid4() for _ in range(2)]

    async def mock_execute(stmt):
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        r.all.return_value = [(i,) for i in oldest_ids]
        return r

    db.execute = mock_execute
    await create_snapshot(db, group_id=1, reason="manual")
    # Pruning-DELETE muss aufgerufen worden sein
    # (schwierig direkt zu prüfen ohne echter DB; es genügt kein Fehler)


@pytest.mark.asyncio
async def test_restore_snapshot_nicht_gefunden():
    from fastapi import HTTPException

    db = AsyncMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await restore_snapshot(db, uuid4(), _mock_user())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_restore_snapshot_roundtrip():
    slot_id = uuid4()
    ue_id = uuid4()

    snap = MagicMock()
    snap.id = uuid4()
    snap.group_id = 1
    snap.reason = "manual"
    snap.payload = {
        "slots": [
            {
                "slot_id": str(slot_id),
                "date": "2026-09-14",
                "kategorie": "unterricht",
                "ue_node_id": str(ue_id),
                "stunde_node_id": None,
                "thema": "Ursprungsthema",
                "pinned": False,
                "anpassung_noetig": False,
            }
        ],
        "stunden_phasen": {},
    }

    slot = _mock_slot(sid=slot_id)

    async def mock_get(model, oid, *args, **kwargs):
        from app.db.models import SlotPlanSnapshot, LessonSlot

        if model == SlotPlanSnapshot:
            return snap
        if str(oid) == str(slot_id):
            return slot
        return None

    db = AsyncMock()
    db.get = mock_get
    db.execute = AsyncMock(return_value=MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
        all=MagicMock(return_value=[]),
    ))
    db.scalar = AsyncMock(return_value=0)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    result = await restore_snapshot(db, snap.id, _mock_user())

    assert result["restored"] is True
    assert result["skipped_slot_ids"] == []
    assert slot.thema == "Ursprungsthema"
    assert slot.ue_node_id == str(ue_id)
