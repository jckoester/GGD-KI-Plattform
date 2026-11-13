"""Einheitenansicht des Planers (0.42.3, Schritt 1): `GET /planning/groups/{id}/inhalt`.

Anlass: Eine kopierte Stunde hat keinen Termin und war im Planer nicht zu finden. Die Ansicht
zeigt die Einheiten einer Gruppe mit allen Stunden — mit Termin oder ohne.

Gruppen von teacher1 (`auth_headers`): ``EIGENE`` (teacher2 unterrichtet mit), ``ZIEL`` (für eine
Kopie); ``FREMD`` gehört nur teacher2.
"""
import json
import time
import uuid
from datetime import date

import psycopg2
import pytest

from app.auth.vorschau import Vorschau
from tests.integration.conftest import TEACHER1_PSEUDO, TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio

FACH = 9450
EIGENE, ZIEL, FREMD = 9451, 9452, 9453
GRUPPEN = [EIGENE, ZIEL, FREMD]


@pytest.fixture
def conn(db_url, run_migrations):
    c = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))

    def aufraeumen():
        with c.cursor() as cur:
            cur.execute("DELETE FROM context_nodes WHERE write_scope_group_id = ANY(%s) OR subject_id = %s",
                        (GRUPPEN, FACH))
            cur.execute("DELETE FROM groups WHERE id = ANY(%s)", (GRUPPEN,))
            cur.execute("DELETE FROM subjects WHERE id = %s", (FACH,))
        c.commit()

    aufraeumen()
    with c.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, icon, color) VALUES (%s, 'ao-ansicht', 'Ansicht', "
                    "'Atom', 'bl')", (FACH,))
        for gid in GRUPPEN:
            cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                        "VALUES (%s, %s, %s, 'teaching_group', %s)", (gid, f"AO {gid}", f"ao-{gid}", FACH))
        for gid, wer in ((EIGENE, TEACHER1_PSEUDO), (EIGENE, TEACHER2_PSEUDO), (ZIEL, TEACHER1_PSEUDO),
                         (FREMD, TEACHER2_PSEUDO)):
            cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                        "VALUES (%s, %s, 'teacher', 'eigen')", (gid, wer))
    c.commit()
    yield c
    c.rollback()
    aufraeumen()
    c.close()


def _knoten(conn, typ, titel, gruppe, *, owner=TEACHER1_PSEUDO, status="active", meta=None):
    nid = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO context_nodes (id, category, content_type, title, owner_pseudonym, read_scope, write_scope,"
            " read_scope_group_id, write_scope_group_id, subject_id, status, metadata)"
            " VALUES (%s, 'artifact', %s, %s, %s, 'group_teachers', 'group_teachers', %s, %s, %s, %s, %s::jsonb)",
            (nid, typ, titel, owner, gruppe, gruppe, FACH, status, json.dumps(meta or {})),
        )
    conn.commit()
    return nid


def _kante(conn, von, nach, relation):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO context_edges (from_node_id, to_node_id, relation) VALUES (%s, %s, %s)",
                    (von, nach, relation))
    conn.commit()


def _einheit(conn, gruppe, titel="Säuren"):
    return _knoten(conn, "unterrichtseinheit", titel, gruppe)


def _stunde(conn, gruppe, einheit, titel, *, owner=TEACHER1_PSEUDO, status="active", nach=None):
    sid = _knoten(conn, "unterrichtsstunde", titel, gruppe, owner=owner, status=status,
                  meta={"phasen": [{"id": "p1", "name": "Einstieg", "dauer_min": 10, "prio": "kern"}]})
    _kante(conn, sid, einheit, "part_of")
    if nach:
        _kante(conn, sid, nach, "follows")
    return sid


def _termin(conn, gruppe, tag, stunde):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO lesson_slots (group_id, date, halbjahr, stunde_node_id) "
                    "VALUES (%s, %s, 1, %s) RETURNING id", (gruppe, tag, stunde))
        sid = cur.fetchone()[0]
    conn.commit()
    return str(sid)


async def _inhalt(client, headers, gruppe=EIGENE):
    return await client.get(f"/planning/groups/{gruppe}/inhalt", headers=headers)


def _stunden(daten):
    return {s["titel"]: s for e in daten["einheiten"] for s in e["stunden"]}


async def test_stunde_ohne_termin_erscheint(test_client, auth_headers, conn):
    einheit = _einheit(conn, EIGENE)
    eins = _stunde(conn, EIGENE, einheit, "Eins")
    _stunde(conn, EIGENE, einheit, "Zwei", nach=eins)
    slot = _termin(conn, EIGENE, date(2026, 9, 14), eins)

    resp = await _inhalt(test_client, auth_headers)

    assert resp.status_code == 200
    daten = resp.json()
    assert [e["titel"] for e in daten["einheiten"]] == ["Säuren"]
    assert [s["titel"] for s in daten["einheiten"][0]["stunden"]] == ["Eins", "Zwei"]
    stunden = _stunden(daten)
    assert stunden["Eins"]["slot_id"] == slot and stunden["Eins"]["datum"] == "2026-09-14"
    assert stunden["Zwei"]["slot_id"] is None and stunden["Zwei"]["datum"] is None


async def test_kopie_erscheint_ohne_termin(test_client, auth_headers, conn):
    """Der Anlass: Die Kopie ist in der Zielgruppe zu finden, obwohl kein Termin auf sie zeigt."""
    quelle = _stunde(conn, EIGENE, _einheit(conn, EIGENE), "Vorlage")
    kopie = await test_client.post(f"/planning/lessons/{quelle}/copy", headers=auth_headers,
                                   json={"gruppe_id": ZIEL, "neue_einheit": "Kopiert"})
    assert kopie.status_code == 201, kopie.text

    daten = (await _inhalt(test_client, auth_headers, ZIEL)).json()

    assert [e["titel"] for e in daten["einheiten"]] == ["Kopiert"]
    (stunde,) = daten["einheiten"][0]["stunden"]
    assert stunde["id"] == kopie.json()["id"] and stunde["slot_id"] is None


async def test_mitlehrkraft_und_ohne_einheit(test_client, auth_headers, conn):
    """Mitglieder sehen alle Stunden der Gruppe, auch die der Kollegin; lose Stunden extra."""
    einheit = _einheit(conn, EIGENE)
    _stunde(conn, EIGENE, einheit, "Von teacher2", owner=TEACHER2_PSEUDO)
    _knoten(conn, "unterrichtsstunde", "Lose", EIGENE)

    daten = (await _inhalt(test_client, auth_headers)).json()

    assert "Von teacher2" in _stunden(daten)
    assert [s["titel"] for s in daten["ohne_einheit"]] == ["Lose"]


async def test_nur_aktives(test_client, auth_headers, conn):
    """Wie die Jahresübersicht: Vom Lebenszyklus Archiviertes gehört ins Archiv, nicht hierher."""
    einheit = _einheit(conn, EIGENE)
    _stunde(conn, EIGENE, einheit, "Aktiv")
    _stunde(conn, EIGENE, einheit, "Abgelaufen", status="archived")
    alt = _knoten(conn, "unterrichtseinheit", "Alte Einheit", EIGENE, status="archived")
    _stunde(conn, EIGENE, alt, "In alter Einheit", status="archived")

    daten = (await _inhalt(test_client, auth_headers)).json()

    assert [e["titel"] for e in daten["einheiten"]] == ["Säuren"]
    assert set(_stunden(daten)) == {"Aktiv"}
    assert daten["ohne_einheit"] == []


async def test_fremde_gruppe_und_vorschau(test_client, auth_headers, jwt_service, conn):
    _stunde(conn, FREMD, _einheit(conn, FREMD), "Fremd", owner=TEACHER2_PSEUDO)
    assert (await _inhalt(test_client, auth_headers, FREMD)).status_code == 403
    assert (await _inhalt(test_client, auth_headers, 9459)).status_code == 404

    jetzt = int(time.time())
    token, _ = jwt_service.issue(
        pseudonym=TEACHER1_PSEUDO, roles=["student"], grade="8",
        preview=Vorschau(echte_rollen=["teacher"], beginn=jetzt, sitzung_ablauf=jetzt + 3600),
        exp=jetzt + 3600,
    )
    assert (await _inhalt(test_client, {"Cookie": f"session={token}"})).status_code == 403


# ── Einplanen (Schritt 3): der Weg des Dialogs über `PATCH /planning/slots/{id}` ─────


def _leerer_termin(conn, gruppe, tag, *, einheit=None, thema=None):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO lesson_slots (group_id, date, halbjahr, ue_node_id, thema) "
                    "VALUES (%s, %s, 1, %s, %s) RETURNING id, updated_at", (gruppe, tag, einheit, thema))
        sid, stand = cur.fetchone()
    conn.commit()
    return str(sid), stand.isoformat()


def _einheit_der_stunde(conn, stunde):
    return [str(z[0]) for z in _lies(conn, "SELECT to_node_id FROM context_edges WHERE from_node_id = %s "
                                           "AND relation = 'part_of'", stunde)]


def _lies(conn, sql, *args):
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


async def test_einplanen_auf_leeren_termin(test_client, auth_headers, conn):
    """Wie der Dialog: Einheit und Titel als Thema mitgeben — die Stunde bleibt in ihrer Einheit."""
    einheit = _einheit(conn, EIGENE)
    stunde = _stunde(conn, EIGENE, einheit, "Kopierte Stunde")
    slot, stand = _leerer_termin(conn, EIGENE, date(2026, 9, 21))

    resp = await test_client.patch(f"/planning/slots/{slot}", headers=auth_headers, json={
        "stunde_node_id": stunde, "ue_node_id": einheit, "thema": "Kopierte Stunde",
        "expected_updated_at": stand,
    })

    assert resp.status_code == 200, resp.text
    assert _einheit_der_stunde(conn, stunde) == [einheit]
    daten = (await _inhalt(test_client, auth_headers)).json()
    assert _stunden(daten)["Kopierte Stunde"]["slot_id"] == slot


async def test_einplanen_ohne_einheit_am_termin_loeste_die_stunde(test_client, auth_headers, conn):
    """Warum der Dialog die Einheit mitschickt: Ohne sie ordnet der Server die Stunde dem
    Termin zu — und der hat keine Einheit."""
    einheit = _einheit(conn, EIGENE)
    stunde = _stunde(conn, EIGENE, einheit, "Lose danach")
    slot, _ = _leerer_termin(conn, EIGENE, date(2026, 9, 22))

    resp = await test_client.patch(f"/planning/slots/{slot}", headers=auth_headers,
                                   json={"stunde_node_id": stunde})

    assert resp.status_code == 200
    assert _einheit_der_stunde(conn, stunde) == []


async def test_einplanen_auf_termin_der_einheit_behaelt_thema(test_client, auth_headers, conn):
    einheit = _einheit(conn, EIGENE)
    stunde = _stunde(conn, EIGENE, einheit, "Zweite")
    slot, stand = _leerer_termin(conn, EIGENE, date(2026, 9, 23), einheit=einheit, thema="Getriebe")

    resp = await test_client.patch(f"/planning/slots/{slot}", headers=auth_headers,
                                   json={"stunde_node_id": stunde, "expected_updated_at": stand})

    assert resp.status_code == 200
    assert resp.json()["thema"] == "Getriebe"
    assert _einheit_der_stunde(conn, stunde) == [einheit]


async def test_einplanen_veralteter_stand_und_doppelt(test_client, auth_headers, conn):
    einheit = _einheit(conn, EIGENE)
    stunde = _stunde(conn, EIGENE, einheit, "Umkämpft")
    slot, stand = _leerer_termin(conn, EIGENE, date(2026, 9, 24))
    with conn.cursor() as cur:
        cur.execute("UPDATE lesson_slots SET thema = 'inzwischen belegt', updated_at = now() WHERE id = %s", (slot,))
    conn.commit()

    veraltet = await test_client.patch(f"/planning/slots/{slot}", headers=auth_headers,
                                       json={"stunde_node_id": stunde, "expected_updated_at": stand})
    assert veraltet.status_code == 409
    assert veraltet.json()["detail"]["grund"] == "veraltet"

    zweiter, _ = _leerer_termin(conn, EIGENE, date(2026, 9, 25))
    _termin(conn, EIGENE, date(2026, 9, 28), stunde)
    doppelt = await test_client.patch(f"/planning/slots/{zweiter}", headers=auth_headers,
                                      json={"stunde_node_id": stunde, "ue_node_id": einheit})
    assert doppelt.status_code == 409


# ── Stunde löschen (0.42.4; Plan F1–F3) ──────────────────────────────────────


async def _loesche(client, headers, stunde):
    return await client.delete(f"/planning/lessons/{stunde}", headers=headers)


def _gibt_es(conn, nid):
    return bool(_lies(conn, "SELECT 1 FROM context_nodes WHERE id = %s", nid))


async def test_loeschen_mit_termin_und_reihenfolge(test_client, auth_headers, conn):
    einheit = _einheit(conn, EIGENE)
    eins = _stunde(conn, EIGENE, einheit, "Eins")
    zwei = _stunde(conn, EIGENE, einheit, "Zwei", nach=eins)
    drei = _stunde(conn, EIGENE, einheit, "Drei", nach=zwei)
    slot = _termin(conn, EIGENE, date(2026, 9, 21), zwei)
    with conn.cursor() as cur:
        cur.execute("UPDATE lesson_slots SET ue_node_id = %s, thema = 'Getriebe' WHERE id = %s", (einheit, slot))
    conn.commit()

    resp = await _loesche(test_client, auth_headers, zwei)

    assert resp.status_code == 204, resp.text
    assert not _gibt_es(conn, zwei)
    # Der Termin bleibt mit Thema und Einheit, nur ohne Entwurf.
    assert _lies(conn, "SELECT stunde_node_id, ue_node_id::text, thema FROM lesson_slots WHERE id = %s", slot) \
        == [(None, einheit, "Getriebe")]
    # Die Reihenfolge schließt sich.
    daten = (await _inhalt(test_client, auth_headers)).json()
    assert [s["titel"] for s in daten["einheiten"][0]["stunden"]] == ["Eins", "Drei"]
    assert _lies(conn, "SELECT to_node_id::text FROM context_edges WHERE from_node_id = %s "
                       "AND relation = 'follows'", drei) == [(eins,)]


async def test_loeschen_nur_eigentuemerin(test_client, auth_headers_teacher2, conn):
    """F1: Die Mitlehrkraft darf die Stunde ändern, aber nicht löschen."""
    stunde = _stunde(conn, EIGENE, _einheit(conn, EIGENE), "Von teacher1")

    resp = await _loesche(test_client, auth_headers_teacher2, stunde)

    assert resp.status_code == 403
    assert "angelegt" in resp.json()["detail"]
    assert _gibt_es(conn, stunde)


async def test_nachbereitete_stunde_bleibt(test_client, auth_headers, conn):
    """F2: Eine nachbereitete Stunde hält fest, was unterrichtet wurde."""
    stunde = _stunde(conn, EIGENE, _einheit(conn, EIGENE), "Gehalten")
    slot = _termin(conn, EIGENE, date(2026, 9, 14), stunde)
    with conn.cursor() as cur:
        cur.execute("UPDATE lesson_slots SET nachbereitet_at = now() WHERE id = %s", (slot,))
    conn.commit()

    resp = await _loesche(test_client, auth_headers, stunde)

    assert resp.status_code == 409
    assert _gibt_es(conn, stunde)


async def test_archiviert_und_fremd_und_unbekannt(test_client, auth_headers, conn):
    archiviert = _stunde(conn, EIGENE, _einheit(conn, EIGENE), "Abgelaufen", status="archived")
    assert (await _loesche(test_client, auth_headers, archiviert)).status_code == 403
    fremd = _stunde(conn, FREMD, _einheit(conn, FREMD), "Fremd", owner=TEACHER2_PSEUDO)
    assert (await _loesche(test_client, auth_headers, fremd)).status_code == 403
    assert (await _loesche(test_client, auth_headers, uuid.uuid4())).status_code == 404
    einheit = _einheit(conn, EIGENE)
    assert (await _loesche(test_client, auth_headers, einheit)).status_code == 404


async def _snapshot_mit(test_client, auth_headers, conn, slot):
    """Ein Snapshot, der den jetzigen Stand des Termins festhält (PATCH legt ihn vorher an)."""
    resp = await test_client.patch(f"/planning/slots/{slot}", headers=auth_headers, json={"thema": "danach"})
    assert resp.status_code == 200, resp.text
    snaps = (await test_client.get(f"/planning/groups/{EIGENE}/snapshots", headers=auth_headers)).json()
    return snaps[0]["id"]


async def test_wiederherstellen_nach_loeschen_der_stunde(test_client, auth_headers, conn):
    einheit = _einheit(conn, EIGENE)
    stunde = _stunde(conn, EIGENE, einheit, "Später gelöscht")
    slot = _termin(conn, EIGENE, date(2026, 9, 29), stunde)
    snap = await _snapshot_mit(test_client, auth_headers, conn, slot)
    assert (await _loesche(test_client, auth_headers, stunde)).status_code == 204

    resp = await test_client.post(f"/planning/snapshots/{snap}/restore", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    assert _lies(conn, "SELECT stunde_node_id FROM lesson_slots WHERE id = %s", slot) == [(None,)]


async def test_wiederherstellen_nach_loeschen_der_einheit(test_client, auth_headers, conn):
    """Dieselbe Lücke gab es schon beim Löschen einer Einheit."""
    einheit = _einheit(conn, EIGENE)
    slot, _ = _leerer_termin(conn, EIGENE, date(2026, 9, 30), einheit=einheit, thema="mit Einheit")
    snap = await _snapshot_mit(test_client, auth_headers, conn, slot)
    assert (await test_client.delete(f"/planning/groups/{EIGENE}/units/{einheit}",
                                     headers=auth_headers)).status_code == 204

    resp = await test_client.post(f"/planning/snapshots/{snap}/restore", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    assert _lies(conn, "SELECT ue_node_id, thema FROM lesson_slots WHERE id = %s", slot) == [(None, "mit Einheit")]


async def test_oberflaeche_erfaehrt_ob_loeschen_geht(test_client, auth_headers, auth_headers_teacher2, conn):
    einheit = _einheit(conn, EIGENE)
    eigene = _stunde(conn, EIGENE, einheit, "Eigene")
    gehalten = _stunde(conn, EIGENE, einheit, "Gehalten")
    slot = _termin(conn, EIGENE, date(2026, 9, 14), gehalten)
    with conn.cursor() as cur:
        cur.execute("UPDATE lesson_slots SET nachbereitet_at = now() WHERE id = %s", (slot,))
    conn.commit()

    async def darf(headers, stunde):
        return (await test_client.get(f"/planning/lessons/{stunde}", headers=headers)).json()["darf_loeschen"]

    assert await darf(auth_headers, eigene) is True
    assert await darf(auth_headers, gehalten) is False
    assert await darf(auth_headers_teacher2, eigene) is False
    stunden = _stunden((await _inhalt(test_client, auth_headers_teacher2)).json())
    assert stunden["Eigene"]["eigen"] is False
    assert _stunden((await _inhalt(test_client, auth_headers)).json())["Eigene"]["eigen"] is True
