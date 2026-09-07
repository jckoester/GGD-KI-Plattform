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
FACHSCHAFT_ID = 622


@pytest.fixture(scope="module")
def sync_conn(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def faecher(sync_conn):
    """Zwei Fächer und eine Fachschaftsgruppe.

    Die Gruppe braucht es für das Curriculum: `check_context_nodes_write_group_id`
    verlangt bei `write_scope='subject'` eine Trägergruppe — das Änderungsrecht
    liegt eben bei einem Gremium, nicht bei einer Person.
    """
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO subjects (id, slug, name, sort_order) VALUES "
            "(%s,'mb-alpha','Alpha',1), (%s,'mb-beta','Beta',2) "
            "ON CONFLICT (id) DO NOTHING",
            (SUBJECT_A, SUBJECT_B),
        )
        cur.execute(
            "INSERT INTO groups (id, name, slug, type, subject_id) "
            "VALUES (%s,'Fachschaft Alpha','mb-fs-alpha','subject_department',%s) "
            "ON CONFLICT (id) DO NOTHING",
            (FACHSCHAFT_ID, SUBJECT_A),
        )
    sync_conn.commit()
    yield
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        cur.execute("DELETE FROM groups WHERE id = %s", (FACHSCHAFT_ID,))
        cur.execute("DELETE FROM subjects WHERE id IN (%s,%s)", (SUBJECT_A, SUBJECT_B))
    sync_conn.commit()


def _node(cur, titel, *, owner, subject=None, status="active", valid_until=None,
          metadata=None, updated=None, content_type="arbeitsblatt",
          category="artifact", read_scope="private", write_scope="private",
          write_group=None):
    """Legt einen Knoten an.

    ⚠️ `check_context_nodes_scope_restrictivity` verlangt, dass das Schreibrecht
    nicht weiter reicht als das Leserecht — `read=private, write=subject` wird
    abgelehnt. Ein echtes Curriculum steht deshalb auf `school`/`subject`.
    """
    nid = uuid.uuid4()
    cur.execute(
        "INSERT INTO context_nodes (id, category, content_type, title, owner_pseudonym,"
        " subject_id, read_scope, write_scope, write_scope_group_id, status, valid_until,"
        " metadata, updated_at)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
        " coalesce(%s, now()))",
        (str(nid), category, content_type, titel, owner, subject, read_scope,
         write_scope, write_group, status, valid_until, json.dumps(metadata or {}), updated),
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

        # Ein Curriculum unter demselben Pseudonym: angelegt von der Lehrkraft,
        # aber von der Fachschaft beschlossen und gepflegt (`write_scope=subject`).
        # Es darf **weder** in der Liste **noch** in der Zählung auftauchen — auch
        # nicht, wenn es auf einen archivierten Knoten verweist.
        ids["curriculum"] = _node(
            cur, "Fachschafts-Curriculum", owner=TEACHER, subject=SUBJECT_A,
            content_type="curriculum", category="knowledge",
            read_scope="school", write_scope="subject", write_group=FACHSCHAFT_ID,
        )
        cur.execute(
            "INSERT INTO context_edges (from_node_id, to_node_id, relation, metadata)"
            " VALUES (%s,%s,'part_of','{}')",
            (str(ids["curriculum"]), str(archiviert)),
        )
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


# ── Abgrenzung: was ist „meins"? ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fachschaftsdokumente_stehen_nicht_in_meinen_bausteinen(
    test_client, lehrer_headers, bestand
):
    """Ein Curriculum trägt das Pseudonym seiner Urheberin, gehört aber der Fachschaft.

    Die Anlage setzt beides zugleich: `owner_pseudonym=user.sub` **und**
    `write_scope="subject"` mit der Fachschaftsgruppe. Das Pseudonym ist dort
    Urheberschaft, nicht Eigentum — Fachschaftsdokumente werden gemeinsam
    beschlossen und berühren keine Betroffenenrechte einer einzelnen Person.
    """
    daten = (await test_client.get("/context/nodes/mine", headers=lehrer_headers)).json()
    assert "Fachschafts-Curriculum" not in _titel(daten)


@pytest.mark.asyncio
async def test_fachschaftsdokumente_loesen_keine_aufmerksamkeit_aus(
    test_client, lehrer_headers, bestand
):
    """Der Fall aus der Praxis: Ein Curriculum verweist auf einen abgelösten
    Bildungsplan-Knoten. Das ist eine Fachschaftsaufgabe für den Curriculum-Editor,
    keine persönliche Aufgabe — und eine Warnung, die eine Zuständigkeit nahelegt,
    die es nicht gibt, ist schlimmer als keine.

    Ohne diese Abgrenzung stand im Sidebar-Zähler eine 1, für die sich auf der
    Seite nichts finden ließ.
    """
    a = (await test_client.get("/context/nodes/mine", headers=lehrer_headers)).json()["aufmerksamkeit"]
    # Nur der eigene Baustein „Verweist auf Archiviertes" zählt, nicht das Curriculum.
    assert a["archivierte_referenzen"] == 1


@pytest.mark.asyncio
async def test_die_typmenge_kommt_aus_der_taxonomie(test_client, lehrer_headers, bestand):
    """Abgeleitet, nicht gepflegt: Der Vorgabewert `write_scope` sagt bereits, wo
    die Pflege liegt. Eine zweite Liste daneben liefe auseinander."""
    from app.context.taxonomy import PERSOENLICHE_CONTENT_TYPES

    assert "arbeitsblatt" in PERSOENLICHE_CONTENT_TYPES
    assert "unterrichtsstunde" in PERSOENLICHE_CONTENT_TYPES  # K5, trotz group-Scope im Bestand
    assert "schuelertext" in PERSOENLICHE_CONTENT_TYPES
    for fremd in ("curriculum", "kapitel", "lernsequenz", "begriff", "methode", "fachplan"):
        assert fremd not in PERSOENLICHE_CONTENT_TYPES, fremd

    daten = (await test_client.get("/context/nodes/mine", headers=lehrer_headers)).json()
    typen = {b["content_type"] for a in daten["abschnitte"] for b in a["bausteine"]}
    assert typen <= PERSOENLICHE_CONTENT_TYPES


# ── „Eingesetzt in" (A4, Lehrkraft-Sicht) ────────────────────────────────────

@pytest.fixture
def einsatz(sync_conn, faecher):
    """Ein Arbeitsblatt in einer Stunde, die Stunde in ihrer Einheit.

    Die beiden Fälle laufen über **verschiedene Kantenrichtungen**: Material trägt
    eingehende `used_with`-Kanten von der Stunde (AP6b), eine Stunde zeigt per
    ausgehendem `part_of` auf ihre Einheit.
    """
    with sync_conn.cursor() as cur:
        einheit = _node(cur, "Einheit Bruchrechnung", owner=TEACHER,
                        content_type="unterrichtseinheit")
        stunde = _node(cur, "Stunde 3: Kürzen", owner=TEACHER,
                       content_type="unterrichtsstunde")
        blatt = _node(cur, "Übungsblatt Kürzen", owner=TEACHER)
        cur.execute(
            "INSERT INTO context_edges (from_node_id, to_node_id, relation, metadata)"
            " VALUES (%s,%s,'used_with',%s), (%s,%s,'part_of','{}')",
            (str(stunde), str(blatt), json.dumps({"via": "material"}),
             str(stunde), str(einheit)),
        )
        ids = {"einheit": einheit, "stunde": stunde, "blatt": blatt}
    sync_conn.commit()
    yield ids
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        for nid in ids.values():
            cur.execute("DELETE FROM context_edges WHERE from_node_id = %s OR to_node_id = %s",
                        (str(nid), str(nid)))
            cur.execute("DELETE FROM context_nodes WHERE id = %s", (str(nid),))
    sync_conn.commit()


def _nach_titel(daten):
    return {b["title"]: b for a in daten["abschnitte"] for b in a["bausteine"]}


@pytest.mark.asyncio
async def test_material_zeigt_die_stunde_die_es_benutzt(
    test_client, lehrer_headers, einsatz
):
    daten = (await test_client.get("/context/nodes/mine", headers=lehrer_headers)).json()
    blatt = _nach_titel(daten)["Übungsblatt Kürzen"]
    assert [o["titel"] for o in blatt["eingesetzt_in"]] == ["Stunde 3: Kürzen"]
    assert blatt["eingesetzt_in"][0]["content_type"] == "unterrichtsstunde"


@pytest.mark.asyncio
async def test_stunde_zeigt_ihre_einheit(test_client, lehrer_headers, einsatz):
    """Die andere Kantenrichtung — hier ist das Gefäß der Einsatzort."""
    daten = (await test_client.get("/context/nodes/mine", headers=lehrer_headers)).json()
    stunde = _nach_titel(daten)["Stunde 3: Kürzen"]
    assert [o["titel"] for o in stunde["eingesetzt_in"]] == ["Einheit Bruchrechnung"]


@pytest.mark.asyncio
async def test_ohne_einsatz_bleibt_die_liste_leer(test_client, lehrer_headers, einsatz):
    """Ein Baustein, den keine Einheit mehr nutzt, ist der natürliche
    Archiv-Kandidat (A4) — er trägt schlicht keine Chips."""
    daten = (await test_client.get("/context/nodes/mine", headers=lehrer_headers)).json()
    assert _nach_titel(daten)["Einheit Bruchrechnung"]["eingesetzt_in"] == []


@pytest.mark.asyncio
async def test_schuelerin_bekommt_keine_einsatzorte(
    test_client, schueler_headers, einsatz
):
    """Bei Schüler:innen gibt es keine Unterrichtsplanung, die etwas einsetzt."""
    daten = (await test_client.get("/context/nodes/mine", headers=schueler_headers)).json()
    for a in daten["abschnitte"]:
        for b in a["bausteine"]:
            assert b["eingesetzt_in"] == []


@pytest.mark.asyncio
async def test_archivierte_einsatzorte_zaehlen_nicht(
    test_client, lehrer_headers, sync_conn, einsatz
):
    """Eine archivierte Stunde setzt nichts mehr ein — sonst sähe ein Baustein
    beschäftigt aus, den in Wahrheit niemand mehr braucht."""
    with sync_conn.cursor() as cur:
        cur.execute("UPDATE context_nodes SET status='archived' WHERE id = %s",
                    (str(einsatz["stunde"]),))
    sync_conn.commit()

    daten = (await test_client.get("/context/nodes/mine", headers=lehrer_headers)).json()
    assert _nach_titel(daten)["Übungsblatt Kürzen"]["eingesetzt_in"] == []
