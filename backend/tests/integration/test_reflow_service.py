"""UP-6 Schritt 1: Tests für build_reflow_context."""

from datetime import timedelta
from uuid import uuid4

import psycopg2
import pytest

from app.db.models import ContextNode, LessonSlot
from app.planning.calendar import load_school_year
from app.planning.reflow_service import build_reflow_context

GROUP_ID = 201
_CFG = load_school_year()
BASE = _CFG.beginn + timedelta(days=14)  # gut im 1. Halbjahr


@pytest.fixture(scope="module")
def seed_reflow_group(db_url, run_migrations):
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO subjects (id, slug, name, sort_order) "
            "VALUES (201, 'rf-test', 'RF Test', 0) ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO groups (id, name, slug, type, subject_id) "
            "VALUES (201, 'RF 9a', 'rf-9a', 'teaching_group', 201) "
            "ON CONFLICT (id) DO NOTHING"
        )
    conn.commit()
    conn.close()


def _ue(title):
    return ContextNode(
        id=uuid4(), category="artifact", content_type="unterrichtseinheit", title=title,
        metadata_={}, read_scope="group", read_scope_group_id=GROUP_ID,
        write_scope="group", write_scope_group_id=GROUP_ID, status="active",
    )


def _stunde(title, phasen=None, refs_offen=None):
    return ContextNode(
        id=uuid4(), category="artifact", content_type="unterrichtsstunde", title=title,
        metadata_={"phasen": phasen or [], "refs_offen": refs_offen or []},
        read_scope="group", read_scope_group_id=GROUP_ID, status="active",
    )


def _slot(d, *, kategorie="unterricht", thema=None, ue_id=None, stunde_id=None,
          pinned=False, periods=1, start_period=3):
    return LessonSlot(
        id=uuid4(), group_id=GROUP_ID, date=d, halbjahr=1, periods=periods,
        start_period=start_period, kategorie=kategorie, thema=thema, ue_node_id=ue_id,
        stunde_node_id=stunde_id, pinned=pinned,
    )


@pytest.mark.asyncio
async def test_reflow_folge_bis_fixpunkt_und_vorrat(db_session, seed_reflow_group):
    ue = _ue("UE Bruchrechnung")
    db_session.add(ue)
    betroffen = _slot(BASE, ue_id=ue.id, thema="Auslöser")
    db_session.add_all([
        betroffen,
        _slot(BASE + timedelta(days=1), ue_id=ue.id, thema="Folge 1"),
        _slot(BASE + timedelta(days=2), ue_id=ue.id, thema="Folge 2"),
        _slot(BASE + timedelta(days=3), kategorie="pruefung", pinned=True),  # Fixpunkt
        _slot(BASE + timedelta(days=4), thema="Dahinter 1"),
        _slot(BASE + timedelta(days=5), thema="Dahinter 2"),
    ])
    await db_session.flush()

    ctx = await build_reflow_context(
        db_session, GROUP_ID, trigger="ausfall", slot_ids=[betroffen.id]
    )
    assert ctx.halbjahr == 1
    assert [s.thema for s in ctx.betroffene] == ["Auslöser"]
    # Folge endet vor dem Fixpunkt (Auslöser ausgenommen).
    assert [s.thema for s in ctx.folge_slots] == ["Folge 1", "Folge 2"]
    # Genau ein Fixpunkt, mit 2 Slots Vorrat dahinter.
    assert len(ctx.fixpunkte) == 1
    assert ctx.fixpunkte[0].kategorie == "pruefung"
    assert ctx.fixpunkte[0].slots_dahinter == 2
    # Bilanz enthält die betroffene UE.
    assert any(b.titel == "UE Bruchrechnung" for b in ctx.bilanz)


@pytest.mark.asyncio
async def test_reflow_planungsstand_und_phasen_kurzform(db_session, seed_reflow_group):
    stunde = _stunde("Geplante Stunde", phasen=[
        {"id": "a", "prio": "kern", "dauer_min": 10, "status": "geplant"},
        {"id": "b", "prio": "kern", "dauer_min": 10, "status": "geplant"},
        {"id": "c", "prio": "uebung", "dauer_min": 10, "status": "geplant"},
    ])
    db_session.add(stunde)
    s = _slot(BASE, stunde_id=stunde.id, thema="X")
    db_session.add(s)
    await db_session.flush()

    ctx = await build_reflow_context(db_session, GROUP_ID, trigger="manual", slot_ids=[s.id])
    state = ctx.betroffene[0]
    assert state.planungsstand == "geplant"
    assert state.phasen_kurzform == "[kern×2, uebung×1]"


@pytest.mark.asyncio
async def test_reflow_open_phases_quellstunde(db_session, seed_reflow_group):
    R = str(uuid4())
    stunde = _stunde(
        "Nachzubereiten",
        phasen=[
            {"id": "p1", "name": "Erarbeitung", "prio": "kern", "dauer_min": 20, "status": "erledigt"},
            {"id": "p2", "name": "Vertiefung", "prio": "vertiefung", "dauer_min": 15, "status": "offen"},
        ],
        refs_offen=[R],
    )
    db_session.add(stunde)
    s = _slot(BASE, stunde_id=stunde.id, thema="Quelle")
    db_session.add(s)
    await db_session.flush()

    ctx = await build_reflow_context(
        db_session, GROUP_ID, trigger="open_phases", slot_ids=[s.id]
    )
    assert ctx.offene_phasen is not None
    assert [p.name for p in ctx.offene_phasen.phasen] == ["Vertiefung"]
    assert ctx.offene_phasen.refs_offen == [R]


@pytest.mark.asyncio
async def test_reflow_invalid_trigger():
    with pytest.raises(ValueError, match="trigger"):
        await build_reflow_context(None, GROUP_ID, trigger="quatsch")


@pytest.mark.asyncio
async def test_detect_overhang(db_session, seed_reflow_group):
    from app.db.models import ContextEdge
    from app.planning.reflow_service import detect_overhang

    kapitel = ContextNode(
        id=uuid4(), category="knowledge", content_type="kapitel", title="Kap",
        metadata_={"std": 2}, read_scope="school", status="active",
    )
    ue = _ue("UE Überhang")
    db_session.add_all([kapitel, ue])
    await db_session.flush()
    db_session.add(
        ContextEdge(id=uuid4(), from_node_id=ue.id, to_node_id=kapitel.id, relation="references")
    )
    db_session.add_all([
        _slot(BASE, ue_id=ue.id),
        _slot(BASE + timedelta(days=1), ue_id=ue.id),
        _slot(BASE + timedelta(days=2), ue_id=ue.id),  # zugewiesen 3 > soll 2 → puffer 1
        _slot(BASE + timedelta(days=3), kategorie="pruefung"),
    ])
    await db_session.flush()

    findings = await detect_overhang(db_session, GROUP_ID)
    f = next(x for x in findings if x.titel == "UE Überhang")
    assert f.ueberhang == 1
    assert f.fixpunkt_datum == (BASE + timedelta(days=3)).isoformat()
