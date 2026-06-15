"""Integrationstests für die Unterrichtsplanungs-API (UP-Phase-1).

Router-Pfade ohne /api-Präfix (CLAUDE.md: FastAPI sieht /api nie).
"""

import psycopg2
import pytest
import pytest_asyncio
from uuid import uuid4

TEACHER1_PSEUDO = "teacher1-pseudo"
TEACHER2_PSEUDO = "teacher2-pseudo"
STUDENT_PSEUDO = "student1-pseudo"

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def seed_planning_fixtures(db_url, run_migrations):
    """Legt Subject, Gruppe und Mitgliedschaften für Planungstests an."""
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    with conn.cursor() as cur:
        # Subject
        cur.execute("""
            INSERT INTO subjects (id, slug, name, sort_order)
            VALUES (100, 'mathe-test', 'Mathematik Test', 0)
            ON CONFLICT (id) DO NOTHING
        """)
        # teaching_group
        cur.execute("""
            INSERT INTO groups (id, name, slug, type, subject_id)
            VALUES (100, '10a Mathe', '10a-mathe-test', 'teaching_group', 100)
            ON CONFLICT (id) DO NOTHING
        """)
        # teacher1 ist Lehrkraft der Gruppe
        cur.execute("""
            INSERT INTO group_memberships (group_id, pseudonym, role_in_group)
            VALUES (100, %s, 'teacher')
            ON CONFLICT DO NOTHING
        """, (TEACHER1_PSEUDO,))
        # student ist Schüler der Gruppe
        cur.execute("""
            INSERT INTO group_memberships (group_id, pseudonym, role_in_group)
            VALUES (100, %s, 'student')
            ON CONFLICT DO NOTHING
        """, (STUDENT_PSEUDO,))
    conn.commit()
    conn.close()


@pytest.fixture
def auth_student(jwt_service):
    token, _ = jwt_service.issue(pseudonym=STUDENT_PSEUDO, roles=["student"], grade=10)
    return {"Cookie": f"session={token}"}


@pytest.fixture
def auth_teacher2(jwt_service):
    token, _ = jwt_service.issue(pseudonym=TEACHER2_PSEUDO, roles=["teacher"], grade=None)
    return {"Cookie": f"session={token}"}


# ── Schritt 1: Wochenmuster + Generierung ──────────────────────────────────────


@pytest.mark.asyncio
async def test_pattern_setzen_und_generieren(
    test_client, auth_headers, seed_planning_fixtures
):
    # Wochenmuster für HJ1 setzen: Montag 3. Stunde
    resp = await test_client.put(
        "/planning/groups/100/pattern",
        json={"halbjahr": 1, "patterns": [{"weekday": 0, "start_period": 3, "periods": 1}]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    patterns = resp.json()
    assert len(patterns) == 1
    assert patterns[0]["weekday"] == 0

    # Slots generieren
    resp = await test_client.post(
        "/planning/groups/100/slots/generate",
        json={"halbjahr": 1, "regenerate": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["created"] > 0
    assert stats["halbjahr"] == 1

    # Overview abrufen
    resp = await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    assert resp.status_code == 200
    overview = resp.json()
    assert len(overview["slots"]) == stats["created"]
    assert overview["slots"][0]["kategorie"] == "unterricht"
    # Alle generierten Slots sind Montage (weekday 0)
    from datetime import date
    for slot in overview["slots"]:
        d = date.fromisoformat(slot["date"])
        assert d.weekday() == 0, f"Slot ist kein Montag: {d}"


@pytest.mark.asyncio
async def test_idempotenz_guard_409(test_client, auth_headers, seed_planning_fixtures):
    resp = await test_client.post(
        "/planning/groups/100/slots/generate",
        json={"halbjahr": 1, "regenerate": False},
        headers=auth_headers,
    )
    assert resp.status_code == 409


# ── Schritt 2: UE anlegen + Slots zuweisen + Bilanz ──────────────────────────


@pytest.mark.asyncio
async def test_ue_anlegen_slots_zuweisen_bilanz(
    test_client, auth_headers, seed_planning_fixtures
):
    # UE anlegen
    resp = await test_client.post(
        "/planning/groups/100/units",
        json={"titel": "Funktionen", "farbe": 2},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    ue = resp.json()
    ue_id = ue["id"]

    # Einen Slot holen
    ov = await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    slots = ov.json()["slots"]
    assert len(slots) > 0
    slot_id = slots[0]["id"]

    # Slot dem UE zuweisen
    resp = await test_client.patch(
        f"/planning/slots/{slot_id}",
        json={"ue_node_id": ue_id},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["ue_node_id"] == ue_id

    # Bilanz prüfen
    resp = await test_client.get("/planning/groups/100/balance", headers=auth_headers)
    assert resp.status_code == 200
    balance = resp.json()
    ue_item = next((i for i in balance["items"] if i["ue_node_id"] == ue_id), None)
    assert ue_item is not None
    assert ue_item["zugewiesen"] == 1


@pytest.mark.asyncio
async def test_bilanz_doppelstunde_zaehlt_zwei_stunden(
    test_client, auth_headers, seed_planning_fixtures
):
    """Ein Doppelstunden-Slot (periods=2) zählt in der Bilanz als 2 Einzelstunden,
    da Curriculum-Soll-Stunden Einzelstunden sind."""
    # Doppelstunden-Muster für HJ1 setzen und generieren
    resp = await test_client.put(
        "/planning/groups/100/pattern",
        json={"halbjahr": 1, "patterns": [{"weekday": 0, "start_period": 1, "periods": 2}]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    resp = await test_client.post(
        "/planning/groups/100/slots/generate",
        json={"halbjahr": 1, "regenerate": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # UE anlegen
    resp = await test_client.post(
        "/planning/groups/100/units",
        json={"titel": "Doppelstunden-UE", "farbe": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    ue_id = resp.json()["id"]

    # Zwei Doppelstunden-Slots dem UE zuweisen
    ov = await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    slots = [s for s in ov.json()["slots"] if s["periods"] == 2][:2]
    assert len(slots) == 2
    for slot in slots:
        resp = await test_client.patch(
            f"/planning/slots/{slot['id']}",
            json={"ue_node_id": ue_id},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    # Bilanz: 2 Doppelstunden = 4 Einzelstunden
    resp = await test_client.get("/planning/groups/100/balance", headers=auth_headers)
    assert resp.status_code == 200
    ue_item = next(
        (i for i in resp.json()["items"] if i["ue_node_id"] == ue_id), None
    )
    assert ue_item is not None
    assert ue_item["zugewiesen"] == 4


@pytest.mark.asyncio
async def test_overview_liefert_feiertage_und_unterrichtsfreie(
    test_client, auth_headers, seed_planning_fixtures
):
    """Overview gibt Feiertage und unterrichtsfreie Tage (mit Namen) aus der
    school_year.yaml zurück, damit das Frontend sie als Sondertag-Zeilen anzeigen kann."""
    resp = await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    # Schuljahresgrenzen werden mitgeliefert (Frontend begrenzt Sondertage daran,
    # nicht am Slot-Bereich, damit der letzte Schultag nicht verschwindet).
    assert data["beginn"] and data["ende"]
    assert isinstance(data["feiertage"], list)
    assert isinstance(data["unterrichtsfreie_tage"], list)
    # Jeder Eintrag hat datum + (optionalen) name
    for entry in data["feiertage"] + data["unterrichtsfreie_tage"]:
        assert "datum" in entry
        assert "name" in entry


@pytest.mark.asyncio
async def test_unit_bearbeiten(test_client, auth_headers, seed_planning_fixtures):
    """UE-Titel/Farbe lassen sich nachträglich korrigieren (Tippfehler-Fall)."""
    resp = await test_client.post(
        "/planning/groups/100/units",
        json={"titel": "Tippfehlre", "farbe": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    ue_id = resp.json()["id"]

    resp = await test_client.patch(
        f"/planning/groups/100/units/{ue_id}",
        json={"titel": "Funktionen", "farbe": 3},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Funktionen"
    assert data["metadata_"]["farbe"] == 3

    # Änderung ist persistiert
    units = (
        await test_client.get("/planning/groups/100/units", headers=auth_headers)
    ).json()
    assert any(u["id"] == ue_id and u["title"] == "Funktionen" for u in units)


@pytest.mark.asyncio
async def test_unit_bearbeiten_404_unbekannt(
    test_client, auth_headers, seed_planning_fixtures
):
    resp = await test_client.patch(
        "/planning/groups/100/units/00000000-0000-0000-0000-000000000000",
        json={"titel": "X"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unit_loeschen_gibt_slots_frei(
    test_client, auth_headers, seed_planning_fixtures
):
    """UE löschen: 204, UE verschwindet, zugewiesene Slots werden freigegeben."""
    await test_client.put(
        "/planning/groups/100/pattern",
        json={"halbjahr": 1, "patterns": [{"weekday": 0, "start_period": 3, "periods": 1}]},
        headers=auth_headers,
    )
    await test_client.post(
        "/planning/groups/100/slots/generate",
        json={"halbjahr": 1, "regenerate": True},
        headers=auth_headers,
    )
    ue_id = (
        await test_client.post(
            "/planning/groups/100/units",
            json={"titel": "Wird gelöscht", "farbe": 0},
            headers=auth_headers,
        )
    ).json()["id"]

    slots = (
        await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    ).json()["slots"]
    slot_id = slots[0]["id"]
    await test_client.patch(
        f"/planning/slots/{slot_id}", json={"ue_node_id": ue_id}, headers=auth_headers
    )

    resp = await test_client.delete(
        f"/planning/groups/100/units/{ue_id}", headers=auth_headers
    )
    assert resp.status_code == 204

    overview = (
        await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    ).json()
    assert all(u["id"] != ue_id for u in overview["units"])
    freed = next(s for s in overview["slots"] if s["id"] == slot_id)
    assert freed["ue_node_id"] is None


# ── Schritt 3: PATCH Kategorie → Auto-Snapshot → Restore ─────────────────────


@pytest.mark.asyncio
async def test_patch_kategorie_auto_snapshot_restore(
    test_client, auth_headers, seed_planning_fixtures
):
    ov = await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    slots = ov.json()["slots"]
    assert len(slots) > 0
    slot_id = slots[0]["id"]

    # Snapshots vor PATCH zählen
    snaps_before = await test_client.get(
        "/planning/groups/100/snapshots", headers=auth_headers
    )
    count_before = len(snaps_before.json())

    # Kategorie ändern → löst Auto-Snapshot aus
    resp = await test_client.patch(
        f"/planning/slots/{slot_id}",
        json={"kategorie": "ausfall"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["kategorie"] == "ausfall"

    # Snapshot wurde angelegt
    snaps_after = await test_client.get(
        "/planning/groups/100/snapshots", headers=auth_headers
    )
    assert len(snaps_after.json()) == count_before + 1
    snapshot_id = snaps_after.json()[0]["id"]

    # Restore
    resp = await test_client.post(
        f"/planning/snapshots/{snapshot_id}/restore",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["restored"] is True

    # Slot-Kategorie wieder "unterricht"
    ov2 = await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    restored_slot = next(s for s in ov2.json()["slots"] if s["id"] == slot_id)
    assert restored_slot["kategorie"] == "unterricht"


# ── Schritt 4: Swap zweier Slots ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_swap_slots(test_client, auth_headers, seed_planning_fixtures):
    ov = await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    slots = ov.json()["slots"]
    assert len(slots) >= 2

    slot_a_id = slots[0]["id"]
    slot_b_id = slots[1]["id"]

    # Thema an Slot A setzen
    await test_client.patch(
        f"/planning/slots/{slot_a_id}",
        json={"thema": "Slot-A-Thema"},
        headers=auth_headers,
    )

    snaps_before = len((await test_client.get(
        "/planning/groups/100/snapshots", headers=auth_headers
    )).json())

    resp = await test_client.post(
        "/planning/groups/100/slots/swap",
        json={"slot_a_id": slot_a_id, "slot_b_id": slot_b_id},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    result = resp.json()
    # Thema ist jetzt bei Slot B
    slot_a_after = next(s for s in result if s["id"] == slot_a_id)
    slot_b_after = next(s for s in result if s["id"] == slot_b_id)
    assert slot_a_after["thema"] is None
    assert slot_b_after["thema"] == "Slot-A-Thema"

    # Swap löst Snapshot aus
    snaps_after = len((await test_client.get(
        "/planning/groups/100/snapshots", headers=auth_headers
    )).json())
    assert snaps_after == snaps_before + 1


# ── Schritt 5: Berechtigungsprüfung ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_fachfremde_lehrkraft_403(
    test_client, auth_teacher2, seed_planning_fixtures
):
    resp = await test_client.get(
        "/planning/groups/100/overview", headers=auth_teacher2
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_schueler_403(test_client, auth_student, seed_planning_fixtures):
    resp = await test_client.get(
        "/planning/groups/100/overview", headers=auth_student
    )
    assert resp.status_code == 403


# ── Schritt 6: HJ2-Regenerierung lässt HJ1 unberührt ────────────────────────


@pytest.mark.asyncio
async def test_hj2_regenerierung_hj1_unveraendert(
    test_client, auth_headers, seed_planning_fixtures
):
    # HJ2-Muster setzen (Dienstag)
    await test_client.put(
        "/planning/groups/100/pattern",
        json={"halbjahr": 2, "patterns": [{"weekday": 1, "start_period": 1, "periods": 1}]},
        headers=auth_headers,
    )

    # HJ2 generieren
    resp = await test_client.post(
        "/planning/groups/100/slots/generate",
        json={"halbjahr": 2, "regenerate": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    hj2_count = resp.json()["created"]

    # HJ1-Slots zählen
    ov_before = await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    hj1_slots_before = [s for s in ov_before.json()["slots"] if s["halbjahr"] == 1]

    # HJ2 regenerieren
    resp = await test_client.post(
        "/planning/groups/100/slots/generate",
        json={"halbjahr": 2, "regenerate": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # HJ1 muss unverändert sein
    ov_after = await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    hj1_slots_after = [s for s in ov_after.json()["slots"] if s["halbjahr"] == 1]
    assert len(hj1_slots_before) == len(hj1_slots_after)

    # Snapshot der Regenerierung vorhanden
    snaps = await test_client.get("/planning/groups/100/snapshots", headers=auth_headers)
    reasons = [s["reason"] for s in snaps.json()]
    assert "regeneration" in reasons


# ── UP-Phase-3a: Curriculum-Kapitel-Endpoint ──────────────────────────────────


@pytest.mark.asyncio
async def test_curriculum_chapters_endpoint_lehrkraft(
    test_client, auth_headers, seed_planning_fixtures
):
    """Lehrkraft der Gruppe erhält 200 mit der erwarteten Struktur.

    Gruppe 100 hat keinen Klassenbezug → grade_unbekannt; ohne Curriculum für das
    Fach ist die Liste leer, der Endpoint liefert trotzdem 200.
    """
    resp = await test_client.get(
        "/planning/groups/100/curriculum-chapters", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "curricula" in body
    assert "grade_unbekannt" in body
    assert isinstance(body["curricula"], list)


@pytest.mark.asyncio
async def test_curriculum_chapters_endpoint_fremde_lehrkraft_403(
    test_client, auth_teacher2, seed_planning_fixtures
):
    """Lehrkraft ohne Mitgliedschaft in der Gruppe erhält 403."""
    resp = await test_client.get(
        "/planning/groups/100/curriculum-chapters", headers=auth_teacher2
    )
    assert resp.status_code == 403
