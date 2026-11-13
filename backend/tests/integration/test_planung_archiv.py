"""Archiv der Planung (0.42, Päckchen AO, Schritt 1; Plan F2, F3, F11, F12, S3).

Gegen echtes Postgres. Fünf Gruppen von teacher1 (`auth_headers`):

* ``AKTUELL`` — Mitglied, Gruppe aktuell (ohne Quellklasse) → im Menü, nicht im Archiv.
* ``FRUEHER`` — Mitglied, Gruppe mit Klasse aus dem Vorjahr ohne Beleg → Archiv, Zugang
  `mitglied`: alles der Gruppe, auch die Stunde von teacher2.
* ``WEG`` — keine Mitgliedschaft mehr, eigene Einheit und Stunden → Archiv, Zugang `eigentum`:
  nur Eigenes; teacher2 ist dort Lehrkraft und hat eigene Planung.
* ``FREMD`` — nur teacher2 → nicht im Archiv, 404.
* ``KLASSE`` — Klassenverband als Quellklasse für ``FRUEHER``.

Die Planungsknoten entstehen per SQL mit `metadata.schuljahr` aus dem Vorjahr — über die
Schnittstelle bekämen sie das laufende Jahr und machten ``FRUEHER`` wieder aktuell.
"""
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

from app.auth.vorschau import Vorschau
from app.planning.calendar import load_school_year
from tests.integration.conftest import TEACHER1_PSEUDO, TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio

FACH = 9420
AKTUELL, FRUEHER, WEG, FREMD, KLASSE = 9421, 9422, 9423, 9424, 9425
GRUPPEN = [AKTUELL, FRUEHER, WEG, FREMD, KLASSE]
JAHR = load_school_year()
VORJAHR = "2000/01"
VOR_EINEM_JAHR = datetime.combine(JAHR.beginn, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=200)


@pytest.fixture
def conn(db_url, run_migrations):
    c = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))

    def aufraeumen():
        with c.cursor() as cur:
            cur.execute("DELETE FROM context_nodes WHERE write_scope_group_id = ANY(%s)", (GRUPPEN,))
            cur.execute("DELETE FROM groups WHERE id = ANY(%s)", (GRUPPEN,))
            cur.execute("DELETE FROM subjects WHERE id = %s", (FACH,))
        c.commit()

    aufraeumen()
    with c.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, icon, color) VALUES (%s, 'ao-archiv', 'AO Archiv', "
                    "'Atom', 'bl')", (FACH,))
        for gid, typ in ((AKTUELL, "teaching_group"), (FRUEHER, "teaching_group"), (WEG, "teaching_group"),
                         (FREMD, "teaching_group"), (KLASSE, "school_class")):
            cur.execute("INSERT INTO groups (id, name, slug, type, subject_id, created_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (gid, f"AO {gid}", f"ao-{gid}", typ, FACH if typ == "teaching_group" else None,
                         VOR_EINEM_JAHR))
        cur.execute("INSERT INTO group_source_classes (group_id, class_group_id) VALUES (%s, %s)",
                    (FRUEHER, KLASSE))
        for gid, wer in ((AKTUELL, TEACHER1_PSEUDO), (FRUEHER, TEACHER1_PSEUDO), (WEG, TEACHER2_PSEUDO),
                         (FREMD, TEACHER2_PSEUDO)):
            cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                        "VALUES (%s, %s, 'teacher', 'eigen')", (gid, wer))
    c.commit()
    yield c
    c.rollback()
    aufraeumen()
    c.close()


def _knoten(conn, typ, gruppe, titel, *, owner=TEACHER1_PSEUDO, status="active", meta=None, minuten=0):
    nid = uuid.uuid4()
    metadata = dict(meta or {})
    if typ == "unterrichtseinheit":
        metadata.setdefault("schuljahr", VORJAHR)
    if typ == "unterrichtsstunde":
        metadata.setdefault("phasen", [{"id": "p1", "name": "Einstieg", "dauer_min": 10, "prio": "kern"}])
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO context_nodes (id, category, content_type, title, owner_pseudonym, read_scope, write_scope,"
            " read_scope_group_id, write_scope_group_id, subject_id, status, metadata, created_at)"
            " VALUES (%s, 'artifact', %s, %s, %s, 'group_teachers', 'group_teachers', %s, %s, %s, %s, %s::jsonb,"
            " %s)",
            (str(nid), typ, titel, owner, gruppe, gruppe, FACH, status, json.dumps(metadata),
             VOR_EINEM_JAHR + timedelta(minutes=minuten)),
        )
    conn.commit()
    return str(nid)


def _kante(conn, von, nach, relation):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO context_edges (from_node_id, to_node_id, relation) VALUES (%s, %s, %s)",
                    (von, nach, relation))
    conn.commit()


def _einheit_mit_stunden(conn, gruppe, titel, stunden, *, owner=TEACHER1_PSEUDO):
    """Eine Einheit und ihre Stunden in Reihenfolge (`follows`), Anlegezeit absichtlich verkehrt."""
    ue = _knoten(conn, "unterrichtseinheit", gruppe, titel, owner=owner)
    ids = []
    for i, name in enumerate(stunden):
        sid = _knoten(conn, "unterrichtsstunde", gruppe, name, owner=owner, minuten=100 - i)
        _kante(conn, sid, ue, "part_of")
        if ids:
            _kante(conn, sid, ids[-1], "follows")
        ids.append(sid)
    return ue, ids


def _status(conn, node_id, status):
    with conn.cursor() as cur:
        cur.execute("UPDATE context_nodes SET status = %s WHERE id = %s", (status, node_id))
    conn.commit()


async def _archiv(client, headers):
    resp = await client.get("/planning/archive", headers=headers)
    assert resp.status_code == 200, resp.text
    return {g["id"]: g for g in resp.json()["items"] if g["id"] in GRUPPEN}


# ── Liste ─────────────────────────────────────────────────────────────────────


async def test_archiv_listet_fruehere_und_eigene_gruppen(test_client, auth_headers, conn):
    _einheit_mit_stunden(conn, AKTUELL, "Laufend", ["Heute"])
    _einheit_mit_stunden(conn, FRUEHER, "Säuren", ["Eins", "Zwei"])
    _knoten(conn, "unterrichtsstunde", FRUEHER, "Von der Kollegin", owner=TEACHER2_PSEUDO)
    _einheit_mit_stunden(conn, WEG, "Redox", ["Drei"])
    _einheit_mit_stunden(conn, WEG, "Fremde Einheit", ["Fremd A", "Fremd B"], owner=TEACHER2_PSEUDO)
    _einheit_mit_stunden(conn, FREMD, "Nie meins", ["X"], owner=TEACHER2_PSEUDO)

    archiv = await _archiv(test_client, auth_headers)

    assert set(archiv) == {FRUEHER, WEG}
    assert (archiv[FRUEHER]["zugang"], archiv[FRUEHER]["einheiten"], archiv[FRUEHER]["stunden"]) == ("mitglied", 1, 3)
    assert (archiv[WEG]["zugang"], archiv[WEG]["einheiten"], archiv[WEG]["stunden"]) == ("eigentum", 1, 1)
    assert archiv[FRUEHER]["schuljahr"] == VORJAHR
    assert archiv[FRUEHER]["fach"]["slug"] == "ao-archiv"


async def test_gruppe_ohne_eigene_planung_fehlt(test_client, auth_headers, conn):
    """Mitglied einer früheren Gruppe, aber dort gibt es nichts — dann nichts im Archiv."""
    archiv = await _archiv(test_client, auth_headers)
    assert FRUEHER not in archiv


async def test_fremde_lehrkraft_sieht_mein_archiv_nicht(test_client, auth_headers_teacher2, conn):
    _einheit_mit_stunden(conn, FRUEHER, "Säuren", ["Eins"])
    archiv = await _archiv(test_client, auth_headers_teacher2)
    assert FRUEHER not in archiv
    # WEG und FREMD sind für teacher2 aktuelle Gruppen (ohne Quellklasse) → im Menü.
    assert WEG not in archiv and FREMD not in archiv


# ── Inhalt einer Gruppe ───────────────────────────────────────────────────────


async def test_inhalt_mitglied_alles_in_reihenfolge(test_client, auth_headers, conn):
    ue, ids = _einheit_mit_stunden(conn, FRUEHER, "Säuren", ["Eins", "Zwei", "Drei"])
    lose = _knoten(conn, "unterrichtsstunde", FRUEHER, "Ohne Einheit", owner=TEACHER2_PSEUDO)

    resp = await test_client.get(f"/planning/archive/groups/{FRUEHER}", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    daten = resp.json()
    assert daten["gruppe"]["zugang"] == "mitglied"
    assert [e["id"] for e in daten["einheiten"]] == [ue]
    assert [s["id"] for s in daten["einheiten"][0]["stunden"]] == ids
    assert [s["id"] for s in daten["ohne_einheit"]] == [lose]


async def test_inhalt_eigentum_nur_eigenes(test_client, auth_headers, conn):
    eigene_ue, eigene = _einheit_mit_stunden(conn, WEG, "Redox", ["Meine"])
    fremde_ue, fremde = _einheit_mit_stunden(conn, WEG, "Fremde Einheit", ["Fremd"], owner=TEACHER2_PSEUDO)
    # Eine eigene Stunde in der fremden Einheit.
    meine_in_fremder = _knoten(conn, "unterrichtsstunde", WEG, "Meine in fremder")
    _kante(conn, meine_in_fremder, fremde_ue, "part_of")
    _knoten(conn, "unterrichtseinheit", WEG, "Fremd und leer", owner=TEACHER2_PSEUDO)

    daten = (await test_client.get(f"/planning/archive/groups/{WEG}", headers=auth_headers)).json()

    einheiten = {e["titel"]: [s["id"] for s in e["stunden"]] for e in daten["einheiten"]}
    assert einheiten == {"Redox": eigene, "Fremde Einheit": [meine_in_fremder]}
    assert daten["ohne_einheit"] == []
    assert fremde[0] not in json.dumps(daten)


async def test_inhalt_ohne_zugang_404(test_client, auth_headers, conn):
    _einheit_mit_stunden(conn, FREMD, "Nie meins", ["X"], owner=TEACHER2_PSEUDO)
    fremd = await test_client.get(f"/planning/archive/groups/{FREMD}", headers=auth_headers)
    gibts_nicht = await test_client.get("/planning/archive/groups/987654", headers=auth_headers)
    klasse = await test_client.get(f"/planning/archive/groups/{KLASSE}", headers=auth_headers)
    assert (fremd.status_code, gibts_nicht.status_code, klasse.status_code) == (404, 404, 404)


async def test_vorschau_kommt_nicht_ins_archiv(test_client, jwt_service, conn):
    jetzt = int(time.time())
    token, _ = jwt_service.issue(
        pseudonym=TEACHER1_PSEUDO, roles=["student"], grade="8",
        preview=Vorschau(echte_rollen=["teacher"], beginn=jetzt, sitzung_ablauf=jetzt + 3600),
        exp=jetzt + 3600,
    )
    h = {"Cookie": f"session={token}"}
    liste = await test_client.get("/planning/archive", headers=h)
    inhalt = await test_client.get(f"/planning/archive/groups/{FRUEHER}", headers=h)
    assert (liste.status_code, inhalt.status_code) == (403, 403)


# ── Archivierte Knoten (F11) und Ändern nur in aktuellen Gruppen (S3) ─────────


async def test_archivierte_stunde_lesbar_nicht_aenderbar(test_client, auth_headers, conn):
    ue, (stunde,) = _einheit_mit_stunden(conn, WEG, "Redox", ["Archiviert"])
    _status(conn, ue, "archived")
    _status(conn, stunde, "archived")

    gelesen = await test_client.get(f"/planning/lessons/{stunde}", headers=auth_headers)
    geaendert = await test_client.patch(f"/planning/lessons/{stunde}", headers=auth_headers,
                                        json={"titel": "Neu"})
    export = await test_client.get(f"/planning/lessons/{stunde}/export", headers=auth_headers)
    inhalt = (await test_client.get(f"/planning/archive/groups/{WEG}", headers=auth_headers)).json()

    assert gelesen.status_code == 200, gelesen.text
    assert gelesen.json()["darf_bearbeiten"] is False
    assert gelesen.json()["ue"]["id"] == ue
    assert geaendert.status_code == 404
    assert export.status_code == 200, export.text
    assert inhalt["einheiten"][0]["archiviert"] is True
    assert inhalt["einheiten"][0]["stunden"][0]["archiviert"] is True


async def test_geloeschte_stunde_bleibt_weg(test_client, auth_headers, conn):
    _, (stunde,) = _einheit_mit_stunden(conn, WEG, "Redox", ["Gelöscht"])
    _status(conn, stunde, "deleted")
    resp = await test_client.get(f"/planning/lessons/{stunde}", headers=auth_headers)
    inhalt = (await test_client.get(f"/planning/archive/groups/{WEG}", headers=auth_headers)).json()
    assert resp.status_code == 404
    assert inhalt["einheiten"][0]["stunden"] == []


async def test_mitglied_einer_frueheren_gruppe_liest_nur(test_client, auth_headers, conn):
    _, (frueher,) = _einheit_mit_stunden(conn, FRUEHER, "Säuren", ["Früher"])
    _, (aktuell,) = _einheit_mit_stunden(conn, AKTUELL, "Laufend", ["Heute"])

    frueh = await test_client.get(f"/planning/lessons/{frueher}", headers=auth_headers)
    akt = await test_client.get(f"/planning/lessons/{aktuell}", headers=auth_headers)
    patch_frueh = await test_client.patch(f"/planning/lessons/{frueher}", headers=auth_headers,
                                          json={"titel": "Neu"})
    patch_akt = await test_client.patch(f"/planning/lessons/{aktuell}", headers=auth_headers,
                                        json={"titel": "Neu"})

    assert (frueh.json()["darf_bearbeiten"], akt.json()["darf_bearbeiten"]) == (False, True)
    assert (patch_frueh.status_code, patch_akt.status_code) == (403, 200)


async def test_fremde_lehrkraft_liest_archivierte_stunde_nicht(test_client, auth_headers_teacher2, conn):
    _, (stunde,) = _einheit_mit_stunden(conn, FRUEHER, "Säuren", ["Früher"])
    _status(conn, stunde, "archived")
    resp = await test_client.get(f"/planning/lessons/{stunde}", headers=auth_headers_teacher2)
    assert resp.status_code == 403


# ── Schuljahr aus den Metadaten (Fund der Sichtung) ───────────────────────────


async def test_jahresplan_im_laufenden_jahr_macht_gruppe_aktuell(test_client, auth_headers, conn):
    """`gruppen_mit_beleg` las bis 0.42 nur die nie gefüllte Spalte `schuljahr`."""
    _einheit_mit_stunden(conn, FRUEHER, "Säuren", ["Eins"])
    assert FRUEHER in await _archiv(test_client, auth_headers)

    _knoten(conn, "jahresplan", FRUEHER, "Jahresplan", meta={"schuljahr": JAHR.schuljahr})

    assert FRUEHER not in await _archiv(test_client, auth_headers)


async def test_fruehere_gruppe_nennt_ihr_schuljahr(test_client, auth_headers, conn):
    """`letztes_schuljahr` in `/groups/me` — ebenfalls aus den Metadaten."""
    _einheit_mit_stunden(conn, FRUEHER, "Säuren", ["Eins"])
    resp = await test_client.get("/groups/me", headers=auth_headers)
    gruppe = next(g for g in resp.json()["items"] if g["id"] == FRUEHER)
    assert gruppe["letztes_schuljahr"] == VORJAHR
