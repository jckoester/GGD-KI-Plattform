"""Der Stundenbezug einer Konversation (0.15, Päckchen A Schritt 2).

Setzen darf ihn nur die Lehrkraft der Gruppe der Stunde; er bringt die Gruppe mit, steht als
Systemzeile im Prompt — bei jedem Aufbau neu geprüft — und überlebt das Wiederöffnen.

Die Chat-Tests halten die Anfrage an `compose_system_content` an: Bis dorthin ist die
Konversation angelegt und die Bezugszeile gebaut; Netz und Modell bleiben unberührt. Die
Kontextsuche ist durch eine Attrappe ersetzt, die festhält, was die Konversation trägt.
"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import psycopg2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.chat.tools import ToolContext
from app.context.bausteine import Kontext
from app.db.models import Conversation, LessonSlot
from app.planning.assistant_tools import _handle_get_lesson_detail, _handle_update_lesson_phases
from app.planning.stundenbezug import bezugszeile
from tests.integration.conftest import STUDENT_PSEUDO, TEACHER1_PSEUDO, TEACHER2_PSEUDO

EIGENE = 771   # teacher1 unterrichtet, student1 lernt
FREMDE = 772   # nur teacher2
ZWEITE = 773   # noch eine Gruppe von teacher1
ARCHIV = 774   # teacher1 legt an, verliert dann die Mitgliedschaft
GRUPPEN = (EIGENE, FREMDE, ZWEITE, ARCHIV)


class _BisHierher(Exception):
    """Die Anfrage ist bis zum System-Prompt gekommen."""


@pytest.fixture(scope="module")
def db(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) "
                    "VALUES (771, 'stundenbezug', 'Stundenbezug', 0) ON CONFLICT (id) DO NOTHING")
        for gid in GRUPPEN:
            cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                        "VALUES (%s, %s, %s, 'teaching_group', 771) ON CONFLICT (id) DO NOTHING",
                        (gid, f"9b Bezug {gid}", f"stundenbezug-{gid}"))
        for gid, pseudonym, rolle in ((EIGENE, TEACHER1_PSEUDO, "teacher"),
                                      (EIGENE, STUDENT_PSEUDO, "student"),
                                      (FREMDE, TEACHER2_PSEUDO, "teacher"),
                                      (ZWEITE, TEACHER1_PSEUDO, "teacher"),
                                      (ARCHIV, TEACHER1_PSEUDO, "teacher")):
            cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                        "VALUES (%s, %s, %s, 'eigen') ON CONFLICT DO NOTHING", (gid, pseudonym, rolle))
    conn.commit()
    yield conn
    with conn.cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE group_id = ANY(%s)", (list(GRUPPEN),))
        cur.execute("DELETE FROM context_nodes WHERE read_scope_group_id = ANY(%s)", (list(GRUPPEN),))
        cur.execute("DELETE FROM groups WHERE id = ANY(%s)", (list(GRUPPEN),))
        cur.execute("DELETE FROM subjects WHERE id = 771")
    conn.commit()
    conn.close()


def _sitzungen(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def _stunde(client, h, gruppe, titel="Hebelgesetz"):
    ue = (await client.post(f"/planning/groups/{gruppe}/units", headers=h,
                            json={"titel": "Mechanik", "farbe": 0})).json()["id"]
    resp = await client.post(f"/planning/units/{ue}/lessons", headers=h, json={"titel": titel})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def _chat(client, headers, **rumpf):
    """`POST /chat` bis zum System-Prompt. → (Antwort | None, Konversation, Bezugszeile)."""
    gesehen = {}

    async def kontext(**kw):
        conv = await kw["db"].get(Conversation, kw["chat_id"])
        gesehen["konversation"] = SimpleNamespace(
            group_id=conv.group_id, subject_id=conv.subject_id, stunde_node_id=conv.stunde_node_id)
        return Kontext(text="")

    def compose(*args, **kw):
        gesehen["bezug"] = kw.get("bezug")
        raise _BisHierher

    with patch("app.chat.router.kontext_fuer_frage", side_effect=kontext), \
         patch("app.chat.router.compose_system_content", side_effect=compose):
        try:
            resp = await client.post("/chat", headers=headers, json={
                "messages": [{"role": "user", "content": "Wie fange ich die Stunde an?"}], **rumpf,
            })
        except _BisHierher:
            resp = None
    return resp, gesehen.get("konversation"), gesehen.get("bezug")


def _konversation(conn, gruppe, stunde=None, pseudonym=TEACHER1_PSEUDO):
    """Eine gespeicherte Konversation — so, wie sie aus der Historie wieder geöffnet wird."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO conversations (pseudonym, group_id, subject_id, stunde_node_id, model_used) "
                    "VALUES (%s, %s, 771, %s, 'chat-standard') RETURNING id",
                    (pseudonym, gruppe, stunde))
        kennung = cur.fetchone()[0]
    conn.commit()
    return str(kennung)


def _bezug_in_db(conn, konversation):
    with conn.cursor() as cur:
        cur.execute("SELECT stunde_node_id FROM conversations WHERE id = %s", (konversation,))
        wert = cur.fetchone()[0]
    return str(wert) if wert else None


# ── Setzen ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bezug_aus_der_entwurfsansicht(test_client, auth_headers, db):
    stunde = await _stunde(test_client, auth_headers, EIGENE)
    resp, konv, bezug = await _chat(test_client, auth_headers, group_id=EIGENE, stunde_node_id=stunde)
    assert resp is None, resp.text
    assert (konv.group_id, str(konv.stunde_node_id)) == (EIGENE, stunde)
    assert "„Hebelgesetz“" in bezug and f"Kennung {stunde}" in bezug
    assert f"9b Bezug {EIGENE}" in bezug


@pytest.mark.asyncio
async def test_die_stunde_bringt_ihre_gruppe_mit(test_client, auth_headers, db):
    stunde = await _stunde(test_client, auth_headers, EIGENE)
    resp, konv, _ = await _chat(test_client, auth_headers, stunde_node_id=stunde)
    assert resp is None, resp.text
    assert (konv.group_id, konv.subject_id, str(konv.stunde_node_id)) == (EIGENE, 771, stunde)


@pytest.mark.asyncio
async def test_gruppe_widerspricht_der_stunde(test_client, auth_headers, db):
    stunde = await _stunde(test_client, auth_headers, EIGENE)
    resp, konv, _ = await _chat(test_client, auth_headers, group_id=ZWEITE, stunde_node_id=stunde)
    assert resp is not None and resp.status_code == 422, resp and resp.text
    assert konv is None


# ── Wächter: wer keinen Bezug setzen darf ───────────────────────────────────


@pytest.mark.asyncio
async def test_fremde_stunde(test_client, auth_headers, auth_headers_teacher2, db):
    fremd = await _stunde(test_client, auth_headers_teacher2, FREMDE)
    resp, konv, _ = await _chat(test_client, auth_headers, stunde_node_id=fremd)
    assert resp is not None and resp.status_code == 403, resp and resp.text
    assert konv is None


@pytest.mark.asyncio
async def test_unbekannte_stunde(test_client, auth_headers, db):
    resp, konv, _ = await _chat(test_client, auth_headers, stunde_node_id=str(uuid4()))
    assert resp is not None and resp.status_code == 404, resp and resp.text
    assert konv is None


@pytest.mark.asyncio
async def test_schuelerin_der_gruppe(test_client, auth_headers, auth_headers_student, db):
    """Mitglied heißt nicht Lehrkraft — ein Bezug setzt Lehrkraft der Gruppe voraus."""
    stunde = await _stunde(test_client, auth_headers, EIGENE)
    resp, konv, _ = await _chat(test_client, auth_headers_student, stunde_node_id=stunde)
    assert resp is not None and resp.status_code == 403, resp and resp.text
    assert konv is None


@pytest.mark.asyncio
async def test_eigentuemerin_ohne_mitgliedschaft(test_client, auth_headers, db):
    """Archiv-Fall: lesen ja, als Bezug setzen nein (Jan, 09.10.2026)."""
    stunde = await _stunde(test_client, auth_headers, ARCHIV)
    with db.cursor() as cur:
        cur.execute("DELETE FROM group_memberships WHERE group_id = %s AND pseudonym = %s",
                    (ARCHIV, TEACHER1_PSEUDO))
    db.commit()
    resp, konv, _ = await _chat(test_client, auth_headers, stunde_node_id=stunde)
    assert resp is not None and resp.status_code == 403, resp and resp.text
    assert konv is None


# ── Die Systemzeile ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bezug_ueberlebt_das_wiederoeffnen(test_client, auth_headers, db):
    stunde = await _stunde(test_client, auth_headers, EIGENE, titel="Drehmoment")
    konversation = _konversation(db, EIGENE, stunde)
    resp, _, bezug = await _chat(test_client, auth_headers, conversation_id=konversation)
    assert resp is None, resp.text
    assert bezug and "„Drehmoment“" in bezug and f"Kennung {stunde}" in bezug


@pytest.mark.asyncio
async def test_ohne_bezug_keine_systemzeile(test_client, auth_headers, db):
    konversation = _konversation(db, EIGENE)
    resp, _, bezug = await _chat(test_client, auth_headers, conversation_id=konversation)
    assert resp is None, resp.text
    assert bezug is None


@pytest.mark.asyncio
async def test_zeile_nur_mit_lesezugang(test_client, auth_headers, auth_headers_teacher2, db):
    """Beim Aufbau neu geprüft: Ein Bezug auf eine fremde Stunde — hier unmittelbar in der
    Datenbank gesetzt — erscheint nicht."""
    fremd = await _stunde(test_client, auth_headers_teacher2, FREMDE, titel="Geheimplan")
    konversation = _konversation(db, EIGENE, fremd)
    resp, _, bezug = await _chat(test_client, auth_headers, conversation_id=konversation)
    assert resp is None, resp.text
    assert bezug is None


@pytest.mark.asyncio
async def test_zeile_nennt_termin(test_client, auth_headers, db, async_engine):
    stunde = await _stunde(test_client, auth_headers, EIGENE, titel="Rolle")
    async with _sitzungen(async_engine)() as s:
        s.add(LessonSlot(id=uuid4(), group_id=EIGENE, date=date(2031, 3, 3), halbjahr=2, periods=2,
                         start_period=3, kategorie="unterricht", stunde_node_id=UUID(stunde)))
        await s.commit()
        zeile = await bezugszeile(s, UUID(stunde), SimpleNamespace(sub=TEACHER1_PSEUDO))
    assert f"(9b Bezug {EIGENE}, Mo 3.3., 3.–4. Stunde)" in zeile


# ── PATCH: Gruppe wechseln ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gruppenwechsel_loescht_den_bezug(test_client, auth_headers, db):
    stunde = await _stunde(test_client, auth_headers, EIGENE)
    konversation = _konversation(db, EIGENE, stunde)

    resp = await test_client.patch(f"/conversations/{konversation}", headers=auth_headers,
                                   json={"title": "Umbenannt"})
    assert resp.status_code == 200, resp.text
    assert _bezug_in_db(db, konversation) == stunde, "Nur der Titel — der Bezug bleibt."

    resp = await test_client.patch(f"/conversations/{konversation}", headers=auth_headers,
                                   json={"group_id": ZWEITE})
    assert resp.status_code == 200, resp.text
    assert _bezug_in_db(db, konversation) is None


@pytest.mark.asyncio
async def test_fach_statt_gruppe_loescht_den_bezug(test_client, auth_headers, db):
    stunde = await _stunde(test_client, auth_headers, EIGENE)
    konversation = _konversation(db, EIGENE, stunde)
    resp = await test_client.patch(f"/conversations/{konversation}", headers=auth_headers,
                                   json={"subject_id": 771})
    assert resp.status_code == 200, resp.text
    assert _bezug_in_db(db, konversation) is None


# ── Die Stundenwerkzeuge nehmen den Bezug als Vorgabe ────────────────────────


def _ctx(s, stunde=None, sub=TEACHER1_PSEUDO):
    return ToolContext(db=s, user=SimpleNamespace(sub=sub), group_id=None, conversation_id=None,
                       stunde_node_id=UUID(stunde) if stunde else None)


@pytest.mark.asyncio
async def test_werkzeuge_ohne_kennung_nehmen_den_bezug(test_client, auth_headers, db, async_engine):
    stunde = await _stunde(test_client, auth_headers, EIGENE, titel="Flaschenzug")
    async with _sitzungen(async_engine)() as s:
        gelesen = await _handle_get_lesson_detail({}, _ctx(s, stunde))
    assert gelesen.get("titel") == "Flaschenzug", gelesen

    async with _sitzungen(async_engine)() as s:
        aus = await _handle_update_lesson_phases(
            {"phasen": [{"name": "Einstieg", "dauer_min": 5}]}, _ctx(s, stunde))
    assert aus.get("ok") is True, aus
    async with _sitzungen(async_engine)() as s:
        gelesen = await _handle_get_lesson_detail({"node_id": stunde}, _ctx(s))
    assert [p["name"] for p in gelesen["phasen"]] == ["Einstieg"]


@pytest.mark.asyncio
async def test_der_bezug_ist_keine_erlaubnis(test_client, auth_headers_teacher2, db, async_engine):
    """Eine Vorgabe aus der Konversation öffnet keine fremde Stunde."""
    fremd = await _stunde(test_client, auth_headers_teacher2, FREMDE)
    async with _sitzungen(async_engine)() as s:
        assert await _handle_get_lesson_detail({}, _ctx(s, fremd)) == {"error": "Stunde nicht gefunden"}
        aus = await _handle_update_lesson_phases({"phasen": [{"name": "X", "dauer_min": 5}]}, _ctx(s, fremd))
    assert aus == {"error": "Stunde nicht gefunden"}


@pytest.mark.asyncio
async def test_ohne_kennung_und_ohne_bezug(db, async_engine):
    async with _sitzungen(async_engine)() as s:
        aus = await _handle_get_lesson_detail({}, _ctx(s))
    assert "keine Bezugsstunde" in aus["error"]
