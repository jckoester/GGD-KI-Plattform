"""UP-7 Schritt 1: Tests für get_current_topic (Service „Aktuelles Thema")."""

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import psycopg2
import pytest

from app.context.service import get_context_for_query
from app.db.models import ContextNode, Conversation, LessonSlot
from app.planning.student_context import (
    CurrentTopic,
    TopicSlot,
    get_current_topic,
    get_exam_scope,
    render_topic_block,
)

GROUP_ID = 200
TODAY = date(2026, 3, 15)


@pytest.fixture(scope="module")
def seed_sc_group(db_url, run_migrations):
    """Fach + Unterrichtsgruppe (id 200) für die student_context-Tests."""
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO subjects (id, slug, name, sort_order) "
            "VALUES (200, 'sc-test', 'SC Test', 0) ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO groups (id, name, slug, type, subject_id) "
            "VALUES (200, 'SC 5b', 'sc-5b', 'teaching_group', 200) "
            "ON CONFLICT (id) DO NOTHING"
        )
    conn.commit()
    conn.close()


def _ue(title: str) -> ContextNode:
    return ContextNode(
        id=uuid4(), category="artifact", content_type="unterrichtseinheit",
        title=title, metadata_={}, read_scope="group", read_scope_group_id=GROUP_ID,
        status="active",
    )


def _stunde(title: str, stundenziel: str | None = None) -> ContextNode:
    return ContextNode(
        id=uuid4(), category="artifact", content_type="unterrichtsstunde",
        title=title, metadata_={"stundenziel": stundenziel} if stundenziel else {},
        read_scope="group", read_scope_group_id=GROUP_ID, status="active",
    )


def _slot(d: date, *, kategorie="unterricht", thema=None, ue_id=None, stunde_id=None,
          nachbereitet=False, auto=False, start_period=3) -> LessonSlot:
    return LessonSlot(
        id=uuid4(), group_id=GROUP_ID, date=d, halbjahr=2, periods=1,
        start_period=start_period, kategorie=kategorie, thema=thema,
        ue_node_id=ue_id, stunde_node_id=stunde_id,
        nachbereitet_at=datetime(2026, 3, 1, tzinfo=timezone.utc) if nachbereitet else None,
        nachbereitet_auto=auto,
    )


@pytest.mark.asyncio
async def test_current_topic_zuletzt_und_naechste(db_session, seed_sc_group):
    ue = _ue("Die Natürlichen Zahlen")
    stunde = _stunde("Stellenwertsysteme verstehen", "SuS verstehen Stellenwerte")
    db_session.add_all([ue, stunde])
    db_session.add_all([
        _slot(date(2026, 3, 10), thema="Zahlen runden", ue_id=ue.id, nachbereitet=True),
        _slot(date(2026, 3, 17), stunde_id=stunde.id, ue_id=ue.id, start_period=1),
        _slot(date(2026, 3, 19), thema="Übungen", ue_id=ue.id),
    ])
    await db_session.flush()

    topic = await get_current_topic(db_session, GROUP_ID, TODAY)
    assert topic is not None
    assert topic.zuletzt.thema == "Zahlen runden"
    assert topic.zuletzt.ue_titel == "Die Natürlichen Zahlen"
    assert [s.thema for s in topic.naechste] == ["Stellenwertsysteme verstehen", "Übungen"]
    assert topic.naechste[0].stundenziel == "SuS verstehen Stellenwerte"


@pytest.mark.asyncio
async def test_current_topic_ausfall_uebersprungen(db_session, seed_sc_group):
    db_session.add_all([
        _slot(date(2026, 3, 17), kategorie="ausfall", thema="Fällt aus"),
        _slot(date(2026, 3, 18), thema="Echtes Thema"),
    ])
    await db_session.flush()

    topic = await get_current_topic(db_session, GROUP_ID, TODAY)
    assert topic is not None
    assert [s.thema for s in topic.naechste] == ["Echtes Thema"]


@pytest.mark.asyncio
async def test_current_topic_nicht_nachbereitet_kein_zuletzt(db_session, seed_sc_group):
    # Vergangener, belegter, aber NICHT nachbereiteter Slot → zählt nicht als behandelt.
    db_session.add(_slot(date(2026, 3, 10), thema="Ungesichert", nachbereitet=False))
    await db_session.flush()

    topic = await get_current_topic(db_session, GROUP_ID, TODAY)
    assert topic is None  # kein zuletzt, kein naechste


@pytest.mark.asyncio
async def test_current_topic_leer_none(db_session, seed_sc_group):
    topic = await get_current_topic(db_session, GROUP_ID, TODAY)
    assert topic is None


# ── Schritt 2: Render-Block + Context-Service-Integration ────────────────────


def test_render_topic_block_felder():
    topic = CurrentTopic(
        zuletzt=TopicSlot(date(2026, 10, 13), "unterricht", "Zahlen runden", None,
                          "Die Natürlichen Zahlen"),
        naechste=[TopicSlot(date(2026, 10, 15), "unterricht", "Stellenwertsysteme",
                            "Ziel X", "Die Natürlichen Zahlen")],
    )
    md = render_topic_block(topic, "Mathematik, 5b")
    assert "## Aktueller Unterricht (Mathematik, 5b)" in md
    assert '13.10.): Zahlen runden (UE „Die Natürlichen Zahlen")' in md
    assert "15.10.): Stellenwertsysteme — Ziel X" in md
    assert "Nächste Stunde" in md


@pytest.mark.asyncio
async def test_context_block_mit_gruppe(db_session, seed_sc_group):
    today = date.today()
    conv = Conversation(
        id=uuid4(), pseudonym="stud-sc", group_id=GROUP_ID, model_used="test"
    )
    db_session.add(conv)
    db_session.add_all([
        _slot(today - timedelta(days=7), thema="Vergangenes Thema", nachbereitet=True),
        _slot(today + timedelta(days=2), thema="Kommendes Thema"),
    ])
    await db_session.flush()

    ctx = await get_context_for_query(
        assistant_id=None, pseudonym="stud-sc", query_text="Was machen wir gerade?",
        chat_id=conv.id, db=db_session,
    )
    assert "## Aktueller Unterricht" in ctx
    assert "Vergangenes Thema" in ctx
    assert "Kommendes Thema" in ctx


@pytest.mark.asyncio
async def test_context_block_ohne_gruppe(db_session, seed_sc_group):
    conv = Conversation(
        id=uuid4(), pseudonym="stud-sc", group_id=None, model_used="test"
    )
    db_session.add(conv)
    await db_session.flush()

    ctx = await get_context_for_query(
        assistant_id=None, pseudonym="stud-sc", query_text="x",
        chat_id=conv.id, db=db_session,
    )
    assert "Aktueller Unterricht" not in ctx


# ── Schritt 3: Klassenarbeits-Scope ──────────────────────────────────────────


def _stunde_mit_refs(title, refs, refs_offen=None):
    return ContextNode(
        id=uuid4(), category="artifact", content_type="unterrichtsstunde", title=title,
        read_scope="group", read_scope_group_id=GROUP_ID, status="active",
        metadata_={"refs": refs, "refs_offen": refs_offen or []},
    )


@pytest.mark.asyncio
async def test_exam_scope_explizite_ue_refs_offen_und_nachbereitung(db_session, seed_sc_group):
    today = date(2026, 3, 15)
    ue = _ue("Die Natürlichen Zahlen")
    R1, R2, R3 = (str(uuid4()) for _ in range(3))
    s_nachb = _stunde_mit_refs(
        "Runden",
        refs=[{"node_id": R1, "titel": "Runden K", "code": "1.1"},
              {"node_id": R2, "titel": "Offen K", "code": "1.2"}],
        refs_offen=[R2],
    )
    s_unnachb = _stunde_mit_refs("Ungesichert", refs=[{"node_id": R3, "titel": "Nicht K"}])
    db_session.add_all([ue, s_nachb, s_unnachb])
    db_session.add_all([
        _slot(date(2026, 3, 10), ue_id=ue.id, stunde_id=s_nachb.id, nachbereitet=True),
        _slot(date(2026, 3, 12), ue_id=ue.id, stunde_id=s_unnachb.id, nachbereitet=False),
        _slot(date(2026, 3, 20), kategorie="pruefung", ue_id=ue.id),
    ])
    await db_session.flush()

    scope = await get_exam_scope(db_session, GROUP_ID, today=today)
    assert scope is not None
    assert scope.exam_date == date(2026, 3, 20)
    assert scope.unit_titles == ["Die Natürlichen Zahlen"]
    # Nur die nachbereitete, nicht-offene Kompetenz; refs_offen + nicht-nachbereitet raus.
    assert scope.ref_node_ids == [R1]
    assert "Runden" in scope.topics and "Ungesichert" in scope.topics


@pytest.mark.asyncio
async def test_exam_scope_slot_historie_fallback(db_session, seed_sc_group):
    ue = _ue("UE-Historie")
    db_session.add(ue)
    db_session.add_all([
        _slot(date(2026, 3, 10), ue_id=ue.id, thema="Thema A"),
        _slot(date(2026, 3, 20), kategorie="pruefung"),  # Prüfung ohne UE
    ])
    await db_session.flush()

    scope = await get_exam_scope(db_session, GROUP_ID, today=date(2026, 3, 15))
    assert scope is not None
    assert scope.unit_titles == ["UE-Historie"]


@pytest.mark.asyncio
async def test_exam_scope_keine_pruefung_none(db_session, seed_sc_group):
    db_session.add(_slot(date(2026, 3, 20), thema="Nur Unterricht"))
    await db_session.flush()
    scope = await get_exam_scope(db_session, GROUP_ID, today=date(2026, 3, 15))
    assert scope is None


# ── Schritt 4: Tool-Ausgabe + KA-Zeile im Kontext-Block ──────────────────────


@pytest.mark.asyncio
async def test_get_exam_scope_tool_output(db_session, seed_sc_group):
    from app.chat.tools import ToolContext
    from app.planning.assistant_tools import _handle_get_exam_scope

    ue = _ue("KA-UE")
    db_session.add(ue)
    db_session.add(_slot(date.today() + timedelta(days=5), kategorie="pruefung", ue_id=ue.id))
    await db_session.flush()

    ctx = ToolContext(db=db_session, user=None, group_id=GROUP_ID, conversation_id=None)
    out = await _handle_get_exam_scope({}, ctx)
    assert out["unit_titles"] == ["KA-UE"]
    assert "exam_date" in out and out["refs"] == []


@pytest.mark.asyncio
async def test_context_block_enthaelt_klassenarbeit(db_session, seed_sc_group):
    today = date.today()
    conv = Conversation(
        id=uuid4(), pseudonym="stud-sc", group_id=GROUP_ID, model_used="test"
    )
    ue = _ue("KA-UE2")
    db_session.add_all([conv, ue])
    db_session.add(_slot(today + timedelta(days=3), kategorie="pruefung", ue_id=ue.id))
    await db_session.flush()

    ctx = await get_context_for_query(
        assistant_id=None, pseudonym="stud-sc", query_text="Wann ist die KA?",
        chat_id=conv.id, db=db_session,
    )
    assert "Klassenarbeit:" in ctx
    assert "KA-UE2" in ctx


# ── Schritt 5: Lernstand End-to-End (Engagement-UNION) ───────────────────────


@pytest.mark.asyncio
async def test_lernstand_eingefuehrte_kompetenz_im_schuelerkontext(db_session, seed_sc_group):
    """UP-5 schreibt introduced/lesson_plan → erscheint im Schüler-Lernstand;
    eine nicht eingeführte (refs_offen) Kompetenz erscheint nicht."""
    from app.context.retrieval import get_engagement_context
    from app.db.models import GroupMembership, NodeEngagement

    db_session.add(
        GroupMembership(group_id=GROUP_ID, pseudonym="stud-lern", role_in_group="student")
    )
    n_intro = ContextNode(
        id=uuid4(), category="knowledge", content_type="ik_kompetenz",
        title="Zahlen runden K", read_scope="school", status="active", metadata_={},
    )
    n_offen = ContextNode(
        id=uuid4(), category="knowledge", content_type="ik_kompetenz",
        title="Nicht eingeführt K", read_scope="school", status="active", metadata_={},
    )
    db_session.add_all([n_intro, n_offen])
    # Nur n_intro wurde als introduced/lesson_plan geschrieben (n_offen war refs_offen).
    db_session.add(NodeEngagement(
        group_id=GROUP_ID, node_id=n_intro.id, relation="introduced", source="lesson_plan",
        metadata_={},
    ))
    await db_session.flush()

    entries = await get_engagement_context([n_intro.id, n_offen.id], "stud-lern", db_session)
    titles = {e.node.title for e in entries}
    assert "Zahlen runden K" in titles
    assert "Nicht eingeführt K" not in titles
