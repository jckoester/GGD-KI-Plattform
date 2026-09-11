"""Passen Scope und Trägergruppe zusammen? — Prüfung beim Anlegen und Ändern.

Zwei Regeln, beide bis 09/2026 lückenhaft:

1. **Pflicht** — `subject`/`group` verlangen eine Gruppe. Beim Anlegen wurde das
   geprüft, beim **Ändern** nicht: Dort schlug der DB-CHECK als IntegrityError
   durch, also als 500 ohne Hinweis.
2. **Art** — `subject` meint die Fachschaft. Geprüft hat das niemand, und beide
   Formulare boten unter „Fachgruppe" nur Unterrichtsgruppen an. Die falsche Wahl
   wurde stumm gespeichert.

Router-Pfade ohne /api-Präfix (CLAUDE.md: FastAPI sieht /api nie).
"""
import uuid

import psycopg2
import pytest

SUBJECT_ID = 630
FACHSCHAFT_ID = 631
UNTERRICHT_ID = 632


@pytest.fixture(scope="module")
def sync_conn(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def gruppen(sync_conn):
    """Eine Fachschaft und eine Unterrichtsgruppe zum selben Fach."""
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO subjects (id, slug, name, sort_order) "
            "VALUES (%s,'sg-fach','Scope-Fach',1) ON CONFLICT (id) DO NOTHING",
            (SUBJECT_ID,),
        )
        cur.execute(
            "INSERT INTO groups (id, name, slug, type, subject_id) VALUES "
            "(%s,'Fachschaft Scope','sg-fs','subject_department',%s), "
            "(%s,'9z Scope','sg-ug','teaching_group',%s) "
            "ON CONFLICT (id) DO NOTHING",
            (FACHSCHAFT_ID, SUBJECT_ID, UNTERRICHT_ID, SUBJECT_ID),
        )
    sync_conn.commit()
    yield
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        cur.execute("DELETE FROM groups WHERE id IN (%s,%s)", (FACHSCHAFT_ID, UNTERRICHT_ID))
        cur.execute("DELETE FROM subjects WHERE id = %s", (SUBJECT_ID,))
    sync_conn.commit()


def _payload(**abweichend):
    basis = {
        "category": "document",
        "content_type": "konvention",
        "title": f"Scope-Probe {uuid.uuid4().hex[:8]}",
        "content": "Inhalt",
        "read_scope": "school",
        "write_scope": "private",
    }
    return {**basis, **abweichend}


@pytest.fixture
def aufraeumen(sync_conn):
    ids = []
    yield ids
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        for nid in ids:
            cur.execute("DELETE FROM context_nodes WHERE id = %s", (str(nid),))
    sync_conn.commit()


# ── Anlegen ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subject_mit_fachschaft_geht(test_client, auth_headers, gruppen, aufraeumen):
    resp = await test_client.post("/context/nodes", headers=auth_headers, json=_payload(
        read_scope="school", write_scope="subject", write_scope_group_id=FACHSCHAFT_ID,
    ))
    assert resp.status_code == 201, resp.text
    aufraeumen.append(resp.json()["id"])


@pytest.mark.asyncio
async def test_subject_mit_unterrichtsgruppe_wird_abgelehnt(
    test_client, auth_headers, gruppen
):
    """Der eigentliche Fehler: Beide Formulare boten hier Unterrichtsgruppen an."""
    resp = await test_client.post("/context/nodes", headers=auth_headers, json=_payload(
        read_scope="school", write_scope="subject", write_scope_group_id=UNTERRICHT_ID,
    ))
    assert resp.status_code == 422, resp.text
    assert "Fachschaft" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_group_mit_fachschaft_wird_abgelehnt(test_client, auth_headers, gruppen):
    """Die Gegenrichtung — sonst prüfte die Regel nur die Hälfte."""
    resp = await test_client.post("/context/nodes", headers=auth_headers, json=_payload(
        read_scope="group", read_scope_group_id=FACHSCHAFT_ID,
        write_scope="private",
    ))
    assert resp.status_code == 422, resp.text
    assert "read_scope" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_fehlende_gruppe_wird_abgelehnt(test_client, auth_headers, gruppen):
    resp = await test_client.post("/context/nodes", headers=auth_headers, json=_payload(
        read_scope="school", write_scope="subject",
    ))
    assert resp.status_code == 422, resp.text
    assert "muss die zuständige Gruppe" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_unbekannte_gruppe_wird_abgelehnt(test_client, auth_headers, gruppen):
    resp = await test_client.post("/context/nodes", headers=auth_headers, json=_payload(
        read_scope="school", write_scope="subject", write_scope_group_id=999_999,
    ))
    assert resp.status_code == 422, resp.text


# ── Ändern ───────────────────────────────────────────────────────────────────

@pytest.fixture
async def knoten(test_client, auth_headers, gruppen, aufraeumen):
    resp = await test_client.post("/context/nodes", headers=auth_headers, json=_payload())
    assert resp.status_code == 201, resp.text
    nid = resp.json()["id"]
    aufraeumen.append(nid)
    return nid


@pytest.mark.asyncio
async def test_aendern_auf_subject_ohne_gruppe_gibt_422_statt_500(
    test_client, auth_headers, knoten
):
    """⚠️ Der Fall, der bisher als IntegrityError durchschlug.

    Beim Anlegen war die Pflicht geprüft, beim Ändern nicht — die Oberfläche bekam
    einen 500 ohne Hinweis, was fehlt.
    """
    resp = await test_client.patch(
        f"/context/nodes/{knoten}", headers=auth_headers, json={"write_scope": "subject"}
    )
    assert resp.status_code == 422, resp.text
    assert "muss die zuständige Gruppe" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_aendern_auf_subject_mit_falscher_gruppenart(
    test_client, auth_headers, knoten
):
    resp = await test_client.patch(
        f"/context/nodes/{knoten}",
        headers=auth_headers,
        json={"write_scope": "subject", "write_scope_group_id": UNTERRICHT_ID},
    )
    assert resp.status_code == 422, resp.text
    assert "Fachschaft" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_aendern_auf_subject_mit_fachschaft_geht(
    test_client, auth_headers, knoten
):
    resp = await test_client.patch(
        f"/context/nodes/{knoten}",
        headers=auth_headers,
        json={"write_scope": "subject", "write_scope_group_id": FACHSCHAFT_ID},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_teiländerung_prueft_den_stand_danach(
    test_client, auth_headers, knoten
):
    """Wer nur den Scope schickt, behält die bisherige Gruppe — die Prüfung muss
    also die Paarung *nach* der Änderung betrachten, nicht die mitgeschickte."""
    # Erst gültig auf Fachschaft setzen …
    resp = await test_client.patch(
        f"/context/nodes/{knoten}",
        headers=auth_headers,
        json={"write_scope": "subject", "write_scope_group_id": FACHSCHAFT_ID},
    )
    assert resp.status_code == 200, resp.text

    # … dann allein den Scope auf `group` drehen. Die Fachschaft bleibt stehen und
    # passt nun nicht mehr.
    resp = await test_client.patch(
        f"/context/nodes/{knoten}", headers=auth_headers, json={"write_scope": "group"}
    )
    assert resp.status_code == 422, resp.text
    assert "Fachschaft" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_aenderung_ohne_scope_bleibt_unberuehrt(test_client, auth_headers, knoten):
    """Eine reine Titeländerung darf nicht an der Scope-Prüfung scheitern."""
    resp = await test_client.patch(
        f"/context/nodes/{knoten}", headers=auth_headers, json={"title": "Neuer Titel"}
    )
    assert resp.status_code == 200, resp.text
