"""Unit-Tests für GET/PATCH /planning/lessons/{node_id}."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.planning.router import router
from app.planning.schemas import VALID_PRIOS


# ── Schema-Tests ──────────────────────────────────────────────────────────────


def test_valid_prios_set():
    assert "kern" in VALID_PRIOS
    assert "uebung" in VALID_PRIOS
    assert "vertiefung" in VALID_PRIOS
    assert len(VALID_PRIOS) == 3


def test_lesson_phase_item_validates_prio():
    from app.planning.schemas import LessonPhaseItem

    phase = LessonPhaseItem(name="Einstieg", dauer_min=15, prio="kern")
    phase.validate_prio()  # should not raise

    phase_bad = LessonPhaseItem(name="Einstieg", dauer_min=15, prio="ungueltig")
    with pytest.raises(ValueError, match="Ungültige Prio"):
        phase_bad.validate_prio()


def test_lesson_phase_item_requires_name():
    from app.planning.schemas import LessonPhaseItem
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        LessonPhaseItem(name="", dauer_min=15)  # min_length=1


def test_lesson_phase_item_requires_positive_dauer():
    from app.planning.schemas import LessonPhaseItem
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        LessonPhaseItem(name="Test", dauer_min=0)


def test_lesson_update_optional_fields():
    from app.planning.schemas import LessonUpdate

    u = LessonUpdate()
    assert u.titel is None
    assert u.phasen is None
    assert u.refs is None


def test_lesson_ref_item_defaults():
    from app.planning.schemas import LessonRefItem

    r = LessonRefItem(node_id=uuid4(), typ="ik")
    assert r.partiell is False
    assert r.code is None


def test_lesson_nav_fields():
    from app.planning.schemas import LessonNav

    nav = LessonNav(prev_node_id=None, next_node_id=None, position=1, total=3)
    assert nav.total == 3
    assert nav.position == 1


# ── Navigation-Hilfsfunktion ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_lesson_nav_empty_unit():
    from app.planning.router import _build_lesson_nav

    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [])))

    nav = await _build_lesson_nav(db, uuid4(), uuid4())
    assert nav.total == 1
    assert nav.position == 1


@pytest.mark.asyncio
async def test_build_lesson_nav_no_unit():
    from app.planning.router import _build_lesson_nav

    db = AsyncMock()
    nav = await _build_lesson_nav(db, uuid4(), None)
    assert nav.prev_node_id is None
    assert nav.next_node_id is None
    assert nav.total == 1


# ── Phasen-Serialisierung ─────────────────────────────────────────────────────


def test_lesson_phase_serialization():
    from app.planning.schemas import LessonPhaseItem, LessonLinkedItem

    phase = LessonPhaseItem(
        id="abc",
        name="Einstieg",
        dauer_min=15,
        prio="kern",
        methode=LessonLinkedItem(typ="text", wert="Fishbowl"),
        material=[LessonLinkedItem(typ="text", wert="Arbeitsblatt")],
    )
    d = phase.model_dump(mode="json")
    assert d["name"] == "Einstieg"
    assert d["methode"]["wert"] == "Fishbowl"
    assert d["material"][0]["wert"] == "Arbeitsblatt"


def test_lesson_phase_material_is_list():
    from app.planning.schemas import LessonPhaseItem

    phase = LessonPhaseItem(name="Test", dauer_min=10)
    assert isinstance(phase.material, list)
    assert len(phase.material) == 0


# ── PATCH-Berechtigung via Schema ─────────────────────────────────────────────


def test_lesson_update_phasen_invalid_prio_rejected():
    from app.planning.schemas import LessonUpdate, LessonPhaseItem

    payload = LessonUpdate(
        phasen=[LessonPhaseItem(name="Test", dauer_min=10, prio="falsch")]
    )
    with pytest.raises(ValueError):
        for p in payload.phasen:
            p.validate_prio()
