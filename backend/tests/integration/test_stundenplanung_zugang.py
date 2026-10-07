"""Stundenplanung ohne Gruppenbezug: Den Zugang prüft das Werkzeug (0.15, Schritt 1).

`lesson_planning` greift an der Lehrkraft-Rolle, nicht an der Gruppe der Konversation
(`tools_for`) — welche Stunde gemeint ist, sagt allein das Modell. Diese Tests halten
fest, dass eine Kennung allein nichts öffnet: nicht ohne Gruppenbezug, nicht aus einer
Konversation in der fremden Gruppe, nicht als Schüler:in der Gruppe.
"""
from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg2
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.chat.tools import ToolContext
from app.db.models import LessonSlot, SlotPlanSnapshot
from app.planning.assistant_tools import (
    _handle_get_lesson_detail,
    _handle_get_unit_detail,
    _handle_update_lesson_phases,
)
from tests.integration.conftest import STUDENT_PSEUDO, TEACHER1_PSEUDO, TEACHER2_PSEUDO

EIGENE = 746   # teacher1 unterrichtet, student1 ist Schüler:in
FREMDE = 747   # nur teacher2
ARCHIV = 748   # teacher1 legt an, verliert dann die Mitgliedschaft
GRUPPEN = (EIGENE, FREMDE, ARCHIV)

NICHT_GEFUNDEN = {"error": "Stunde nicht gefunden"}


@pytest.fixture(scope="module")
def gruppen(db_url, run_migrations):
    """Fächer, Gruppen, Mitgliedschaften — und danach wieder weg.

    Das Wegräumen ist nötig: Gruppen von teacher1 mit Slots träfen sonst die
    Tagesauswertungen in `test_planning_api.py` (vgl. `test_optimistisches_sperren.py`).
    """
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        for gid in GRUPPEN:
            cur.execute("INSERT INTO subjects (id, slug, name, sort_order) "
                        "VALUES (%s, %s, %s, 0) ON CONFLICT (id) DO NOTHING",
                        (gid, f"stundenzugang-{gid}", f"Stundenzugang {gid}"))
            cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                        "VALUES (%s, %s, %s, 'teaching_group', %s) ON CONFLICT (id) DO NOTHING",
                        (gid, f"9z Zugang {gid}", f"zugang-{gid}", gid))
        for gid, pseudonym, rolle in ((EIGENE, TEACHER1_PSEUDO, "teacher"),
                                      (EIGENE, STUDENT_PSEUDO, "student"),
                                      (FREMDE, TEACHER2_PSEUDO, "teacher"),
                                      (ARCHIV, TEACHER1_PSEUDO, "teacher")):
            cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                        "VALUES (%s, %s, %s, 'eigen') ON CONFLICT DO NOTHING", (gid, pseudonym, rolle))
    conn.commit()
    yield conn
    with conn.cursor() as cur:
        # Erst die Planungsknoten — beim Löschen der Gruppe würde ihr Scope NULL.
        cur.execute("DELETE FROM context_nodes WHERE read_scope_group_id = ANY(%s)", (list(GRUPPEN),))
        # Slots, Mitgliedschaften und Snapshots gehen per Kaskade mit.
        cur.execute("DELETE FROM groups WHERE id = ANY(%s)", (list(GRUPPEN),))
        cur.execute("DELETE FROM subjects WHERE id = ANY(%s)", (list(GRUPPEN),))
    conn.commit()
    conn.close()


def _sitzungen(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


def _ctx(db, sub, group_id=None):
    return ToolContext(db=db, user=SimpleNamespace(sub=sub), group_id=group_id, conversation_id=None)


async def _einheit_und_stunde(client, h, gruppe, titel="Zahnräder"):
    ue = (await client.post(f"/planning/groups/{gruppe}/units", headers=h,
                            json={"titel": titel, "farbe": 0})).json()["id"]
    stunde = (await client.post(f"/planning/units/{ue}/lessons", headers=h,
                                json={"titel": titel})).json()["id"]
    resp = await client.patch(f"/planning/lessons/{stunde}", headers=h, json={"phasen": [
        {"name": "Einstieg", "dauer_min": 10}, {"name": "Erarbeitung", "dauer_min": 25},
    ]})
    assert resp.status_code == 200, resp.text
    return ue, stunde


async def _rufe(async_engine, handler, args, sub, group_id=None):
    async with _sitzungen(async_engine)() as db:
        return await handler(args, _ctx(db, sub, group_id))


async def _phasennamen(client, h, stunde):
    return [p["name"] for p in (await client.get(f"/planning/lessons/{stunde}", headers=h)).json()["phasen"]]


async def _snapshots(async_engine, gruppe):
    async with _sitzungen(async_engine)() as db:
        return (await db.execute(
            sa.select(sa.func.count()).select_from(SlotPlanSnapshot).where(
                SlotPlanSnapshot.group_id == gruppe, SlotPlanSnapshot.reason == "assistant")
        )).scalar_one()


# ── Die eigene Stunde: ohne Gruppenbezug lesen und schreiben ─────────────────


@pytest.mark.asyncio
async def test_eigene_stunde_ohne_gruppenbezug(test_client, auth_headers, gruppen, async_engine):
    _, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE)

    gelesen = await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": stunde}, TEACHER1_PSEUDO)
    assert [p["name"] for p in gelesen["phasen"]] == ["Einstieg", "Erarbeitung"]

    vorher = await _snapshots(async_engine, EIGENE)
    aus = await _rufe(async_engine, _handle_update_lesson_phases, {"node_id": stunde, "phasen": [
        {"id": gelesen["phasen"][0]["id"], "name": "Einstieg", "dauer_min": 5},
        {"name": "Sicherung", "dauer_min": 10},
    ]}, TEACHER1_PSEUDO)
    assert aus.get("ok") is True, aus
    assert await _phasennamen(test_client, auth_headers, stunde) == ["Einstieg", "Sicherung"]
    # Rückgängig gehört der Gruppe der Stunde — die Konversation hat hier keine.
    assert await _snapshots(async_engine, EIGENE) == vorher + 1


# ── Wächter: eine fremde Kennung öffnet nichts ───────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("gruppe_der_konversation", [None, EIGENE, FREMDE])
async def test_fremde_stunde_weder_lesen_noch_schreiben(
    test_client, auth_headers, auth_headers_teacher2, gruppen, async_engine, gruppe_der_konversation,
):
    """Auch nicht aus einer Konversation, die in der fremden Gruppe steht."""
    _, fremd = await _einheit_und_stunde(test_client, auth_headers_teacher2, FREMDE)

    assert await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": fremd},
                       TEACHER1_PSEUDO, gruppe_der_konversation) == NICHT_GEFUNDEN
    assert await _rufe(async_engine, _handle_update_lesson_phases, {
        "node_id": fremd, "phasen": [{"name": "Übernommen", "dauer_min": 45}],
    }, TEACHER1_PSEUDO, gruppe_der_konversation) == NICHT_GEFUNDEN
    assert await _phasennamen(test_client, auth_headers_teacher2, fremd) == ["Einstieg", "Erarbeitung"]


@pytest.mark.asyncio
async def test_schuelerin_der_gruppe_kommt_nicht_an_die_stunde(test_client, auth_headers, gruppen, async_engine):
    """Mitglied der Gruppe heißt nicht Lehrkraft der Gruppe."""
    _, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE)

    assert await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": stunde},
                       STUDENT_PSEUDO, EIGENE) == NICHT_GEFUNDEN
    assert await _rufe(async_engine, _handle_update_lesson_phases, {
        "node_id": stunde, "phasen": [{"name": "Weg", "dauer_min": 45}],
    }, STUDENT_PSEUDO, EIGENE) == NICHT_GEFUNDEN
    assert await _phasennamen(test_client, auth_headers, stunde) == ["Einstieg", "Erarbeitung"]


@pytest.mark.asyncio
async def test_fremd_und_unbekannt_sind_nicht_zu_unterscheiden(
    test_client, auth_headers_teacher2, gruppen, async_engine,
):
    """Sonst verriete das Werkzeug, welche Kennungen es gibt."""
    _, fremd = await _einheit_und_stunde(test_client, auth_headers_teacher2, FREMDE)
    fremd_gelesen = await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": fremd}, TEACHER1_PSEUDO)
    unbekannt = await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": str(uuid4())}, TEACHER1_PSEUDO)
    assert fremd_gelesen == unbekannt == NICHT_GEFUNDEN


@pytest.mark.asyncio
async def test_ohne_mitgliedschaft_nur_lesen(test_client, auth_headers, gruppen, async_engine):
    """Der Archiv-Fall aus `zugang_zur_stunde`: Die Eigentümerin liest, ändert aber nicht."""
    _, stunde = await _einheit_und_stunde(test_client, auth_headers, ARCHIV)
    with gruppen.cursor() as cur:
        cur.execute("DELETE FROM group_memberships WHERE group_id = %s AND pseudonym = %s",
                    (ARCHIV, TEACHER1_PSEUDO))
    gruppen.commit()

    gelesen = await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": stunde}, TEACHER1_PSEUDO)
    assert gelesen.get("titel") == "Zahnräder", gelesen
    aus = await _rufe(async_engine, _handle_update_lesson_phases, {
        "node_id": stunde, "phasen": [{"name": "Neu", "dauer_min": 45}],
    }, TEACHER1_PSEUDO)
    assert aus == {"error": "Stunde nur lesbar: keine Lehrkraft der Gruppe"}

    async with _sitzungen(async_engine)() as db:
        nochmal = await _handle_get_lesson_detail({"node_id": stunde}, _ctx(db, TEACHER1_PSEUDO))
    assert [p["name"] for p in nochmal["phasen"]] == ["Einstieg", "Erarbeitung"]


# ── Die Einheit: dieselbe Regel ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_einheit_ohne_gruppenbezug_mit_den_slots_ihrer_gruppe(
    test_client, auth_headers, gruppen, async_engine,
):
    ue, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE, titel="Hebel")
    async with _sitzungen(async_engine)() as db:
        db.add(LessonSlot(id=uuid4(), group_id=EIGENE, date=date(2031, 3, 3), halbjahr=2,
                          periods=1, start_period=3, kategorie="unterricht", ue_node_id=UUID(ue)))
        await db.commit()

    aus = await _rufe(async_engine, _handle_get_unit_detail, {"unit_node_id": ue}, TEACHER1_PSEUDO)
    assert aus["titel"] == "Hebel", aus
    assert [s["date"] for s in aus["slots"]] == ["2031-03-03"]
    assert [s["id"] for s in aus["stunden"]] == [stunde]


@pytest.mark.asyncio
@pytest.mark.parametrize("gruppe_der_konversation", [None, EIGENE, FREMDE])
async def test_fremde_einheit_bleibt_zu(
    test_client, auth_headers_teacher2, gruppen, async_engine, gruppe_der_konversation,
):
    ue, _ = await _einheit_und_stunde(test_client, auth_headers_teacher2, FREMDE, titel="Geheim")
    aus = await _rufe(async_engine, _handle_get_unit_detail, {"unit_node_id": ue},
                      TEACHER1_PSEUDO, gruppe_der_konversation)
    assert aus == {"error": "UE nicht gefunden"}
