"""Selbstverwaltung eigener Bausteine — AP7, Schritt 3 (Backend).

Die Seite „Meine Bausteine" ist die Bedienstelle der Betroffenenrechte (ADR-019):
Wer etwas unter seinem Pseudonym gespeichert hat, muss es umbenennen, archivieren
und löschen können — **unabhängig von der Rolle**. Bis 09/2026 hingen alle diese
Endpunkte an `_TEACHER_OR_ADMIN`; für Schüler:innen endete schon der Zeilenklick
auf das Detail mit 403.

Geprüft wird beides: dass die eigenen Aktionen jetzt gehen **und** dass fremde
weiterhin scheitern. Der Rollenriegel ist gefallen, der Rechteriegel nicht.

Router-Pfade ohne /api-Präfix (CLAUDE.md: FastAPI sieht /api nie).
"""
import json
import uuid
from datetime import date, timedelta

import psycopg2
import pytest

SCHUELER = "schueler-verwalten"
FREMD = "fremd-verwalten"


@pytest.fixture(scope="module")
def sync_conn(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield conn
    conn.close()


def _node(cur, titel, *, owner, status="active", valid_until=None, read_scope="private"):
    nid = uuid.uuid4()
    cur.execute(
        "INSERT INTO context_nodes (id, category, content_type, title, owner_pseudonym,"
        " read_scope, write_scope, status, valid_until, metadata)"
        " VALUES (%s,'artifact','schuelertext',%s,%s,%s,'private',%s,%s,'{}')",
        (str(nid), titel, owner, read_scope, status, valid_until),
    )
    return nid


@pytest.fixture
def bestand(sync_conn):
    with sync_conn.cursor() as cur:
        ids = {
            "eigen": _node(cur, "Mein Text", owner=SCHUELER),
            "archiviert": _node(cur, "Alter Text", owner=SCHUELER, status="archived",
                                valid_until=date.today() - timedelta(days=5)),
            "fremd_privat": _node(cur, "Fremder Text", owner=FREMD),
            "fremd_offen": _node(cur, "Schulweit", owner=FREMD, read_scope="school"),
        }
    sync_conn.commit()
    yield ids
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        for nid in ids.values():
            cur.execute("DELETE FROM context_nodes WHERE id = %s", (str(nid),))
    sync_conn.commit()


@pytest.fixture
def schueler(jwt_service):
    token, _ = jwt_service.issue(pseudonym=SCHUELER, roles=["student"], grade="8")
    return {"Cookie": f"session={token}"}


# ── Detailansicht ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schuelerin_sieht_den_eigenen_baustein(test_client, schueler, bestand):
    """Der Zeilenklick aus „Meine Bausteine" — vorher 403."""
    resp = await test_client.get(f"/context/nodes/{bestand['eigen']}", headers=schueler)
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Mein Text"


@pytest.mark.asyncio
async def test_schuelerin_sieht_keinen_fremden_privaten(test_client, schueler, bestand):
    """`private` ist eigentümer-only — daran ändert die Öffnung nichts."""
    resp = await test_client.get(
        f"/context/nodes/{bestand['fremd_privat']}", headers=schueler
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_schuelerin_sieht_schulweites(test_client, schueler, bestand):
    """Dieselbe Menge, die die Suche ihr ohnehin liefert — das war die Unstimmigkeit."""
    resp = await test_client.get(
        f"/context/nodes/{bestand['fremd_offen']}", headers=schueler
    )
    assert resp.status_code == 200, resp.text


# ── Umbenennen ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_umbenennen(test_client, schueler, bestand):
    resp = await test_client.patch(
        f"/context/nodes/{bestand['eigen']}/verwalten",
        headers=schueler, json={"title": "Besserer Titel"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Besserer Titel"


@pytest.mark.asyncio
async def test_fremdes_umbenennen_scheitert(test_client, schueler, bestand):
    resp = await test_client.patch(
        f"/context/nodes/{bestand['fremd_offen']}/verwalten",
        headers=schueler, json={"title": "Gekapert"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_leerer_titel_wird_abgelehnt(test_client, schueler, bestand):
    resp = await test_client.patch(
        f"/context/nodes/{bestand['eigen']}/verwalten", headers=schueler, json={"title": ""}
    )
    assert resp.status_code == 422, resp.text


# ── Archivieren und zurück ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_archivieren_setzt_archived_at(test_client, schueler, sync_conn, bestand):
    """Ohne `archived_at` berechnet der Löschlauf nie eine Frist (ADR-013)."""
    resp = await test_client.patch(
        f"/context/nodes/{bestand['eigen']}/verwalten",
        headers=schueler, json={"status": "archived"},
    )
    assert resp.status_code == 200, resp.text

    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        cur.execute("SELECT status, archived_at FROM context_nodes WHERE id = %s",
                    (str(bestand["eigen"]),))
        status, archiviert_am = cur.fetchone()
    assert status == "archived"
    assert archiviert_am is not None


@pytest.mark.asyncio
async def test_reaktivieren_setzt_ein_neues_ablaufdatum(
    test_client, schueler, sync_conn, bestand
):
    """Sonst sammelte der nächtliche Lauf den Knoten in derselben Nacht wieder ein."""
    resp = await test_client.post(
        f"/context/nodes/{bestand['archiviert']}/reaktivieren", headers=schueler
    )
    assert resp.status_code == 200, resp.text
    daten = resp.json()
    assert daten["status"] == "active"
    if daten["valid_until"] is not None:
        assert date.fromisoformat(daten["valid_until"]) > date.today()


# ── Ablaufdatum ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ablauf_verlaengern(test_client, schueler, bestand):
    neu = date.today() + timedelta(days=200)
    resp = await test_client.patch(
        f"/context/nodes/{bestand['eigen']}/verwalten",
        headers=schueler,
        json={"valid_until": neu.isoformat(), "valid_until_gesetzt": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["valid_until"] == neu.isoformat()


@pytest.mark.asyncio
async def test_ablauf_entfernen_geht_ausdruecklich(test_client, schueler, sync_conn, bestand):
    """`null` heißt „gilt dauerhaft" — das braucht das Flag, sonst wäre es von
    „Feld weggelassen" nicht zu unterscheiden."""
    with sync_conn.cursor() as cur:
        cur.execute("UPDATE context_nodes SET valid_until = %s WHERE id = %s",
                    (date.today() + timedelta(days=3), str(bestand["eigen"])))
    sync_conn.commit()

    resp = await test_client.patch(
        f"/context/nodes/{bestand['eigen']}/verwalten",
        headers=schueler, json={"valid_until": None, "valid_until_gesetzt": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["valid_until"] is None


@pytest.mark.asyncio
async def test_ohne_flag_bleibt_das_datum_stehen(test_client, schueler, sync_conn, bestand):
    stichtag = date.today() + timedelta(days=3)
    with sync_conn.cursor() as cur:
        cur.execute("UPDATE context_nodes SET valid_until = %s WHERE id = %s",
                    (stichtag, str(bestand["eigen"])))
    sync_conn.commit()

    resp = await test_client.patch(
        f"/context/nodes/{bestand['eigen']}/verwalten",
        headers=schueler, json={"title": "Nur der Titel"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["valid_until"] == stichtag.isoformat()


# ── Der schmale Vertrag ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scopes_lassen_sich_hier_nicht_aendern(test_client, schueler, bestand):
    """Der Kern der Entscheidung: „Verwalten ist nicht Bearbeiten" (Leitprinzip 5).

    Ein durchgereichter `read_scope` veröffentlichte einen Text, den jemand für sich
    geschrieben hat. Pydantic ignoriert unbekannte Felder — geprüft wird deshalb die
    Wirkung, nicht die Ablehnung.
    """
    resp = await test_client.patch(
        f"/context/nodes/{bestand['eigen']}/verwalten",
        headers=schueler, json={"title": "X", "read_scope": "school"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["read_scope"] == "private", "Sichtbarkeit darf sich nicht ändern"


@pytest.mark.asyncio
async def test_generischer_patch_bleibt_lehrkraeften_vorbehalten(
    test_client, schueler, bestand
):
    resp = await test_client.patch(
        f"/context/nodes/{bestand['eigen']}", headers=schueler, json={"title": "X"}
    )
    assert resp.status_code == 403, resp.text


# ── Löschen ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_eigenes_loeschen(test_client, schueler, sync_conn, bestand):
    resp = await test_client.delete(
        f"/context/nodes/{bestand['eigen']}", headers=schueler
    )
    assert resp.status_code == 204, resp.text

    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM context_nodes WHERE id = %s",
                    (str(bestand["eigen"]),))
        assert cur.fetchone()[0] == 0


@pytest.mark.asyncio
async def test_fremdes_loeschen_scheitert(test_client, schueler, bestand):
    resp = await test_client.delete(
        f"/context/nodes/{bestand['fremd_offen']}", headers=schueler
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_force_bleibt_admins_vorbehalten(test_client, schueler, bestand):
    resp = await test_client.delete(
        f"/context/nodes/{bestand['eigen']}?force=true", headers=schueler
    )
    assert resp.status_code == 403, resp.text
    assert "Admins" in resp.json()["detail"]
