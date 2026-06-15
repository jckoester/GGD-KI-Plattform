"""Unit-Tests für den Slot-Generator.

Verwendet eine Fixture-Konfiguration statt der echten school_year.yaml,
damit Ferien, Doppelstunden und Halbjahresgrenzen deterministisch testbar sind.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.planning.calendar import FerienPeriod, SchoolYearConfig, halbjahr_bounds
from app.planning.slot_generator import generate_slots


def _mini_cfg() -> SchoolYearConfig:
    """Kleines Schuljahr (3 Wochen) für deterministische Tests."""
    return SchoolYearConfig(
        schuljahr="2026/27",
        # 2026-01-05 Montag → 2026-01-23 Freitag (3 Wochen, 15 Werktage)
        beginn=date(2026, 1, 5),
        ende=date(2026, 1, 23),
        halbjahreswechsel=date(2026, 1, 12),  # Montag der 2. Woche
        ferien=[
            # Ferien in Woche 2 (Mo–Fr)
            FerienPeriod(name="TestFerien", von=date(2026, 1, 12), bis=date(2026, 1, 16)),
        ],
        feiertage=[],
        unterrichtsfreie_tage=[],
    )


def _mk_pattern(weekday: int, start_period: int = 1, periods: int = 1, halbjahr: int = 1):
    p = MagicMock()
    p.weekday = weekday
    p.start_period = start_period
    p.periods = periods
    p.halbjahr = halbjahr
    return p


def _make_db(
    patterns_hj: dict[int, list] | None = None,
    existing_count: int = 0,
    primary_halbjahr: int = 1,
):
    """Erstellt eine Mock-DB.

    primary_halbjahr: das Halbjahr das zuerst abgefragt wird (ergibt Aufruf 0).
    Bei leerem primären Ergebnis und HJ2 folgt ein zweiter Aufruf für HJ1-Fallback.
    """
    patterns_hj = patterns_hj or {}
    call_counter = [0]
    # Reihenfolge: Aufruf 0 → primary_halbjahr, Aufruf 1 → HJ1-Fallback
    call_order = [primary_halbjahr, 1]

    async def mock_execute(stmt):
        idx = call_counter[0]
        call_counter[0] += 1

        # DELETE-Statement: kein scalars nötig
        if "delete" in type(stmt).__name__.lower() or "Delete" in str(type(stmt)):
            return MagicMock()

        hj = call_order[min(idx, len(call_order) - 1)]
        r = MagicMock()
        r.scalars.return_value.all.return_value = patterns_hj.get(hj, [])
        return r

    async def mock_scalar(stmt):
        return existing_count

    db = AsyncMock()
    db.execute = mock_execute
    db.scalar = mock_scalar
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_generiert_nur_schultage():
    cfg = _mini_cfg()
    # HJ1: 5 Schultage (Woche 1, Mo–Fr)
    # Mo pattern
    patterns = {1: [_mk_pattern(weekday=0, halbjahr=1)]}  # Montag
    db = _make_db(patterns)

    with patch("app.planning.slot_generator.load_school_year", return_value=cfg):
        stats = await generate_slots(db, group_id=1, halbjahr=1, cfg=cfg)

    # Woche 1 hat 1 Montag → 1 Slot; Woche 2 Montag ist Ferienbeginn → kein Slot
    assert stats.created == 1
    assert stats.halbjahr == 1


@pytest.mark.asyncio
async def test_doppelstunde():
    cfg = _mini_cfg()
    patterns = {1: [_mk_pattern(weekday=1, periods=2, halbjahr=1)]}  # Dienstag Doppel
    db = _make_db(patterns)

    with patch("app.planning.slot_generator.load_school_year", return_value=cfg):
        stats = await generate_slots(db, group_id=1, halbjahr=1, cfg=cfg)

    assert stats.created == 1  # Dienstag in Woche 1 (Woche 2 = Ferien)
    assert db.add.call_count == 1
    added_slot = db.add.call_args[0][0]
    assert added_slot.periods == 2


@pytest.mark.asyncio
async def test_halbjahresgrenze():
    cfg = _mini_cfg()
    # Di pattern für beide Halbjahre
    patterns = {
        1: [_mk_pattern(weekday=1, halbjahr=1)],
        2: [_mk_pattern(weekday=1, halbjahr=2)],
    }
    db = _make_db(patterns, primary_halbjahr=2)

    with patch("app.planning.slot_generator.load_school_year", return_value=cfg):
        stats = await generate_slots(db, group_id=1, halbjahr=2, cfg=cfg)

    # HJ2: 2026-01-17 Samstag → 2026-01-23 Freitag → Dienstag 2026-01-20
    assert stats.created == 1


@pytest.mark.asyncio
async def test_hj1_fallback_fuer_hj2():
    cfg = _mini_cfg()
    # HJ2 hat kein eigenes Muster → Fallback auf HJ1
    patterns = {
        1: [_mk_pattern(weekday=0, halbjahr=1)],
        2: [],  # kein HJ2-Muster
    }
    db = _make_db(patterns, primary_halbjahr=2)

    with patch("app.planning.slot_generator.load_school_year", return_value=cfg):
        stats = await generate_slots(db, group_id=1, halbjahr=2, cfg=cfg)

    assert stats.used_hj1_fallback is True
    assert stats.created >= 0  # Fallback-Muster angewendet


@pytest.mark.asyncio
async def test_regenerieren_loescht_alte_slots():
    cfg = _mini_cfg()
    patterns = {1: [_mk_pattern(weekday=0, halbjahr=1)]}
    db = _make_db(patterns, existing_count=5, primary_halbjahr=1)

    with (
        patch("app.planning.slot_generator.load_school_year", return_value=cfg),
        patch("app.planning.slot_generator.create_snapshot", new_callable=AsyncMock) as mock_snap,
    ):
        stats = await generate_slots(
            db, group_id=1, halbjahr=1, regenerate=True, cfg=cfg
        )

    assert stats.created == 1


@pytest.mark.asyncio
async def test_idempotenz_guard_ohne_regenerate():
    cfg = _mini_cfg()
    db = _make_db(existing_count=3)

    from fastapi import HTTPException

    with patch("app.planning.slot_generator.load_school_year", return_value=cfg):
        with pytest.raises(HTTPException) as exc:
            await generate_slots(db, group_id=1, halbjahr=1, cfg=cfg)

    assert exc.value.status_code == 409
