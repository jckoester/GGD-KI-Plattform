"""Die Liste der Werkstatt: Suche, Filter, Sortierung, Blättern (0.41, Päckchen AN, Schritt 4).

Gegen echtes Postgres über `GET /artifacts`. Erfordert TEST_DATABASE_URL.
"""
import json
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

from tests.integration.conftest import TEACHER1_PSEUDO, TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio

ICH = TEACHER2_PSEUDO
FACH, ANDERES = 9621, 9622
JETZT = datetime.now(timezone.utc)


@pytest.fixture
def conn(db_url, run_migrations):
    c = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with c.cursor() as cur:
        cur.execute("DELETE FROM artifacts WHERE owner_pseudonym = ANY(%s)", ([ICH, TEACHER1_PSEUDO],))
        for fid in (FACH, ANDERES):
            cur.execute("INSERT INTO subjects (id, slug, name) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
                        (fid, f"an4-{fid}", f"AN4 {fid}"))
    c.commit()
    yield c
    c.rollback()
    with c.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE title LIKE 'AN4 %%'")
        cur.execute("DELETE FROM artifacts WHERE owner_pseudonym = ANY(%s)", ([ICH, TEACHER1_PSEUDO],))
        cur.execute("DELETE FROM subjects WHERE id IN (%s, %s)", (FACH, ANDERES))
    c.commit()
    c.close()


def _p(conn, titel, *, kind="document", owner=ICH, fach=None, thema=None, quelle=None,
       erstellt=0, bearbeitet=0, frist_tage=300):
    """Produkt mit Zeitpunkten relativ zu jetzt (Minuten in die Vergangenheit)."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO artifacts (owner_pseudonym, kind, mime_type, byte_size, title, source, subject_id,"
            " topic, created_at, updated_at, expires_at) VALUES (%s, %s, 'text/markdown', 10, %s, %s, %s, %s,"
            " %s, %s, %s) RETURNING id",
            (owner, kind, titel, quelle, fach, thema, JETZT - timedelta(minutes=erstellt),
             JETZT - timedelta(minutes=bearbeitet), JETZT + timedelta(days=frist_tage)),
        )
        pid = cur.fetchone()[0]
    conn.commit()
    return str(pid)


async def _liste(client, headers, **params):
    resp = await client.get("/artifacts", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _titel(antwort):
    return [i["title"] for i in antwort["items"]]


async def test_suche_in_titel_und_inhalt(test_client, auth_headers_teacher2, conn):
    _p(conn, "Säuren und Basen")
    _p(conn, "Arbeitsblatt 3", quelle="# Neutralisation von Säuren")
    _p(conn, "Optik")

    assert sorted(_titel(await _liste(test_client, auth_headers_teacher2, q="säure"))) == \
        ["Arbeitsblatt 3", "Säuren und Basen"]


async def test_suche_nimmt_prozent_woertlich(test_client, auth_headers_teacher2, conn):
    _p(conn, "Zinsen 5 % pro Jahr")
    _p(conn, "Anderes")
    assert _titel(await _liste(test_client, auth_headers_teacher2, q="%")) == ["Zinsen 5 % pro Jahr"]


async def test_art_fasst_zusammen(test_client, auth_headers_teacher2, conn):
    _p(conn, "Plot", kind="plot")
    _p(conn, "Mermaid", kind="mermaid")
    _p(conn, "Bild", kind="image")
    _p(conn, "Export", kind="export_pdf")

    assert sorted(_titel(await _liste(test_client, auth_headers_teacher2, art="diagram"))) == ["Mermaid", "Plot"]
    assert _titel(await _liste(test_client, auth_headers_teacher2, art="file")) == ["Export"]
    resp = await test_client.get("/artifacts", headers=auth_headers_teacher2, params={"art": "zeitreise"})
    assert resp.status_code == 422


async def test_fach_thema_und_facetten(test_client, auth_headers_teacher2, conn):
    _p(conn, "A", fach=FACH, thema="Redox")
    _p(conn, "B", fach=FACH, thema="Säuren")
    _p(conn, "C", fach=ANDERES, thema="Optik")
    _p(conn, "fremd", owner=TEACHER1_PSEUDO, fach=FACH, thema="Fremdes Thema")

    gefiltert = await _liste(test_client, auth_headers_teacher2, subject_id=FACH, topic="Redox")
    assert _titel(gefiltert) == ["A"]
    # Die Auswahl der Filter kommt aus dem ganzen eigenen Bestand.
    assert gefiltert["faecher"] == sorted([FACH, ANDERES])
    assert gefiltert["themen"] == ["Optik", "Redox", "Säuren"]


async def test_bald_ablaufend(test_client, auth_headers_teacher2, conn):
    _p(conn, "bald", frist_tage=10)
    _p(conn, "später", frist_tage=200)
    assert _titel(await _liste(test_client, auth_headers_teacher2, bald_ablaufend="true")) == ["bald"]


async def test_als_baustein_uebernommen(test_client, auth_headers_teacher2, conn):
    uebernommen = _p(conn, "übernommen")
    _p(conn, "nicht übernommen")
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO context_nodes (category, content_type, title, read_scope, write_scope, owner_pseudonym,"
            " status, metadata) VALUES ('artifact', 'arbeitsblatt', 'AN4 Baustein', 'private', 'private', %s,"
            " 'active', %s::jsonb)",
            (ICH, json.dumps({"source_artifact_id": uebernommen})),
        )
    conn.commit()

    assert _titel(await _liste(test_client, auth_headers_teacher2, als_baustein="true")) == ["übernommen"]


async def test_sortierungen(test_client, auth_headers_teacher2, conn):
    _p(conn, "b alt bearbeitet", erstellt=10, bearbeitet=9)
    _p(conn, "a frisch bearbeitet", erstellt=30, bearbeitet=1)
    _p(conn, "C neu angelegt", erstellt=2, bearbeitet=2)

    assert _titel(await _liste(test_client, auth_headers_teacher2, sort="updated")) == \
        ["a frisch bearbeitet", "C neu angelegt", "b alt bearbeitet"]
    assert _titel(await _liste(test_client, auth_headers_teacher2, sort="created")) == \
        ["C neu angelegt", "b alt bearbeitet", "a frisch bearbeitet"]
    # Titel ohne Rücksicht auf Groß- und Kleinschreibung.
    assert _titel(await _liste(test_client, auth_headers_teacher2, sort="title")) == \
        ["a frisch bearbeitet", "b alt bearbeitet", "C neu angelegt"]


async def test_blaettern_und_gesamtzahl(test_client, auth_headers_teacher2, conn):
    for i in range(5):
        _p(conn, f"Nr {i}", erstellt=i)

    erste = await _liste(test_client, auth_headers_teacher2, limit=2, sort="created")
    zweite = await _liste(test_client, auth_headers_teacher2, limit=2, offset=2, sort="created")

    assert (erste["total"], _titel(erste)) == (5, ["Nr 0", "Nr 1"])
    assert _titel(zweite) == ["Nr 2", "Nr 3"]


async def test_belegung_bleibt_unverfiltert(test_client, auth_headers_teacher2, conn):
    _p(conn, "A", fach=FACH)
    _p(conn, "B")
    antwort = await _liste(test_client, auth_headers_teacher2, subject_id=FACH)
    assert antwort["total"] == 1
    assert antwort["used_bytes"] == 20


# ── Exporte am Dokument (Schritt 5, F5) ──────────────────────────────────────

def _export(conn, dokument_id, titel, kind="export_pdf"):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO artifacts (owner_pseudonym, kind, mime_type, byte_size, title, derived_from, expires_at)"
            " VALUES (%s, %s, 'application/pdf', 5, %s, %s, %s) RETURNING id",
            (ICH, kind, titel, dokument_id, JETZT + timedelta(days=300)),
        )
        eid = cur.fetchone()[0]
    conn.commit()
    return str(eid)


async def test_exporte_haengen_am_dokument(test_client, auth_headers_teacher2, conn):
    dok = _p(conn, "Arbeitsblatt")
    export = _export(conn, dok, "Arbeitsblatt")
    _p(conn, "alter Export ohne Verweis", kind="export_pdf")

    antwort = await _liste(test_client, auth_headers_teacher2, sort="title")

    assert _titel(antwort) == ["alter Export ohne Verweis", "Arbeitsblatt"]
    assert antwort["total"] == 2
    karte = next(i for i in antwort["items"] if i["id"] == dok)
    assert [e["id"] for e in karte["exporte"]] == [export]
    # Auch der Filter „Dateien“ zeigt nur, was für sich steht.
    assert _titel(await _liste(test_client, auth_headers_teacher2, art="file")) == ["alter Export ohne Verweis"]


async def test_dokument_loeschen_nimmt_die_exporte_mit(test_client, auth_headers_teacher2, conn):
    dok = _p(conn, "Arbeitsblatt")
    _export(conn, dok, "Arbeitsblatt")
    _export(conn, dok, "Arbeitsblatt", kind="export_docx")

    resp = await test_client.delete(f"/artifacts/{dok}", headers=auth_headers_teacher2)

    assert resp.status_code == 200, resp.text
    assert resp.json()["mitgeloescht"] == 2
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM artifacts WHERE derived_from = %s", (dok,))
        assert cur.fetchone()[0] == 0
