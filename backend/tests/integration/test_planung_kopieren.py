"""Stunde kopieren (0.42, Päckchen AO, Schritt 3; Plan F4–F6, F8, F9, F11, S1).

Gegen echtes Postgres. Gruppen von teacher1 (`auth_headers`):

* ``QUELLE`` — aktuell, Mitglied; teacher2 unterrichtet mit (F9).
* ``ZIEL`` — aktuell, Mitglied, dasselbe Fach.
* ``ANDERES`` — aktuell, Mitglied, anderes Fach (F5).
* ``ALT`` — Mitglied, aber nicht mehr aktuell (Klasse aus dem Vorjahr, kein Beleg).
* ``FREMD`` — nur teacher2.
* ``KLASSE`` — Klassenverband als Quellklasse für ``ALT``.
"""
import json
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import psycopg2
import pytest

from app.auth.vorschau import Vorschau
from app.planning import kopieren
from app.planning.calendar import load_school_year
from tests.integration.conftest import TEACHER1_PSEUDO, TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio

FACH, FACH2 = 9430, 9439
QUELLE, ZIEL, ANDERES, ALT, FREMD, KLASSE = 9431, 9432, 9433, 9434, 9435, 9436
GRUPPEN = [QUELLE, ZIEL, ANDERES, ALT, FREMD, KLASSE]
JAHR = load_school_year()
VOR_EINEM_JAHR = datetime.combine(JAHR.beginn, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=200)


@pytest.fixture
def conn(db_url, run_migrations):
    c = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))

    def aufraeumen():
        with c.cursor() as cur:
            cur.execute("DELETE FROM context_nodes WHERE write_scope_group_id = ANY(%s) "
                        "OR read_scope_group_id = ANY(%s) OR subject_id = ANY(%s)",
                        (GRUPPEN, GRUPPEN, [FACH, FACH2]))
            cur.execute("DELETE FROM groups WHERE id = ANY(%s)", (GRUPPEN,))
            cur.execute("DELETE FROM subjects WHERE id = ANY(%s)", ([FACH, FACH2],))
        c.commit()

    aufraeumen()
    with c.cursor() as cur:
        for fid, slug in ((FACH, "ao-kopie"), (FACH2, "ao-kopie-2")):
            cur.execute("INSERT INTO subjects (id, slug, name, icon, color) VALUES (%s, %s, %s, 'Atom', 'bl')",
                        (fid, slug, slug))
        for gid, typ, fach, angelegt in (
            (QUELLE, "teaching_group", FACH, None), (ZIEL, "teaching_group", FACH, None),
            (ANDERES, "teaching_group", FACH2, None), (ALT, "teaching_group", FACH, VOR_EINEM_JAHR),
            (FREMD, "teaching_group", FACH, None), (KLASSE, "school_class", None, VOR_EINEM_JAHR),
        ):
            cur.execute("INSERT INTO groups (id, name, slug, type, subject_id, created_at) "
                        "VALUES (%s, %s, %s, %s, %s, COALESCE(%s, now()))",
                        (gid, f"AO {gid}", f"ao-{gid}", typ, fach, angelegt))
        cur.execute("INSERT INTO group_source_classes (group_id, class_group_id) VALUES (%s, %s)", (ALT, KLASSE))
        for gid, wer in ((QUELLE, TEACHER1_PSEUDO), (QUELLE, TEACHER2_PSEUDO), (ZIEL, TEACHER1_PSEUDO),
                         (ANDERES, TEACHER1_PSEUDO), (ALT, TEACHER1_PSEUDO), (FREMD, TEACHER2_PSEUDO)):
            cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                        "VALUES (%s, %s, 'teacher', 'eigen')", (gid, wer))
    c.commit()
    yield c
    c.rollback()
    aufraeumen()
    c.close()


def _knoten(conn, typ, titel, *, gruppe=None, owner=TEACHER1_PSEUDO, status="active", meta=None,
            scope="group_teachers", kategorie="artifact", bp="", fach=FACH):
    nid = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO context_nodes (id, category, content_type, title, owner_pseudonym, read_scope, write_scope,"
            " read_scope_group_id, write_scope_group_id, subject_id, status, metadata, bp_version)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)",
            (nid, kategorie, typ, titel, owner, scope, scope if scope.startswith("group") else "private",
             gruppe, gruppe, fach, status, json.dumps(meta or {}), bp),
        )
    conn.commit()
    return nid


def _kante(conn, von, nach, relation):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO context_edges (from_node_id, to_node_id, relation) VALUES (%s, %s, %s)",
                    (von, nach, relation))
    conn.commit()


def _stunde(conn, gruppe, titel="Säuren und Basen", *, owner=TEACHER1_PSEUDO, meta=None, status="active"):
    return _knoten(conn, "unterrichtsstunde", titel, gruppe=gruppe, owner=owner, status=status,
                   meta=meta or {"phasen": [{"id": "p1", "name": "Einstieg", "dauer_min": 10, "prio": "kern"}]})


def _einheit(conn, gruppe, titel="Einheit", schuljahr=JAHR.schuljahr):
    return _knoten(conn, "unterrichtseinheit", titel, gruppe=gruppe, meta={"schuljahr": schuljahr})


def _lies(conn, sql, *args):
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


async def _kopiere(client, headers, stunde, **ziel):
    return await client.post(f"/planning/lessons/{stunde}/copy", headers=headers, json=ziel)


# ── Felder ───────────────────────────────────────────────────────────────────


async def test_kopie_nimmt_entwurf_mit_und_laesst_gehaltenes_weg(test_client, auth_headers, conn):
    schulweit = _knoten(conn, "arbeitsblatt", "AB Neutralisation", scope="school")
    nur_quelle = _knoten(conn, "arbeitsblatt", "AB nur alte Gruppe", gruppe=QUELLE, scope="group")
    begriff = _knoten(conn, "begriff", "Neutralisation", scope="school", kategorie="concept")
    methode = {"typ": "node", "node_id": str(uuid.uuid4()), "titel": "Think-Pair-Share"}
    quelle = _stunde(conn, QUELLE, meta={
        "stundenziel": "Neutralisation erklären",
        "phasen": [
            {"id": "p1", "name": "Einstieg", "dauer_min": 10, "prio": "kern", "beschreibung": "Versuch",
             "methode": methode, "status": "erledigt", "status_vorher": "offen",
             "material": [{"typ": "node", "node_id": schulweit, "titel": "AB Neutralisation"},
                          {"typ": "node", "node_id": nur_quelle, "titel": "AB nur alte Gruppe"},
                          {"typ": "text", "wert": "Indikator"}]},
            {"id": "p2", "name": "Sicherung", "dauer_min": 20, "prio": "uebung", "status": "gestrichen",
             "kuerzung": True, "uebertrag_von": "x"},
        ],
        "refs": [{"node_id": begriff, "typ": "concept", "titel": "Neutralisation", "partiell": True}],
        "refs_dismissed": [str(uuid.uuid4())],
        "refs_offen": [begriff],
        "begriffe_vorschlag": {"begriffe": ["Salz"]},
        "reflexion": "Versuch dauerte zu lang",
    })
    with conn.cursor() as cur:
        cur.execute("INSERT INTO lesson_slots (group_id, date, halbjahr, stunde_node_id) "
                    "VALUES (%s, %s, 1, %s)", (QUELLE, date(2026, 9, 14), quelle))
    conn.commit()
    einheit = _einheit(conn, ZIEL)
    vorher = _stunde(conn, ZIEL, "Schon da")
    _kante(conn, vorher, einheit, "part_of")

    resp = await _kopiere(test_client, auth_headers, quelle, gruppe_id=ZIEL, einheit_id=einheit)

    assert resp.status_code == 201, resp.text
    antwort = resp.json()
    assert (antwort["gruppe_id"], antwort["einheit_id"], antwort["einheit_neu"]) == (ZIEL, einheit, False)
    assert [(m["art"], m["titel"], m["was"], m["phase"]) for m in antwort["meldungen"]] == [
        ("material", "AB nur alte Gruppe", "weggelassen", "Einstieg")]

    kopie = antwort["id"]
    (titel, owner, rs, rgid, wgid, status, meta, valid_until, assistant_id), = _lies(
        conn, "SELECT title, owner_pseudonym, read_scope, read_scope_group_id, write_scope_group_id, status, "
              "metadata, valid_until, assistant_id FROM context_nodes WHERE id = %s", kopie)
    assert (titel, owner, rs, rgid, wgid, status) == (
        "Säuren und Basen", TEACHER1_PSEUDO, "group_teachers", ZIEL, ZIEL, "active")
    assert assistant_id is None
    assert valid_until is None or valid_until == JAHR.ende
    assert meta["stundenziel"] == "Neutralisation erklären"
    assert meta["kopie_von"] == quelle
    assert meta["notiz_aus_vorlage"] == {"text": "Versuch dauerte zu lang", "kopie_von": quelle,
                                         "datum": "2026-09-14"}
    for weg in ("reflexion", "refs_dismissed", "refs_offen", "begriffe_vorschlag"):
        assert weg not in meta, weg

    einstieg, sicherung = meta["phasen"]
    assert {einstieg["id"], sicherung["id"]}.isdisjoint({"p1", "p2"})
    assert einstieg["id"] != sicherung["id"]
    for phase in (einstieg, sicherung):
        assert not {"status", "status_vorher", "kuerzung", "uebertrag_von"} & set(phase), phase
    assert (einstieg["beschreibung"], einstieg["methode"]["titel"], sicherung["prio"]) == (
        "Versuch", "Think-Pair-Share", "uebung")
    assert einstieg["material"] == [{"typ": "node", "node_id": schulweit, "titel": "AB Neutralisation"},
                                    {"typ": "text", "wert": "Indikator"}]
    assert meta["refs"] == [{"node_id": begriff, "typ": "concept", "titel": "Neutralisation", "partiell": True}]

    kanten = set(_lies(conn, "SELECT relation, to_node_id::text FROM context_edges WHERE from_node_id = %s", kopie))
    assert kanten == {("part_of", einheit), ("follows", vorher), ("used_with", schulweit)}
    assert _lies(conn, "SELECT count(*) FROM lesson_slots WHERE stunde_node_id = %s", kopie) == [(0,)]
    # Die Quelle bleibt, wie sie war.
    assert _lies(conn, "SELECT metadata->>'reflexion' FROM context_nodes WHERE id = %s", quelle) == [
        ("Versuch dauerte zu lang",)]


async def test_kopie_in_neue_einheit(test_client, auth_headers, conn):
    quelle = _stunde(conn, QUELLE)

    resp = await _kopiere(test_client, auth_headers, quelle, gruppe_id=ZIEL, neue_einheit="  Redox  ")

    assert resp.status_code == 201, resp.text
    einheit = resp.json()["einheit_id"]
    assert resp.json()["einheit_neu"] is True
    (titel, schuljahr), = _lies(conn, "SELECT title, metadata->>'schuljahr' FROM context_nodes WHERE id = %s", einheit)
    assert (titel, schuljahr) == ("Redox", JAHR.schuljahr)
    assert _lies(conn, "SELECT n.content_type FROM context_edges e JOIN context_nodes n ON n.id = e.to_node_id "
                       "WHERE e.from_node_id = %s AND e.relation = 'part_of'", einheit) == [("jahresplan",)]
    kanten = _lies(conn, "SELECT relation FROM context_edges WHERE from_node_id = %s", resp.json()["id"])
    assert kanten == [("part_of",)]


@pytest.mark.parametrize("ziel", [{}, {"einheit_id": "E", "neue_einheit": "Neu"}, {"neue_einheit": "   "}])
async def test_genau_eine_zieleinheit(test_client, auth_headers, conn, ziel):
    quelle = _stunde(conn, QUELLE)
    if ziel.get("einheit_id") == "E":
        ziel["einheit_id"] = _einheit(conn, ZIEL)

    resp = await _kopiere(test_client, auth_headers, quelle, gruppe_id=ZIEL, **ziel)

    assert resp.status_code == 422


# ── Rechte und Ziele ─────────────────────────────────────────────────────────


async def test_ziel_muss_aktuell_eigen_und_vom_selben_fach_sein(test_client, auth_headers, conn):
    quelle = _stunde(conn, QUELLE)

    anderes_fach = await _kopiere(test_client, auth_headers, quelle, gruppe_id=ANDERES,
                                  einheit_id=_einheit(conn, ANDERES))
    # Eine Einheit des laufenden Jahres machte ALT wieder aktuell — deshalb aus dem Vorjahr.
    alt = await _kopiere(test_client, auth_headers, quelle, gruppe_id=ALT,
                         einheit_id=_einheit(conn, ALT, schuljahr="2000/01"))
    fremd = await _kopiere(test_client, auth_headers, quelle, gruppe_id=FREMD, einheit_id=_einheit(conn, FREMD))
    falsche_einheit = await _kopiere(test_client, auth_headers, quelle, gruppe_id=ZIEL,
                                     einheit_id=_einheit(conn, QUELLE))

    assert (anderes_fach.status_code, alt.status_code, fremd.status_code, falsche_einheit.status_code) == (
        422, 422, 403, 422)
    assert "desselben Fachs" in anderes_fach.json()["detail"]
    assert "laufenden Schuljahres" in alt.json()["detail"]
    assert _lies(conn, "SELECT count(*) FROM context_nodes WHERE content_type = 'unterrichtsstunde' "
                       "AND metadata->>'kopie_von' = %s", quelle) == [(0,)]


async def test_wer_lesen_darf_darf_kopieren(test_client, auth_headers, conn):
    von_kollegin = _stunde(conn, QUELLE, "Von der Kollegin", owner=TEACHER2_PSEUDO)
    aus_dem_archiv = _stunde(conn, ALT, "Archiviert", status="archived")
    nicht_lesbar = _stunde(conn, FREMD, "Fremd", owner=TEACHER2_PSEUDO)
    geloescht = _stunde(conn, QUELLE, "Gelöscht", status="deleted")
    einheit = _einheit(conn, ZIEL)

    kollegin = await _kopiere(test_client, auth_headers, von_kollegin, gruppe_id=ZIEL, einheit_id=einheit)
    archiv = await _kopiere(test_client, auth_headers, aus_dem_archiv, gruppe_id=ZIEL, einheit_id=einheit)
    fremd = await _kopiere(test_client, auth_headers, nicht_lesbar, gruppe_id=ZIEL, einheit_id=einheit)
    weg = await _kopiere(test_client, auth_headers, geloescht, gruppe_id=ZIEL, einheit_id=einheit)

    assert (kollegin.status_code, archiv.status_code, fremd.status_code, weg.status_code) == (201, 201, 403, 404)
    assert _lies(conn, "SELECT owner_pseudonym, metadata->>'kopie_von' FROM context_nodes WHERE id = %s",
                 kollegin.json()["id"]) == [(TEACHER1_PSEUDO, von_kollegin)]


async def test_vorschau_kopiert_nicht(test_client, jwt_service, conn):
    jetzt = int(time.time())
    token, _ = jwt_service.issue(
        pseudonym=TEACHER1_PSEUDO, roles=["student"], grade="8",
        preview=Vorschau(echte_rollen=["teacher"], beginn=jetzt, sitzung_ablauf=jetzt + 3600),
        exp=jetzt + 3600,
    )
    resp = await _kopiere(test_client, {"Cookie": f"session={token}"}, _stunde(conn, QUELLE),
                          gruppe_id=ZIEL, einheit_id=_einheit(conn, ZIEL))
    assert resp.status_code == 403


# ── Fassung des Bildungsplans (F4 a) ─────────────────────────────────────────


def _kompetenz(conn, nr, text, bp, typ="ik_kompetenz"):
    return _knoten(conn, typ, f"{nr} {text}", scope="school", kategorie="knowledge", bp=bp,
                   meta={"kompetenz_nr": nr, "bp_version": bp})


async def test_kompetenzen_in_der_fassung_der_zielgruppe(test_client, auth_headers, conn, monkeypatch):
    alt_gleich = _kompetenz(conn, "3.2.1(1)", "Säuren und Basen unterscheiden", "2016")
    neu_gleich = _kompetenz(conn, "3.2.1(1)", "Säuren und Basen unterscheiden", "2016.V3")
    alt_anders = _kompetenz(conn, "3.2.1(2)", "die Neutralisation beschreiben", "2016")
    _kompetenz(conn, "3.2.1(2)", "Redoxreaktionen am Beispiel der Elektrolyse untersuchen", "2016.V3")
    alt_ohne = _kompetenz(conn, "3.2.1(3)", "pH-Werte messen", "2016")
    schon_neu = _kompetenz(conn, "3.2.1(4)", "Indikatoren nutzen", "2016.V3")
    pk_alt = _kompetenz(conn, "2.1(1)", "Fragestellungen formulieren", "2016", typ="pk_kompetenz")
    pk_neu = _kompetenz(conn, "2.1(1)", "Fragestellungen formulieren", "2016.V3", typ="pk_kompetenz")

    def ref(nid, typ="ik", code=""):
        return {"node_id": nid, "typ": typ, "code": code, "titel": f"T {code}", "partiell": False}

    quelle = _stunde(conn, QUELLE, meta={"phasen": [], "refs": [
        ref(alt_gleich, code="3.2.1(1)"), ref(alt_anders, code="3.2.1(2)"), ref(alt_ohne, code="3.2.1(3)"),
        ref(schon_neu, code="3.2.1(4)"), ref(pk_alt, "pk", "2.1(1)")]})
    monkeypatch.setattr(kopieren, "group_grade", _immer(8))
    monkeypatch.setattr(kopieren, "aktive_bp_version", lambda stufe, verfuegbar: "2016.V3")

    resp = await _kopiere(test_client, auth_headers, quelle, gruppe_id=ZIEL, einheit_id=_einheit(conn, ZIEL))

    assert resp.status_code == 201, resp.text
    refs = _lies(conn, "SELECT metadata->'refs' FROM context_nodes WHERE id = %s", resp.json()["id"])[0][0]
    assert [(r["node_id"], r["typ"], r["code"]) for r in refs] == [
        (neu_gleich, "ik", "3.2.1(1)"), (schon_neu, "ik", "3.2.1(4)"), (pk_neu, "pk", "2.1(1)")]
    assert refs[0]["titel"] == "3.2.1(1) Säuren und Basen unterscheiden"
    assert sorted((m["titel"], m["was"]) for m in resp.json()["meldungen"]) == [
        ("T 2.1(1)", "umgestellt"), ("T 3.2.1(1)", "umgestellt"),
        ("T 3.2.1(2)", "weggelassen"), ("T 3.2.1(3)", "weggelassen")]


async def test_ohne_jahrgang_bleiben_kompetenzen(test_client, auth_headers, conn, monkeypatch):
    alt = _kompetenz(conn, "3.2.1(1)", "Säuren und Basen unterscheiden", "2016")
    _kompetenz(conn, "3.2.1(1)", "Säuren und Basen unterscheiden", "2016.V3")
    quelle = _stunde(conn, QUELLE, meta={"phasen": [], "refs": [
        {"node_id": alt, "typ": "ik", "code": "3.2.1(1)", "titel": "T", "partiell": False}]})
    monkeypatch.setattr(kopieren, "group_grade", _immer(None))

    resp = await _kopiere(test_client, auth_headers, quelle, gruppe_id=ZIEL, einheit_id=_einheit(conn, ZIEL))

    assert resp.status_code == 201, resp.text
    assert resp.json()["meldungen"] == []
    refs = _lies(conn, "SELECT metadata->'refs' FROM context_nodes WHERE id = %s", resp.json()["id"])[0][0]
    assert [r["node_id"] for r in refs] == [alt]


def _immer(wert):
    async def f(*_):
        return wert
    return f


# ── Notiz aus der Vorlage (S1) ───────────────────────────────────────────────


async def test_notiz_wandert_weiter_und_laesst_sich_entfernen(test_client, auth_headers, conn):
    original = _stunde(conn, QUELLE, meta={"phasen": [], "reflexion": "Gruppenarbeit zu lang"})
    einheit = _einheit(conn, ZIEL)
    erste = (await _kopiere(test_client, auth_headers, original, gruppe_id=ZIEL, einheit_id=einheit)).json()["id"]

    zweite = await _kopiere(test_client, auth_headers, erste, gruppe_id=ZIEL, einheit_id=einheit)

    assert zweite.status_code == 201, zweite.text
    lesen = await test_client.get(f"/planning/lessons/{zweite.json()['id']}", headers=auth_headers)
    assert lesen.status_code == 200
    assert lesen.json()["kopie_von"] == erste
    assert lesen.json()["notiz_aus_vorlage"] == {"text": "Gruppenarbeit zu lang", "kopie_von": original,
                                                 "datum": None}
    # Folgt der Kette: die zweite Kopie hängt an der ersten.
    assert _lies(conn, "SELECT count(*) FROM context_edges WHERE from_node_id = %s AND to_node_id = %s "
                       "AND relation = 'follows'", zweite.json()["id"], erste) == [(1,)]

    weg = await test_client.patch(f"/planning/lessons/{erste}", headers=auth_headers,
                                  json={"notiz_aus_vorlage_entfernen": True})
    assert weg.status_code == 200, weg.text
    assert _lies(conn, "SELECT metadata ? 'notiz_aus_vorlage', metadata->>'kopie_von' FROM context_nodes "
                       "WHERE id = %s", erste) == [(False, original)]


# ── F8: der allgemeine Kopierweg lehnt Planung ab ────────────────────────────


async def test_allgemeines_kopieren_lehnt_planung_ab(test_client, auth_headers, conn):
    resp = await test_client.post(f"/context/nodes/{_stunde(conn, QUELLE)}/copy", headers=auth_headers, json={})
    assert resp.status_code == 422
    assert "Planung" in resp.json()["detail"]


# ── Einheit kopieren (Schritt 4) ─────────────────────────────────────────────


def _setze(conn, sql, *args):
    with conn.cursor() as cur:
        cur.execute(sql, args)
    conn.commit()


def _kette(conn, gruppe, titel, namen, *, owner=TEACHER1_PSEUDO, besitzer=None):
    """Einheit mit Stunden in Reihenfolge `namen`; angelegt rückwärts, damit nur `follows` ordnet."""
    ue = _knoten(conn, "unterrichtseinheit", titel, gruppe=gruppe, owner=owner,
                 meta={"schuljahr": "2000/01", "farbe": 3})
    ids = {}
    for name in reversed(namen):
        ids[name] = _stunde(conn, gruppe, name, owner=(besitzer or {}).get(name, owner))
        _kante(conn, ids[name], ue, "part_of")
    for frueher, spaeter in zip(namen, namen[1:]):
        _kante(conn, ids[spaeter], ids[frueher], "follows")
    return ue, ids


def _stunden_der_einheit(conn, einheit):
    """Titel der Stunden einer Einheit in `follows`-Reihenfolge."""
    zeilen = _lies(conn, "SELECT n.id::text, n.title FROM context_edges e JOIN context_nodes n "
                         "ON n.id = e.from_node_id WHERE e.to_node_id = %s AND e.relation = 'part_of'", einheit)
    titel = dict(zeilen)
    folgt = dict(_lies(conn, "SELECT from_node_id::text, to_node_id::text FROM context_edges "
                             "WHERE relation = 'follows' AND from_node_id = ANY(%s::uuid[])", list(titel)))
    assert set(folgt.values()) <= set(titel), "follows zeigt aus der Einheit hinaus"
    anfang = [i for i in titel if i not in folgt]
    assert len(anfang) == 1, folgt
    nach = {v: k for k, v in folgt.items()}
    reihe, aktuell = [], anfang[0]
    while aktuell:
        reihe.append(titel[aktuell])
        aktuell = nach.get(aktuell)
    return reihe


async def test_einheit_mit_stunden_in_reihenfolge(test_client, auth_headers, conn):
    _setze(conn, "UPDATE groups SET jahrgang = 8 WHERE id = %s", ZIEL)
    curriculum = _knoten(conn, "curriculum", "Chemie 8", scope="school", kategorie="document")
    passt = _knoten(conn, "kapitel", "Säuren", scope="school", kategorie="document")
    _kante(conn, passt, curriculum, "part_of")
    fremdes = _knoten(conn, "kapitel", "Kapitel ohne Curriculum der Gruppe", scope="school", kategorie="document")
    ue, ids = _kette(conn, QUELLE, "Säuren und Basen", ["Eins", "Zwei", "Drei"],
                     besitzer={"Zwei": TEACHER2_PSEUDO})
    _setze(conn, "UPDATE context_nodes SET content = 'Beschreibung' WHERE id = %s", ue)
    _kante(conn, ue, passt, "references")
    _kante(conn, ue, fremdes, "references")
    weg = _stunde(conn, QUELLE, "Gelöscht", status="deleted")
    _kante(conn, weg, ue, "part_of")

    resp = await test_client.post(f"/planning/units/{ue}/copy", headers=auth_headers, json={"gruppe_id": ZIEL})

    assert resp.status_code == 201, resp.text
    antwort = resp.json()
    assert (antwort["titel"], antwort["gruppe_id"], antwort["stunden"]) == ("Säuren und Basen", ZIEL, 3)
    assert [(m["art"], m["titel"]) for m in antwort["meldungen"]] == [
        ("kapitel", "Kapitel ohne Curriculum der Gruppe")]
    neu = antwort["id"]
    (owner, wgid, content, meta), = _lies(
        conn, "SELECT owner_pseudonym, write_scope_group_id, content, metadata FROM context_nodes WHERE id = %s", neu)
    assert (owner, wgid, content) == (TEACHER1_PSEUDO, ZIEL, "Beschreibung")
    assert (meta["schuljahr"], meta["farbe"], meta["kopie_von"]) == (JAHR.schuljahr, 3, ue)
    kanten = _lies(conn, "SELECT e.relation, n.content_type, n.id::text FROM context_edges e "
                         "JOIN context_nodes n ON n.id = e.to_node_id WHERE e.from_node_id = %s", neu)
    assert sorted(k[:2] for k in kanten) == [("part_of", "jahresplan"), ("references", "kapitel")]
    assert ("references", "kapitel", passt) in kanten
    assert _stunden_der_einheit(conn, neu) == ["Eins", "Zwei", "Drei"]
    assert _lies(conn, "SELECT DISTINCT owner_pseudonym FROM context_nodes n JOIN context_edges e "
                       "ON e.from_node_id = n.id WHERE e.to_node_id = %s", neu) == [(TEACHER1_PSEUDO,)]
    assert _lies(conn, "SELECT count(*) FROM lesson_slots WHERE ue_node_id = %s", neu) == [(0,)]


async def test_einheit_ohne_mitgliedschaft_nur_eigene_stunden(test_client, auth_headers, conn):
    gemischt, _ = _kette(conn, FREMD, "Gemischt", ["Meine", "Ihre"], owner=TEACHER2_PSEUDO,
                         besitzer={"Meine": TEACHER1_PSEUDO})
    nur_ihre, _ = _kette(conn, FREMD, "Nur ihre", ["Ihre"], owner=TEACHER2_PSEUDO)

    ok = await test_client.post(f"/planning/units/{gemischt}/copy", headers=auth_headers, json={"gruppe_id": ZIEL})
    nein = await test_client.post(f"/planning/units/{nur_ihre}/copy", headers=auth_headers, json={"gruppe_id": ZIEL})

    assert (ok.status_code, nein.status_code) == (201, 403), ok.text
    assert ok.json()["stunden"] == 1
    assert _stunden_der_einheit(conn, ok.json()["id"]) == ["Meine"]


async def test_einheit_ganz_oder_gar_nicht(test_client, auth_headers, conn, monkeypatch):
    ue, _ = _kette(conn, QUELLE, "Abbruch", ["Eins", "Zwei", "Drei"])
    echt = kopieren.kopiere_stunde
    aufrufe = []

    async def bricht_bei_der_zweiten(*args, **kwargs):
        aufrufe.append(1)
        if len(aufrufe) == 2:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail="Absichtlich")
        return await echt(*args, **kwargs)

    monkeypatch.setattr(kopieren, "kopiere_stunde", bricht_bei_der_zweiten)

    resp = await test_client.post(f"/planning/units/{ue}/copy", headers=auth_headers, json={"gruppe_id": ZIEL})

    assert resp.status_code == 422
    assert _lies(conn, "SELECT count(*) FROM context_nodes WHERE write_scope_group_id = %s", ZIEL) == [(0,)]


async def test_einheit_ziel_wie_bei_der_stunde(test_client, auth_headers, conn):
    ue, _ = _kette(conn, QUELLE, "Ziel", ["Eins"])
    anderes = await test_client.post(f"/planning/units/{ue}/copy", headers=auth_headers, json={"gruppe_id": ANDERES})
    fremd = await test_client.post(f"/planning/units/{ue}/copy", headers=auth_headers, json={"gruppe_id": FREMD})
    stunde = await test_client.post(f"/planning/units/{_stunde(conn, QUELLE)}/copy", headers=auth_headers,
                                    json={"gruppe_id": ZIEL})
    assert (anderes.status_code, fremd.status_code, stunde.status_code) == (422, 403, 404)
