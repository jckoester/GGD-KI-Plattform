"""Integrationstests für „Meine Bausteine" — AP7, Schritt 1.

Geprüft wird der Endpunkt `GET /context/nodes/mine` und seine Zählung: Sieht jede
Rolle **nur Eigenes**, stimmen die vier Aufmerksamkeits-Kategorien gegen von Hand
gesetzte Daten, und liefert der Sidebar-Zähler dieselbe Zahl wie der Banner?

Router-Pfade ohne /api-Präfix (CLAUDE.md: FastAPI sieht /api nie).
"""
import json
import uuid
from datetime import date, timedelta

import psycopg2
import pytest

# ⚠️ **Eigene Pseudonyme, nicht die der conftest.** Die Zählung läuft über *alle*
# Knoten eines Eigentümers. Mit `teacher1-pseudo` hingen die Zahlen daran, was
# andere Testdateien unter demselben Pseudonym angelegt haben — einzeln grün, im
# Gesamtlauf rot, je nach Reihenfolge. Genau so ist es beim Bauen passiert.
TEACHER = "teacher-meine-bausteine"
STUDENT = "student-meine-bausteine"
FREMD = "fremd-meine-bausteine"

SUBJECT_A = 620  # kleinere sort_order → steht vorn
SUBJECT_B = 621


@pytest.fixture(scope="module")
def sync_conn(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def faecher(sync_conn):
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO subjects (id, slug, name, sort_order) VALUES "
            "(%s,'mb-alpha','Alpha',1), (%s,'mb-beta','Beta',2) "
            "ON CONFLICT (id) DO NOTHING",
            (SUBJECT_A, SUBJECT_B),
        )
    sync_conn.commit()
    yield
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        cur.execute("DELETE FROM subjects WHERE id IN (%s,%s)", (SUBJECT_A, SUBJECT_B))
    sync_conn.commit()


def _node(cur, titel, *, owner, subject=None, status="active",
          valid_until=None, metadata=None, updated=None):
    nid = uuid.uuid4()
    cur.execute(
        "INSERT INTO context_nodes (id, category, content_type, title, owner_pseudonym,"
        " subject_id, read_scope, write_scope, status, valid_until, metadata, updated_at)"
        " VALUES (%s,'artifact','arbeitsblatt',%s,%s,%s,'private','private',%s,%s,%s,"
        " coalesce(%s, now()))",
        (str(nid), titel, owner, subject, status, valid_until,
         json.dumps(metadata or {}), updated),
    )
    return nid


@pytest.fixture
def bestand(sync_conn, faecher):
    """Ein durchgerechneter Bestand — jede Kategorie genau einmal belegt."""
    heute = date.today()
    with sync_conn.cursor() as cur:
        ids = {
            # Zwei Fächer, um Gruppierung und Reihenfolge zu prüfen …
            "alpha_neu": _node(cur, "Alpha neu", owner=TEACHER, subject=SUBJECT_A,
                               updated="2026-09-05 10:00+02"),
            "alpha_alt": _node(cur, "Alpha alt", owner=TEACHER, subject=SUBJECT_A,
                               updated="2026-01-01 10:00+01"),
            "beta": _node(cur, "Beta", owner=TEACHER, subject=SUBJECT_B),
            # … und einer ohne Fach, der ans Ende gehört.
            "ohne_fach": _node(cur, "Ohne Fach", owner=TEACHER),
            # Kategorie 1: läuft in ≤ 14 Tagen ab
            "bald": _node(cur, "Läuft bald ab", owner=TEACHER, subject=SUBJECT_A,
                          valid_until=heute + timedelta(days=3)),
            # Kategorie 2: archiviert und Datum überschritten
            "abgelaufen": _node(cur, "Abgelaufen", owner=TEACHER, subject=SUBJECT_A,
                                status="archived", valid_until=heute - timedelta(days=1)),
            # Kategorie 4: Stub
            "stub": _node(cur, "Unvollständig", owner=TEACHER, subject=SUBJECT_A,
                          metadata={"unvollstaendig": True}),
            # Fremd — darf nirgends auftauchen
            "fremd": _node(cur, "Fremder Baustein", owner=FREMD, subject=SUBJECT_A),
            # Schülerin
            "schueler": _node(cur, "Schüler-Baustein", owner=STUDENT),
            "schueler_stub": _node(cur, "Schüler-Stub", owner=STUDENT,
                                   metadata={"unvollstaendig": True}),
        }
        # Kategorie 3: verweist auf einen archivierten Knoten
        archiviert = _node(cur, "Archiviertes Ziel", owner=FREMD, status="archived")
        ids["verweist"] = _node(cur, "Verweist auf Archiviertes", owner=TEACHER,
                                subject=SUBJECT_B)
        cur.execute(
            "INSERT INTO context_edges (from_node_id, to_node_id, relation, metadata)"
            " VALUES (%s,%s,'references','{}')",
            (str(ids["verweist"]), str(archiviert)),
        )
        ids["archiviert_ziel"] = archiviert
    sync_conn.commit()
    yield ids
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        for nid in ids.values():
            cur.execute("DELETE FROM context_edges WHERE from_node_id = %s OR to_node_id = %s",
                        (str(nid), str(nid)))
            cur.execute("DELETE FROM context_nodes WHERE id = %s", (str(nid),))
    sync_conn.commit()


@pytest.fixture
def lehrer_headers(jwt_service):
    """Lehrkraft **ohne** Admin-Rolle — so wird auch geprüft, dass die Kategorie
    „unvollständig" an `teacher` hängt und nicht an `admin`."""
    token, _ = jwt_service.issue(pseudonym=TEACHER, roles=["teacher"], grade=None)
    return {"Cookie": f"session={token}"}


@pytest.fixture
def schueler_headers(jwt_service):
    token, _ = jwt_service.issue(pseudonym=STUDENT, roles=["student"], grade="8")
    return {"Cookie": f"session={token}"}


def _titel(daten):
    return [b["title"] for a in daten["abschnitte"] for b in a["bausteine"]]


# ── Sichtbarkeit ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lehrkraft_sieht_nur_eigenes(test_client, lehrer_headers, bestand):
    daten = (await test_client.get("/context/nodes/mine", headers=lehrer_headers)).json()
    assert "Fremder Baustein" not in _titel(daten)
    assert "Schüler-Baustein" not in _titel(daten)
    assert "Alpha neu" in _titel(daten)


@pytest.mark.asyncio
async def test_schuelerin_bekommt_die_seite_und_nur_eigenes(
    test_client, schueler_headers, bestand
):
    """Der Endpunkt ist rollenoffen — anders als `GET /context/nodes`, das für
    Schüler:innen 403 liefert. Für sie ist dies neben der Suche die einzige
    Wissensgraph-Fläche (ADR-019 F8)."""
    resp = await test_client.get("/context/nodes/mine", headers=schueler_headers)
    assert resp.status_code == 200, resp.text
    assert sorted(_titel(resp.json())) == ["Schüler-Baustein", "Schüler-Stub"]


@pytest.mark.asyncio
async def test_ohne_anmeldung_kein_zugriff(test_client, bestand):
    assert (await test_client.get("/context/nodes/mine")).status_code == 401


# ── Gruppierung und Reihenfolge ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gruppiert_nach_fach_ohne_fach_am_ende(test_client, lehrer_headers, bestand):
    daten = (await test_client.get("/context/nodes/mine", headers=lehrer_headers)).json()
    faecher = [a["fach"] for a in daten["abschnitte"]]
    assert faecher == ["Alpha", "Beta", None], "nach sort_order, ohne Fach zuletzt"
    assert daten["abschnitte"][-1]["subject_id"] is None


@pytest.mark.asyncio
async def test_innerhalb_eines_fachs_nach_aktualitaet(test_client, lehrer_headers, bestand):
    daten = (await test_client.get("/context/nodes/mine", headers=lehrer_headers)).json()
    alpha = next(a for a in daten["abschnitte"] if a["fach"] == "Alpha")
    titel = [b["title"] for b in alpha["bausteine"]]
    assert titel.index("Alpha neu") < titel.index("Alpha alt")


@pytest.mark.asyncio
async def test_abschnitt_zaehlt_seine_bausteine(test_client, lehrer_headers, bestand):
    daten = (await test_client.get("/context/nodes/mine", headers=lehrer_headers)).json()
    for abschnitt in daten["abschnitte"]:
        assert abschnitt["anzahl"] == len(abschnitt["bausteine"])
    assert daten["gesamt"] == sum(a["anzahl"] for a in daten["abschnitte"])


# ── Aufmerksamkeit ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_die_vier_kategorien_zaehlen_richtig(test_client, lehrer_headers, bestand):
    a = (await test_client.get("/context/nodes/mine", headers=lehrer_headers)).json()["aufmerksamkeit"]
    assert a["laeuft_bald_ab"] == 1
    assert a["abgelaufen"] == 1
    assert a["archivierte_referenzen"] == 1
    assert a["unvollstaendig"] == 1
    assert a["gesamt"] == 4


@pytest.mark.asyncio
async def test_kategorien_stehen_an_der_zeile(test_client, lehrer_headers, bestand):
    daten = (await test_client.get("/context/nodes/mine", headers=lehrer_headers)).json()
    nach_titel = {b["title"]: b for a in daten["abschnitte"] for b in a["bausteine"]}
    assert nach_titel["Läuft bald ab"]["kategorien"] == ["laeuft_bald_ab"]
    assert nach_titel["Abgelaufen"]["kategorien"] == ["abgelaufen"]
    assert nach_titel["Verweist auf Archiviertes"]["kategorien"] == ["archivierte_referenzen"]
    assert nach_titel["Unvollständig"]["kategorien"] == ["unvollstaendig"]
    assert nach_titel["Alpha neu"]["kategorien"] == []


@pytest.mark.asyncio
async def test_schuelerin_bekommt_keine_stub_warnung(
    test_client, schueler_headers, bestand
):
    """„Unvollständig" ist eine Lehrkraft-Kategorie (A4) — Schüler:innen erzeugen
    keine Stubs, und eine Warnung, die sie nicht auflösen können, wäre Lärm."""
    daten = (await test_client.get("/context/nodes/mine", headers=schueler_headers)).json()
    assert daten["aufmerksamkeit"]["unvollstaendig"] == 0
    assert daten["aufmerksamkeit"]["gesamt"] == 0
    nach_titel = {b["title"]: b for a in daten["abschnitte"] for b in a["bausteine"]}
    assert nach_titel["Schüler-Stub"]["kategorien"] == []


@pytest.mark.asyncio
async def test_gesamt_zaehlt_mehrfach_betroffene_nur_einmal(
    test_client, lehrer_headers, sync_conn, bestand
):
    """`gesamt` ist nicht die Summe der Kategorien — sonst zählte ein Baustein,
    der abgelaufen *und* auf Archiviertes verweisend ist, doppelt."""
    with sync_conn.cursor() as cur:
        cur.execute(
            "UPDATE context_nodes SET status='archived', valid_until=%s WHERE id=%s",
            (date.today() - timedelta(days=2), str(bestand["verweist"])),
        )
    sync_conn.commit()

    a = (await test_client.get("/context/nodes/mine", headers=lehrer_headers)).json()["aufmerksamkeit"]
    assert a["abgelaufen"] == 2
    assert a["archivierte_referenzen"] == 1
    assert a["gesamt"] == 4, "der doppelt betroffene Baustein zählt einmal"


# ── Filter ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_nur_aufmerksamkeit_filtert_die_liste(test_client, lehrer_headers, bestand):
    daten = (await test_client.get(
        "/context/nodes/mine?nur_aufmerksamkeit=true", headers=lehrer_headers)).json()
    assert sorted(_titel(daten)) == [
        "Abgelaufen", "Läuft bald ab", "Unvollständig", "Verweist auf Archiviertes",
    ]
    assert daten["aufmerksamkeit"]["gesamt"] == 4, "die Zählung bleibt die des Gesamtbestands"


@pytest.mark.asyncio
async def test_typ_filter(test_client, lehrer_headers, sync_conn, bestand):
    with sync_conn.cursor() as cur:
        cur.execute("UPDATE context_nodes SET content_type='aufgabe' WHERE id=%s",
                    (str(bestand["beta"]),))
    sync_conn.commit()

    daten = (await test_client.get(
        "/context/nodes/mine?content_type=aufgabe", headers=lehrer_headers)).json()
    assert _titel(daten) == ["Beta"]


# ── Sidebar-Zähler ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_zaehlung_liefert_dieselben_zahlen_wie_die_liste(
    test_client, lehrer_headers, bestand
):
    """Banner und Sidebar-Zähler stammen aus derselben Funktion — hier wird das
    festgehalten, damit sie nicht auseinanderlaufen."""
    liste = (await test_client.get("/context/nodes/mine", headers=lehrer_headers)).json()
    zaehlung = (await test_client.get("/context/nodes/mine/zaehlung", headers=lehrer_headers)).json()
    assert zaehlung == liste["aufmerksamkeit"]


@pytest.mark.asyncio
async def test_zaehlung_ist_rollenoffen(test_client, schueler_headers, bestand):
    resp = await test_client.get("/context/nodes/mine/zaehlung", headers=schueler_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["gesamt"] == 0


# ── Routenreihenfolge ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mine_wird_nicht_als_knoten_id_gelesen(test_client, lehrer_headers, bestand):
    """⚠️ `/nodes/mine` muss **vor** `/nodes/{node_id}` deklariert sein.

    Sonst versucht FastAPI, „mine" als UUID zu lesen, und antwortet mit 422 —
    eine Reihenfolge-Abhängigkeit, die man beim Umsortieren der Datei nicht sieht.
    """
    resp = await test_client.get("/context/nodes/mine", headers=lehrer_headers)
    assert resp.status_code == 200, "422 hieße: als node_id gelesen"
    assert "abschnitte" in resp.json()
