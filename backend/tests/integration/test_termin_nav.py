"""Stunden-Navigation nach Terminen der Gruppe in `GET /planning/lessons/{id}` (0.48, Päckchen N).

Die Regel selbst prüft `tests/unit/test_termin_nav.py`; hier, dass die Route die richtigen
Termine und Entwürfe einsammelt: nur die der Gruppe, Ausfall übersprungen, gelöschte Entwürfe
als „kein Entwurf“, keine Termin-Navigation ohne Termin.
"""
import uuid
from datetime import date

import psycopg2
import pytest

from tests.integration.conftest import TEACHER1_PSEUDO

GRUPPE = 990480
FREMD = 990481


@pytest.fixture(scope="module")
def conn(db_url, run_migrations):
    c = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield c
    c.close()


@pytest.fixture(autouse=True)
def bestand(conn):
    def raeumen():
        conn.rollback()
        with conn.cursor() as cur:
            for g in (GRUPPE, FREMD):
                cur.execute("DELETE FROM lesson_slots WHERE group_id = %s", (g,))
                cur.execute("DELETE FROM context_nodes WHERE write_scope_group_id = %s", (g,))
                cur.execute("DELETE FROM group_memberships WHERE group_id = %s", (g,))
                cur.execute("DELETE FROM groups WHERE id = %s", (g,))
        conn.commit()

    raeumen()
    with conn.cursor() as cur:
        for g, name in ((GRUPPE, "termin-nav"), (FREMD, "termin-nav-fremd")):
            cur.execute("INSERT INTO groups (id, name, slug, type) VALUES (%s, %s, %s, 'teaching_group')",
                        (g, name, name))
            cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                        "VALUES (%s, %s, 'teacher', 'eigen')", (g, TEACHER1_PSEUDO))
    conn.commit()
    yield
    raeumen()


def _stunde(conn, titel, gruppe=GRUPPE, status="active"):
    kid = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO context_nodes (id, category, content_type, title, owner_pseudonym, status, "
            "read_scope, write_scope, read_scope_group_id, write_scope_group_id) "
            "VALUES (%s, 'artifact', 'unterrichtsstunde', %s, %s, %s, 'group', 'group', %s, %s)",
            (kid, titel, TEACHER1_PSEUDO, status, gruppe, gruppe),
        )
    conn.commit()
    return kid


def _termin(conn, tag, stunde=1, kategorie="unterricht", entwurf=None, gruppe=GRUPPE):
    sid = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO lesson_slots (id, group_id, date, start_period, halbjahr, kategorie, "
            "stunde_node_id) VALUES (%s, %s, %s, %s, 1, %s, %s)",
            (sid, gruppe, date(2026, 11, tag), stunde, kategorie, entwurf),
        )
    conn.commit()
    return sid


async def _termine(test_client, auth_headers, stunde_id):
    r = await test_client.get(f"/planning/lessons/{stunde_id}", headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["termine"]


@pytest.mark.asyncio
async def test_naechster_termin_ueberspringt_ausfall_und_bietet_leeren_termin_an(
        conn, test_client, auth_headers):
    erste = _stunde(conn, "Erste")
    _termin(conn, 16, entwurf=erste)
    _termin(conn, 17, kategorie="ausfall")
    leer = _termin(conn, 18)
    _termin(conn, 18, stunde=1, gruppe=FREMD)  # andere Gruppe zählt nicht

    t = await _termine(test_client, auth_headers, erste)
    assert t["vorher"] is None
    assert t["nachher"]["slot_id"] == leer
    assert t["nachher"]["stunde_node_id"] is None


@pytest.mark.asyncio
async def test_voriger_termin_mit_entwurf_und_geloeschter_entwurf_gilt_als_leer(
        conn, test_client, auth_headers):
    erste, zweite = _stunde(conn, "Erste"), _stunde(conn, "Zweite")
    weg = _stunde(conn, "Gelöscht", status="deleted")
    _termin(conn, 16, entwurf=erste)
    _termin(conn, 17, entwurf=zweite)
    mit_geloeschtem = _termin(conn, 18, entwurf=weg)

    t = await _termine(test_client, auth_headers, zweite)
    assert t["vorher"]["stunde_node_id"] == erste
    assert t["nachher"]["slot_id"] == mit_geloeschtem
    assert t["nachher"]["stunde_node_id"] is None


@pytest.mark.asyncio
async def test_stunde_ohne_termin_hat_keine_termin_navigation(conn, test_client, auth_headers):
    lose = _stunde(conn, "Ohne Termin")
    _termin(conn, 16)
    assert await _termine(test_client, auth_headers, lose) is None
