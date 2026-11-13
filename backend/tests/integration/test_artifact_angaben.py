"""Angaben eines Produkts ändern und Themen vorschlagen (0.41, Päckchen AN, Schritt 3).

`PATCH /artifacts/{id}`: Titel, Fach, Thema — jede Art, nur die Eigentümer:in.
`GET /artifacts/topics`: eigene Themen; Lehrkräfte dazu die Einheiten ihrer Gruppen (F8).
Erfordert TEST_DATABASE_URL.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg2
import pytest

from tests.integration.conftest import STUDENT_PSEUDO, TEACHER1_PSEUDO, TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio

FACH, ANDERES_FACH = 9611, 9612
GRUPPE, FREMDE_GRUPPE = 9611, 9612
T0 = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn(db_url, run_migrations):
    c = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with c.cursor() as cur:
        for fid, slug in ((FACH, "an3-chemie"), (ANDERES_FACH, "an3-physik")):
            cur.execute("INSERT INTO subjects (id, slug, name) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
                        (fid, slug, slug))
        for gid, slug in ((GRUPPE, "an3-9a"), (FREMDE_GRUPPE, "an3-9b")):
            cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) VALUES (%s, %s, %s, 'teaching_group', %s)"
                        " ON CONFLICT (id) DO NOTHING", (gid, slug, slug, FACH))
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft)"
                    " VALUES (%s, %s, 'teacher', 'manuell') ON CONFLICT DO NOTHING", (GRUPPE, TEACHER2_PSEUDO))
    c.commit()
    yield c
    c.rollback()
    with c.cursor() as cur:
        cur.execute("DELETE FROM artifacts WHERE title LIKE 'AN3 %%'")
        cur.execute("DELETE FROM context_nodes WHERE title LIKE 'AN3 %%'")
        cur.execute("DELETE FROM group_memberships WHERE group_id IN (%s, %s)", (GRUPPE, FREMDE_GRUPPE))
        cur.execute("DELETE FROM groups WHERE id IN (%s, %s)", (GRUPPE, FREMDE_GRUPPE))
        cur.execute("DELETE FROM subjects WHERE id IN (%s, %s)", (FACH, ANDERES_FACH))
    c.commit()
    c.close()


def _produkt(conn, owner, titel, *, kind="image", fach=None, thema=None, versatz_min=0):
    with conn.cursor() as cur:
        zeit = T0 + timedelta(minutes=versatz_min)
        cur.execute(
            "INSERT INTO artifacts (owner_pseudonym, kind, mime_type, byte_size, title, subject_id, topic,"
            " created_at, updated_at, expires_at) VALUES (%s, %s, 'image/png', 3, %s, %s, %s, %s, %s, %s)"
            " RETURNING id",
            (owner, kind, titel, fach, thema, zeit, zeit, zeit + timedelta(days=365)),
        )
        pid = cur.fetchone()[0]
    conn.commit()
    return str(pid)


def _einheit(conn, titel, gruppe):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO context_nodes (category, content_type, title, read_scope, read_scope_group_id,"
            " write_scope, write_scope_group_id, owner_pseudonym, status)"
            " VALUES ('artifact', 'unterrichtseinheit', %s, 'group', %s, 'group', %s, %s, 'active')",
            (titel, gruppe, gruppe, TEACHER2_PSEUDO),
        )
    conn.commit()


# ── PATCH ─────────────────────────────────────────────────────────────────────

async def test_angaben_aendern_auch_bei_einem_bild(test_client, auth_headers_teacher2, conn):
    pid = _produkt(conn, TEACHER2_PSEUDO, "AN3 Bild")

    resp = await test_client.patch(f"/artifacts/{pid}", headers=auth_headers_teacher2, json={
        "title": "  AN3 Fuchs im Schnee ", "subject_id": FACH, "topic": " Säuren und Basen ",
    })

    assert resp.status_code == 200, resp.text
    a = resp.json()
    assert (a["title"], a["subject_id"], a["topic"]) == ("AN3 Fuchs im Schnee", FACH, "Säuren und Basen")
    assert a["updated_at"] > T0.isoformat()


async def test_nur_gesendete_felder_aendern_sich(test_client, auth_headers_teacher2, conn):
    pid = _produkt(conn, TEACHER2_PSEUDO, "AN3 bleibt", fach=FACH, thema="Redox")

    resp = await test_client.patch(f"/artifacts/{pid}", headers=auth_headers_teacher2, json={"topic": None})

    assert resp.status_code == 200, resp.text
    assert (resp.json()["title"], resp.json()["subject_id"], resp.json()["topic"]) == ("AN3 bleibt", FACH, None)


async def test_fach_entfernen(test_client, auth_headers_teacher2, conn):
    pid = _produkt(conn, TEACHER2_PSEUDO, "AN3 ohne Fach", fach=FACH)
    resp = await test_client.patch(f"/artifacts/{pid}", headers=auth_headers_teacher2, json={"subject_id": None})
    assert resp.json()["subject_id"] is None


@pytest.mark.parametrize("nutzlast, status", [
    ({"title": "   "}, 422),
    ({"subject_id": 987654}, 422),
])
async def test_ungueltige_angaben(test_client, auth_headers_teacher2, conn, nutzlast, status):
    pid = _produkt(conn, TEACHER2_PSEUDO, "AN3 ungültig")
    resp = await test_client.patch(f"/artifacts/{pid}", headers=auth_headers_teacher2, json=nutzlast)
    assert resp.status_code == status


async def test_fremdes_produkt(test_client, auth_headers, conn):
    pid = _produkt(conn, TEACHER2_PSEUDO, "AN3 fremd")
    resp = await test_client.patch(f"/artifacts/{pid}", headers=auth_headers, json={"title": "AN3 gekapert"})
    assert resp.status_code == 403


async def test_unbekanntes_produkt(test_client, auth_headers_teacher2, conn):
    resp = await test_client.patch(f"/artifacts/{uuid4()}", headers=auth_headers_teacher2, json={"title": "x"})
    assert resp.status_code == 404


# ── Themen ────────────────────────────────────────────────────────────────────

async def test_eigene_themen_zuletzt_benutzte_zuerst(test_client, auth_headers_teacher2, conn):
    _produkt(conn, TEACHER2_PSEUDO, "AN3 a", fach=FACH, thema="Redox", versatz_min=0)
    _produkt(conn, TEACHER2_PSEUDO, "AN3 b", fach=FACH, thema="Säuren", versatz_min=5)
    _produkt(conn, TEACHER2_PSEUDO, "AN3 c", fach=ANDERES_FACH, thema="Optik", versatz_min=9)
    _produkt(conn, TEACHER1_PSEUDO, "AN3 d", fach=FACH, thema="Fremdes Thema")

    alle = (await test_client.get("/artifacts/topics", headers=auth_headers_teacher2)).json()
    im_fach = (await test_client.get(f"/artifacts/topics?subject_id={FACH}", headers=auth_headers_teacher2)).json()

    assert alle["eigene"][:3] == ["Optik", "Säuren", "Redox"]
    assert im_fach["eigene"] == ["Säuren", "Redox"]
    assert "Fremdes Thema" not in alle["eigene"]


async def test_lehrkraft_bekommt_die_einheiten_ihrer_gruppen(test_client, auth_headers_teacher2, conn):
    _einheit(conn, "AN3 Elektrochemie", GRUPPE)
    _einheit(conn, "AN3 Fremde Einheit", FREMDE_GRUPPE)
    _produkt(conn, TEACHER2_PSEUDO, "AN3 x", fach=FACH, thema="AN3 Doppelt")
    _einheit(conn, "AN3 Doppelt", GRUPPE)

    t = (await test_client.get(f"/artifacts/topics?subject_id={FACH}", headers=auth_headers_teacher2)).json()

    assert "AN3 Elektrochemie" in t["einheiten"]
    assert "AN3 Fremde Einheit" not in t["einheiten"]
    # Was schon eigenes Thema ist, steht nicht zweimal da.
    assert "AN3 Doppelt" in t["eigene"] and "AN3 Doppelt" not in t["einheiten"]


async def test_schuelerin_bekommt_keine_einheiten(test_client, auth_headers_student, conn):
    """F8: Die Titel der Einheiten sind Planung der Lehrkraft."""
    _einheit(conn, "AN3 Elektrochemie", GRUPPE)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft)"
                    " VALUES (%s, %s, 'student', 'manuell') ON CONFLICT DO NOTHING", (GRUPPE, STUDENT_PSEUDO))
    conn.commit()

    t = (await test_client.get(f"/artifacts/topics?subject_id={FACH}", headers=auth_headers_student)).json()

    assert t["einheiten"] == []


async def test_angaben_aendern_erneuert_die_frist(test_client, auth_headers_teacher2, conn):
    """0.41, Schritt 6: Wer ordnet, benutzt."""
    pid = _produkt(conn, TEACHER2_PSEUDO, "AN3 Frist")   # Frist: T0 + 365 Tage (Sept. 2027)
    with conn.cursor() as cur:
        cur.execute("UPDATE artifacts SET expires_at = now() + interval '2 days' WHERE id = %s", (pid,))
    conn.commit()

    resp = await test_client.patch(f"/artifacts/{pid}", headers=auth_headers_teacher2, json={"topic": "Redox"})

    assert resp.status_code == 200, resp.text
    with conn.cursor() as cur:
        cur.execute("SELECT expires_at > now() + interval '30 days' FROM artifacts WHERE id = %s", (pid,))
        assert cur.fetchone()[0] is True
