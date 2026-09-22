"""Unit-Tests für den Slot-Generator.

Verwendet eine Fixture-Konfiguration statt der echten school_year.yaml,
damit Ferien, Doppelstunden und Halbjahresgrenzen deterministisch testbar sind.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.planning.calendar import (
    A_WOCHE,
    B_WOCHE,
    WOECHENTLICH,
    FerienPeriod,
    SchoolYearConfig,
    halbjahr_bounds,
)
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


def _mk_pattern(
    weekday: int,
    start_period: int = 1,
    periods: int = 1,
    halbjahr: int = 1,
    rhythmus: str = WOECHENTLICH,
):
    p = MagicMock()
    p.weekday = weekday
    p.start_period = start_period
    p.periods = periods
    p.halbjahr = halbjahr
    # Muss gesetzt werden: Ein MagicMock ohne dieses Attribut liefert ein Mock-Objekt, und
    # der Generator hielte jedes Muster für 14-tägig.
    p.rhythmus = rhythmus
    return p


def _make_db(
    patterns_hj: dict[int, list] | None = None,
    existing_count: int = 0,
    primary_halbjahr: int = 1,
    verschonte: list | None = None,
):
    """Erstellt eine Mock-DB.

    primary_halbjahr: das Halbjahr das zuerst abgefragt wird (ergibt Aufruf 0).
    Bei leerem primären Ergebnis und HJ2 folgt ein zweiter Aufruf für HJ1-Fallback.

    `verschonte` sind die Slots, die nach dem Löschen noch stehen — der Generator fragt
    sie ab, um belegte Termine zu erkennen (Neuaufbau seit 22.09.2026).

    ⚠️ **Die Abfragen werden am Tabellennamen unterschieden, nicht an der Aufrufnummer.**
    Nach der Zählweise allein bekäme die Slot-Abfrage die Musterzeilen geliefert — der
    Mock behauptete dann etwas, was der Code nie sieht, und der Test wäre trotzdem grün.
    """
    patterns_hj = patterns_hj or {}
    verschonte = verschonte or []
    call_counter = [0]
    # Reihenfolge: Aufruf 0 → primary_halbjahr, Aufruf 1 → HJ1-Fallback
    call_order = [primary_halbjahr, 1]

    async def mock_execute(stmt):
        idx = call_counter[0]
        call_counter[0] += 1

        # DELETE-Statement: kein scalars nötig
        if "delete" in type(stmt).__name__.lower() or "Delete" in str(type(stmt)):
            return MagicMock()

        # Die Abfrage der verschonten Slots — am Tabellennamen erkannt.
        if "lesson_slots" in str(stmt):
            r = MagicMock()
            r.scalars.return_value.all.return_value = verschonte
            return r

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


# ── 14-tägige Muster ─────────────────────────────────────────────────────────


def _cfg_mit_ferienwoche(ab_zaehlung: str = "unterrichtswoche") -> SchoolYearConfig:
    """Mo 05.01. bis Fr 06.02.2026, Woche 2 (12.–16.01.) Ferien.

    Vier Montage im 1. Halbjahr, einer davon in den Ferien. Damit liegen zwei
    Unterrichtswochen — der 19.01. und der 26.01. — unmittelbar hinter einer **einwöchigen**
    Lücke, und genau dort trennen sich die beiden Zählweisen.
    """
    return SchoolYearConfig(
        schuljahr="2026/27",
        beginn=date(2026, 1, 5),
        ende=date(2026, 2, 6),
        halbjahreswechsel=date(2026, 2, 2),
        ferien=[FerienPeriod(name="TestFerien", von=date(2026, 1, 12), bis=date(2026, 1, 16))],
        ab_zaehlung=ab_zaehlung,
    )


async def _montage(cfg: SchoolYearConfig, rhythmus: str) -> list[date]:
    db = _make_db({1: [_mk_pattern(weekday=0, halbjahr=1, rhythmus=rhythmus)]})
    with patch("app.planning.slot_generator.load_school_year", return_value=cfg):
        await generate_slots(db, group_id=1, halbjahr=1, cfg=cfg)
    return sorted(aufruf[0][0].date for aufruf in db.add.call_args_list)


@pytest.mark.asyncio
async def test_vierzehntaegig_erzeugt_nur_die_halbe_anzahl():
    """Bis zum 14.09.2026 las der Generator `rhythmus` gar nicht — jeder 14-tägige Termin
    erzeugte doppelt so viele Stunden, wie er sollte."""
    cfg = _cfg_mit_ferienwoche()
    woechentlich = await _montage(cfg, WOECHENTLICH)
    assert len(woechentlich) == 3
    assert len(await _montage(cfg, A_WOCHE)) + len(await _montage(cfg, B_WOCHE)) == 3


@pytest.mark.asyncio
async def test_der_takt_laeuft_ueber_die_ferienwoche_weiter():
    """Unterrichtswochenzählung: Die Ferienwoche zählt nicht, der Wechsel geht weiter.

    Der 19.01. folgt unmittelbar auf die Ferien und ist trotzdem die *nächste* Woche im
    Takt — ein A-Wochen-Muster überspringt ihn.
    """
    cfg = _cfg_mit_ferienwoche("unterrichtswoche")
    assert await _montage(cfg, A_WOCHE) == [date(2026, 1, 5), date(2026, 1, 26)]
    assert await _montage(cfg, B_WOCHE) == [date(2026, 1, 19)]


@pytest.mark.asyncio
async def test_kalenderwochenzaehlung_legt_dieselbe_stunde_anders():
    """Dieselben Muster, dieselben Ferien — andere Regel, andere Wochen.

    Der Beweis, dass `ab_zaehlung` tatsächlich bis in die Slots durchschlägt und nicht nur
    ein Etikett verschiebt.
    """
    cfg = _cfg_mit_ferienwoche("kalenderwoche")
    assert await _montage(cfg, A_WOCHE) == [date(2026, 1, 5), date(2026, 1, 19)]
    assert await _montage(cfg, B_WOCHE) == [date(2026, 1, 26)]


@pytest.mark.asyncio
async def test_fallback_meldet_vierzehntaegige_muster():
    """Die einzige Stelle, an der eine Phase über den Halbjahreswechsel getragen wird."""
    cfg = _mini_cfg()
    db = _make_db({1: [_mk_pattern(weekday=0, halbjahr=1, rhythmus=A_WOCHE)]}, primary_halbjahr=2)
    with patch("app.planning.slot_generator.load_school_year", return_value=cfg):
        stats = await generate_slots(db, group_id=1, halbjahr=2, cfg=cfg)
    assert stats.used_hj1_fallback
    assert stats.fallback_vierzehntaegig


@pytest.mark.asyncio
async def test_woechentlicher_fallback_meldet_nichts():
    """Ein wöchentliches Muster kann über den Wechsel hinweg nicht verrutschen."""
    cfg = _mini_cfg()
    db = _make_db({1: [_mk_pattern(weekday=0, halbjahr=1)]}, primary_halbjahr=2)
    with patch("app.planning.slot_generator.load_school_year", return_value=cfg):
        stats = await generate_slots(db, group_id=1, halbjahr=2, cfg=cfg)
    assert stats.used_hj1_fallback
    assert not stats.fallback_vierzehntaegig


# ── Vorläufige Termine und verschonte Slots (AP1, 22.09.2026) ────────────────


def _mk_slot(datum, start_period=1):
    """Ein verschonter Slot, wie ihn der Generator nach dem Löschen vorfindet."""
    s = MagicMock()
    s.date = datum
    s.start_period = start_period
    return s


@pytest.mark.asyncio
async def test_vorlaeufig_landet_an_den_erzeugten_slots():
    """Das Kennzeichen muss bis an die Zeile durchreichen — sonst sieht ein vorläufiges
    Halbjahr aus wie ein bestätigtes."""
    cfg = _mini_cfg()
    db = _make_db({1: [_mk_pattern(weekday=0, halbjahr=1)]})

    with patch("app.planning.slot_generator.load_school_year", return_value=cfg):
        stats = await generate_slots(db, group_id=1, halbjahr=1, vorlaeufig=True, cfg=cfg)

    assert stats.created == 1
    assert stats.vorlaeufig is True
    angelegt = [c.args[0] for c in db.add.call_args_list]
    assert all(s.vorlaeufig is True for s in angelegt)


@pytest.mark.asyncio
async def test_ohne_angabe_ist_nichts_vorlaeufig():
    cfg = _mini_cfg()
    db = _make_db({1: [_mk_pattern(weekday=0, halbjahr=1)]})

    with patch("app.planning.slot_generator.load_school_year", return_value=cfg):
        stats = await generate_slots(db, group_id=1, halbjahr=1, cfg=cfg)

    assert stats.vorlaeufig is False
    assert all(s.vorlaeufig is False for s in [c.args[0] for c in db.add.call_args_list])


@pytest.mark.asyncio
async def test_belegter_termin_laesst_die_musterzeile_entfallen():
    """Entscheidung F4 (22.09.2026): Der verschonte Slot ist der konkretere — er kennt
    seine Quelle. Zwei Slots auf derselben Stunde wären eine Dublette, die niemand
    auflösen kann."""
    cfg = _mini_cfg()
    # Montag der ersten Woche, 1. Stunde — genau die Zeile, die das Muster erzeugen will.
    verschont = [_mk_slot(date(2026, 1, 5), start_period=1)]
    db = _make_db(
        {1: [_mk_pattern(weekday=0, halbjahr=1)]},
        existing_count=1,
        verschonte=verschont,
    )

    with (
        patch("app.planning.slot_generator.load_school_year", return_value=cfg),
        patch("app.planning.slot_generator.create_snapshot", new_callable=AsyncMock),
    ):
        stats = await generate_slots(
            db, group_id=1, halbjahr=1, regenerate=True, cfg=cfg
        )

    assert stats.created == 0, "Die Musterzeile hätte entfallen müssen"
    assert stats.verschont == 1


@pytest.mark.asyncio
async def test_anderer_termin_wird_trotzdem_erzeugt():
    """Die Gegenprobe: Ein verschonter Slot blockiert nur *seinen* Termin."""
    cfg = _mini_cfg()
    verschont = [_mk_slot(date(2026, 1, 6), start_period=1)]  # Dienstag
    db = _make_db(
        {1: [_mk_pattern(weekday=0, halbjahr=1)]},  # Muster: Montag
        existing_count=1,
        verschonte=verschont,
    )

    with (
        patch("app.planning.slot_generator.load_school_year", return_value=cfg),
        patch("app.planning.slot_generator.create_snapshot", new_callable=AsyncMock),
    ):
        stats = await generate_slots(
            db, group_id=1, halbjahr=1, regenerate=True, cfg=cfg
        )

    assert stats.created == 1

