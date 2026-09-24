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
            INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft)
            VALUES (100, %s, 'teacher', 'eigen')
            ON CONFLICT DO NOTHING
        """, (TEACHER1_PSEUDO,))
        # student ist Schüler der Gruppe
        cur.execute("""
            INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft)
            VALUES (100, %s, 'student', 'geerbt')
            ON CONFLICT DO NOTHING
        """, (STUDENT_PSEUDO,))
    conn.commit()
    conn.close()


@pytest.fixture
def auth_student(jwt_service):
    token, _ = jwt_service.issue(pseudonym=STUDENT_PSEUDO, roles=["student"], grade="10")
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
async def test_vierzehntaegige_muster_teilen_die_woechentlichen_termine(
    test_client, auth_headers, seed_planning_fixtures
):
    """A- und B-Woche zusammen ergeben genau die wöchentlichen Termine — keinen mehr, keinen
    weniger, und keinen doppelt.

    Bis zum 14.09.2026 las der Generator `rhythmus` gar nicht: Alle drei Läufe ergaben
    dieselben Termine, ein 14-tägiger Kurs bekam doppelt so viele Stunden wie er hat.

    Die Zusage wird als Eigenschaft geprüft, nicht gegen feste Datumswerte — sonst hinge
    der Test an der `school_year.yaml` der Entwicklungsumgebung.
    """
    from datetime import date

    async def termine(rhythmus: str) -> list[date]:
        resp = await test_client.put(
            "/planning/groups/100/pattern",
            json={
                "halbjahr": 1,
                "patterns": [
                    {"weekday": 0, "start_period": 3, "periods": 1, "rhythmus": rhythmus}
                ],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        resp = await test_client.post(
            "/planning/groups/100/slots/generate",
            json={"halbjahr": 1, "regenerate": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        resp = await test_client.get("/planning/groups/100/overview", headers=auth_headers)
        assert resp.status_code == 200
        return sorted(date.fromisoformat(s["date"]) for s in resp.json()["slots"])

    woechentlich = await termine("woechentlich")
    a_wochen = await termine("a_woche")
    b_wochen = await termine("b_woche")

    assert a_wochen and b_wochen, "sonst prüft der Test nichts"
    assert not set(a_wochen) & set(b_wochen)
    assert sorted(a_wochen + b_wochen) == woechentlich


@pytest.mark.asyncio
async def test_ab_wochen_stimmen_mit_den_erzeugten_slots_ueberein(
    test_client, auth_headers, seed_planning_fixtures
):
    """Der Editor zeigt Termine an, der Generator legt sie an — beide müssen dasselbe sagen.

    Sonst wäre die Anzeige das Gegenteil dessen, wofür sie da ist: Eine Lehrkraft, die
    „findet statt am 15.06." liest und dann keinen Slot am 15.06. vorfindet, korrigiert das
    Auswahlfeld — und verschiebt die Phase erst dadurch.
    """
    from datetime import date

    resp = await test_client.get("/planning/ab-wochen?halbjahr=1", headers=auth_headers)
    assert resp.status_code == 200
    kalender = resp.json()
    a_tage = {date.fromisoformat(d) for d in kalender["a_woche"]}
    b_tage = {date.fromisoformat(d) for d in kalender["b_woche"]}
    assert a_tage and b_tage
    assert not a_tage & b_tage

    await test_client.put(
        "/planning/groups/100/pattern",
        json={
            "halbjahr": 1,
            "patterns": [
                {"weekday": 0, "start_period": 3, "periods": 1, "rhythmus": "a_woche"}
            ],
        },
        headers=auth_headers,
    )
    resp = await test_client.post(
        "/planning/groups/100/slots/generate",
        json={"halbjahr": 1, "regenerate": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    resp = await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    erzeugt = {date.fromisoformat(s["date"]) for s in resp.json()["slots"]}

    assert erzeugt == {t for t in a_tage if t.weekday() == 0}


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


@pytest.mark.asyncio
async def test_ausfall_zaehlt_nicht_zur_ue(
    test_client, auth_headers, seed_planning_fixtures
):
    """Eine auf Ausfall gesetzte Stunde zählt nicht mehr zum Ist der UE."""
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
            json={"titel": "Funktionen", "farbe": 0},
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

    bal = (
        await test_client.get("/planning/groups/100/balance", headers=auth_headers)
    ).json()
    item = next(i for i in bal["items"] if i["ue_node_id"] == ue_id)
    assert item["zugewiesen"] == 1

    # Stunde auf Ausfall setzen → zählt nicht mehr
    await test_client.patch(
        f"/planning/slots/{slot_id}", json={"kategorie": "ausfall"}, headers=auth_headers
    )
    bal = (
        await test_client.get("/planning/groups/100/balance", headers=auth_headers)
    ).json()
    item = next(i for i in bal["items"] if i["ue_node_id"] == ue_id)
    assert item["zugewiesen"] == 0


@pytest.mark.asyncio
async def test_lesson_anlegen_verknuepft_slot(
    test_client, auth_headers, seed_planning_fixtures
):
    """Stunde mit slot_id anlegen → der Slot trägt danach stunde_node_id (Overview)."""
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
            json={"titel": "Funktionen", "farbe": 0},
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

    resp = await test_client.post(
        f"/planning/units/{ue_id}/lessons",
        json={"titel": "Stunde 1", "slot_id": slot_id},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    lesson_id = resp.json()["id"]

    # Overview neu laden → der Slot muss die Stunde verknüpft führen
    overview = (
        await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    ).json()
    slot = next(s for s in overview["slots"] if s["id"] == slot_id)
    assert slot["stunde_node_id"] == lesson_id


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


# ── Schritt 4/8: sozialform-Round-Trip + Aliassuche ──────────────────────────


@pytest.mark.asyncio
async def test_lesson_sozialform_roundtrip(
    test_client, auth_headers, seed_planning_fixtures
):
    """PATCH einer Stunde mit sozialform → GET liefert sie unverändert zurück."""
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
            json={"titel": "Sozialform-UE", "farbe": 0},
            headers=auth_headers,
        )
    ).json()["id"]
    slot_id = (
        await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    ).json()["slots"][0]["id"]
    await test_client.patch(
        f"/planning/slots/{slot_id}", json={"ue_node_id": ue_id}, headers=auth_headers
    )
    lesson_id = (
        await test_client.post(
            f"/planning/units/{ue_id}/lessons",
            json={"titel": "Stunde S", "slot_id": slot_id},
            headers=auth_headers,
        )
    ).json()["id"]

    resp = await test_client.patch(
        f"/planning/lessons/{lesson_id}",
        json={
            "phasen": [
                {
                    "id": "p1",
                    "name": "Erarbeitung",
                    "dauer_min": 20,
                    "prio": "kern",
                    "sozialform": {"typ": "text", "wert": "Gruppenarbeit"},
                    "methode": {"typ": "text", "wert": "Gruppenpuzzle"},
                }
            ]
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    lesson = (
        await test_client.get(f"/planning/lessons/{lesson_id}", headers=auth_headers)
    ).json()
    phase = lesson["phasen"][0]
    assert phase["sozialform"]["typ"] == "text"
    assert phase["sozialform"]["wert"] == "Gruppenarbeit"
    assert phase["methode"]["wert"] == "Gruppenpuzzle"


@pytest.mark.asyncio
async def test_context_nodes_aliassuche(test_client, auth_headers):
    """GET /context/nodes?q=<alias> findet den Knoten über metadata.aliase."""
    create = await test_client.post(
        "/context/nodes",
        json={
            "category": "knowledge",
            "content_type": "methode",
            "title": "Think-Pair-Share AliasTest",
            # Pflichtfeld seit AP5 — ohne Beschreibung wäre der Vektor der Titel.
            "content": "Erst allein, dann zu zweit, dann in der Klasse.",
            "read_scope": "school",
            "metadata": {"aliase": ["Ich-Du-Wir XYZ"]},
        },
        headers=auth_headers,
    )
    assert create.status_code == 201
    node_id = create.json()["id"]

    # Treffer über Alias
    by_alias = (
        await test_client.get(
            "/context/nodes", params={"q": "Ich-Du-Wir XYZ"}, headers=auth_headers
        )
    ).json()
    assert any(n["id"] == node_id for n in by_alias)

    # Treffer über Titel
    by_title = (
        await test_client.get(
            "/context/nodes", params={"q": "AliasTest"}, headers=auth_headers
        )
    ).json()
    assert any(n["id"] == node_id for n in by_title)

    # Kein Treffer bei nicht vorkommendem Begriff
    none = (
        await test_client.get(
            "/context/nodes", params={"q": "ZZZ-nicht-vorhanden-QQQ"}, headers=auth_headers
        )
    ).json()
    assert all(n["id"] != node_id for n in none)


@pytest.mark.asyncio
async def test_context_nodes_subject_id_or_global(
    test_client, auth_headers, seed_planning_fixtures
):
    """subject_id_or_global liefert fach­unabhängige (NULL) + Fach-Knoten, keine fremden."""
    generic = (
        await test_client.post(
            "/context/nodes",
            json={
                "category": "knowledge",
                "content_type": "methode",
                "title": "Vokab-Generisch-XYZ",
                "content": "Fachübergreifender Eintrag für den Test.",
                "read_scope": "school",
            },
            headers=auth_headers,
        )
    ).json()["id"]
    fach = (
        await test_client.post(
            "/context/nodes",
            json={
                "category": "knowledge",
                "content_type": "methode",
                "title": "Vokab-Fach100-XYZ",
                "content": "Fachgebundener Eintrag für den Test.",
                "read_scope": "school",
                "subject_id": 100,
            },
            headers=auth_headers,
        )
    ).json()["id"]

    # Fach 100: generisch + Fach-100 enthalten
    res100 = (
        await test_client.get(
            "/context/nodes",
            params={"content_type": "methode", "subject_id_or_global": 100},
            headers=auth_headers,
        )
    ).json()
    ids100 = {n["id"] for n in res100}
    assert generic in ids100 and fach in ids100

    # Fremdes Fach: generisch enthalten, Fach-100 NICHT
    res_other = (
        await test_client.get(
            "/context/nodes",
            params={"content_type": "methode", "subject_id_or_global": 99999},
            headers=auth_headers,
        )
    ).json()
    ids_other = {n["id"] for n in res_other}
    assert generic in ids_other and fach not in ids_other


# ── Entwurfsstand in der Jahresplanung (11.09.2026) ──────────────────────────
#
# Ein angelegter, aber leerer Stundenentwurf sah in der Jahresplanung genauso aus wie
# ein ausgearbeiteter: Thema fett, verlinkt, anklickbar. `hat_phasen` macht den
# Unterschied sichtbar; die Beschriftung leitet das Frontend daraus ab
# (`entwurfsStand` in `lib/planner.js`).


@pytest.mark.asyncio
async def test_hat_phasen_unterscheidet_idee_von_entwurf(
    test_client, auth_headers, seed_planning_fixtures
):
    # Eine eigene UE, damit der Test nicht an den Stunden der übrigen Tests hängt.
    ue = (
        await test_client.post(
            "/planning/groups/100/units",
            json={"titel": "Entwurfsstand-Test", "farbe": 3},
            headers=auth_headers,
        )
    ).json()

    # ⚠️ Nur Slots **ohne** Entwurf nehmen. Die Fixtures dieses Moduls haben
    # `scope="module"`, frühere Tests hängen also schon Stunden an die vorderen
    # Slots — `slots[0]` war prompt belegt.
    ov = await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    frei = [s for s in ov.json()["slots"] if s["stunde_node_id"] is None]
    assert len(frei) >= 3, "zu wenige freie Slots für den Test"
    ohne_entwurf, fuer_idee, fuer_entwurf = frei[0], frei[1], frei[2]

    # Zwei Stundenentwürfe anlegen — beide zunächst ohne Phasen.
    stunde_idee = (
        await test_client.post(
            f"/planning/units/{ue['id']}/lessons",
            json={"titel": "Nur eine Idee", "slot_id": fuer_idee["id"]},
            headers=auth_headers,
        )
    ).json()
    stunde_entwurf = (
        await test_client.post(
            f"/planning/units/{ue['id']}/lessons",
            json={"titel": "Ausgearbeitet", "slot_id": fuer_entwurf["id"]},
            headers=auth_headers,
        )
    ).json()

    # Nur einer bekommt Phasen.
    resp = await test_client.patch(
        f"/planning/lessons/{stunde_entwurf['id']}",
        json={"phasen": [{"name": "Erarbeitung", "dauer_min": 30, "prio": "kern"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    stand = {
        s["id"]: s
        for s in (
            await test_client.get(
                "/planning/groups/100/overview", headers=auth_headers
            )
        ).json()["slots"]
    }

    # Ohne Entwurf: kein Knoten, keine Phasen.
    assert stand[ohne_entwurf["id"]]["stunde_node_id"] is None
    assert stand[ohne_entwurf["id"]]["hat_phasen"] is False

    # ⚠️ Der Kern: Beide haben einen Entwurf — nur einer ist ausgearbeitet.
    assert stand[fuer_idee["id"]]["stunde_node_id"] == stunde_idee["id"]
    assert stand[fuer_idee["id"]]["hat_phasen"] is False

    assert stand[fuer_entwurf["id"]]["stunde_node_id"] == stunde_entwurf["id"]
    assert stand[fuer_entwurf["id"]]["hat_phasen"] is True


@pytest.mark.asyncio
async def test_geleerte_phasen_fallen_auf_idee_zurueck(
    test_client, auth_headers, seed_planning_fixtures
):
    """Wer alle Phasen löscht, hat wieder eine Idee — nicht weiter einen Entwurf.

    Der Rückweg ist der unangenehmere Fall: Ein einmal gesetztes `hat_phasen`, das
    hängen bliebe, behauptete Arbeit, die es nicht mehr gibt.
    """
    ue = (
        await test_client.post(
            "/planning/groups/100/units",
            json={"titel": "Rueckweg-Test", "farbe": 4},
            headers=auth_headers,
        )
    ).json()
    slots = (
        await test_client.get("/planning/groups/100/overview", headers=auth_headers)
    ).json()["slots"]
    frei = [s for s in slots if s["stunde_node_id"] is None]
    assert frei, "kein freier Slot für den Test"
    ziel = frei[-1]

    stunde = (
        await test_client.post(
            f"/planning/units/{ue['id']}/lessons",
            json={"titel": "Hin und zurück", "slot_id": ziel["id"]},
            headers=auth_headers,
        )
    ).json()

    async def hat_phasen() -> bool:
        daten = (
            await test_client.get(
                "/planning/groups/100/overview", headers=auth_headers
            )
        ).json()["slots"]
        return next(s for s in daten if s["id"] == ziel["id"])["hat_phasen"]

    assert await hat_phasen() is False

    await test_client.patch(
        f"/planning/lessons/{stunde['id']}",
        json={"phasen": [{"name": "Einstieg", "dauer_min": 10, "prio": "kern"}]},
        headers=auth_headers,
    )
    assert await hat_phasen() is True

    await test_client.patch(
        f"/planning/lessons/{stunde['id']}",
        json={"phasen": []},
        headers=auth_headers,
    )
    assert await hat_phasen() is False


# ── GET /planning/mein-tag (Startseite, AP2) ──────────────────────────────────


@pytest.mark.asyncio
async def test_mein_tag_zeigt_nur_eigene_gruppen(
    test_client, auth_headers, auth_teacher2, seed_planning_fixtures, db_url
):
    """⚠️ **Der Mitgliedschaftsfilter ist die Zugriffsregel.**

    Fällt er weg, stehen die Stunden fremder Kolleg:innen auf der eigenen Startseite —
    mit Thema und Unterrichtseinheit. Das ist kein Anzeigefehler, sondern ein
    Zugriffsfehler, und er fiele niemandem auf, der die andere Gruppe nicht kennt.
    """
    from datetime import date

    heute = date.today()
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        # Zweite Gruppe, die teacher1 **nicht** gehört.
        cur.execute("""
            INSERT INTO groups (id, name, slug, type, subject_id)
            VALUES (101, 'Fremde Gruppe', 'fremde-gruppe-test', 'teaching_group', 100)
            ON CONFLICT (id) DO NOTHING
        """)
        cur.execute("""
            INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft)
            VALUES (101, %s, 'teacher', 'eigen') ON CONFLICT DO NOTHING
        """, (TEACHER2_PSEUDO,))
        for gid, thema in ((100, "Eigenes Thema"), (101, "Fremdes Thema")):
            cur.execute("""
                INSERT INTO lesson_slots
                    (id, group_id, date, start_period, periods, halbjahr, kategorie, thema)
                VALUES (%s, %s, %s, 2, 1, 1, 'unterricht', %s)
            """, (str(uuid4()), gid, heute, thema))
    conn.commit()

    try:
        resp = await test_client.get("/planning/mein-tag", headers=auth_headers)
        assert resp.status_code == 200
        themen = [s["thema"] for s in resp.json()["heute"]["stunden"]]
        assert "Eigenes Thema" in themen
        assert "Fremdes Thema" not in themen, (
            "Die Stunde einer fremden Gruppe steht auf der eigenen Startseite."
        )

        # Gegenprobe aus der anderen Richtung: teacher2 sieht seine, nicht meine.
        resp2 = await test_client.get("/planning/mein-tag", headers=auth_teacher2)
        themen2 = [s["thema"] for s in resp2.json()["heute"]["stunden"]]
        assert themen2 == ["Fremdes Thema"]
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lesson_slots WHERE group_id IN (100, 101) AND date = %s",
                        (heute,))
            cur.execute("DELETE FROM group_memberships WHERE group_id = 101")
            cur.execute("DELETE FROM groups WHERE id = 101")
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_mein_tag_liefert_stundenbezeichnung_statt_uhrzeit(
    test_client, auth_headers, seed_planning_fixtures, db_url
):
    """Uhrzeiten gibt es im System nicht — die Stundennummer schon."""
    from datetime import date

    heute = date.today()
    slot_id = str(uuid4())
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO lesson_slots
                (id, group_id, date, start_period, periods, halbjahr, kategorie)
            VALUES (%s, 100, %s, 3, 2, 1, 'unterricht')
        """, (slot_id, heute))
    conn.commit()
    try:
        resp = await test_client.get("/planning/mein-tag", headers=auth_headers)
        # ⚠️ **Die eigene Stunde suchen, nicht `stunden[0]` nehmen.** Andere Tests des
        # Laufs legen für dieselbe Gruppe Slots an; welche zuerst steht, hängt dann von
        # der Testreihenfolge ab. Der erste Entwurf dieses Tests lief allein grün und im
        # Gesamtlauf rot.
        stunden = resp.json()["heute"]["stunden"]
        stunde = next(s for s in stunden if s["slot_id"].replace("-", "")
                      == slot_id.replace("-", ""))
        # Ohne das Wort „Stunde“ — in einer Tagesliste steht es in jeder Zeile.
        assert stunde["stunde"] == "3.–4."
        assert "uhrzeit" not in stunde
    finally:
        with conn.cursor() as cur:
            # Nur die eigene Zeile — fremde Slots dieses Tages gehören anderen Tests.
            cur.execute("DELETE FROM lesson_slots WHERE id = %s", (slot_id,))
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_mein_tag_liefert_die_id_des_entwurfs(
    test_client, auth_headers, seed_planning_fixtures, db_url
):
    """⚠️ **`hat_entwurf` allein macht keinen Link.**

    Die Startseite verlinkt den Stundentitel in den Entwurf. Dafür braucht sie dessen
    **Id**, nicht nur die Auskunft, dass es einen gibt. Fehlt `stunde_node_id` in der
    Antwort, rendert der Titel klaglos als reiner Text — kein Fehler, keine Warnung,
    nur eine Funktion, die es nicht gibt.

    Genau das ist am 24.09.2026 passiert und durch zwei Prüfungen gefallen: Der
    Unit-Test reichte die Id **selbst** in `stundenLink()` hinein und prüfte damit die
    Funktion statt des Datenwegs; der Quelltext-Wächter sah `href={zumEntwurf}` im
    Markup und fragte nicht, ob `zumEntwurf` je einen Wert annimmt. Dieser Test prüft
    das eine, was beide nicht prüften: **dass die Id über die API ankommt.**
    """
    from datetime import date

    heute = date.today()
    slot_id = str(uuid4())
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO lesson_slots
                (id, group_id, date, start_period, periods, halbjahr, kategorie)
            VALUES (%s, 100, %s, 5, 1, 1, 'unterricht')
        """, (slot_id, heute))
    conn.commit()
    try:
        ue_id = (
            await test_client.post(
                "/planning/groups/100/units",
                json={"titel": "Einheit mit Entwurf", "farbe": 0},
                headers=auth_headers,
            )
        ).json()["id"]
        await test_client.patch(
            f"/planning/slots/{slot_id}", json={"ue_node_id": ue_id}, headers=auth_headers
        )
        lesson_id = (
            await test_client.post(
                f"/planning/units/{ue_id}/lessons",
                json={"titel": "Entwurf zur Stunde", "slot_id": slot_id},
                headers=auth_headers,
            )
        ).json()["id"]

        resp = await test_client.get("/planning/mein-tag", headers=auth_headers)
        assert resp.status_code == 200
        stunden = resp.json()["heute"]["stunden"]
        stunde = next(s for s in stunden if s["slot_id"].replace("-", "")
                      == slot_id.replace("-", ""))
        assert stunde["hat_entwurf"] is True
        assert stunde["stunde_node_id"] is not None, (
            "Die Antwort meldet einen Entwurf, nennt ihn aber nicht — der Titel auf der "
            "Startseite kann nicht verlinken."
        )
        assert stunde["stunde_node_id"].replace("-", "") == lesson_id.replace("-", "")

        # Gegenprobe: eine Stunde ohne Entwurf trägt hier nichts ein.
        ohne = [s for s in stunden if not s["hat_entwurf"]]
        assert all(s["stunde_node_id"] is None for s in ohne)
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lesson_slots WHERE id = %s", (slot_id,))
        conn.commit()
        conn.close()


# ── POST /planning/slots/{slot_id}/lesson (Entwurf vom Termin aus) ────────────


@pytest.mark.asyncio
async def test_entwurf_am_termin_ohne_einheit(
    test_client, auth_headers, seed_planning_fixtures, db_url
):
    """⚠️ **Der Normalfall am Schuljahresanfang: Stundenplan ja, Jahresplanung nein.**

    Über `POST /units/{id}/lessons` kommt so ein Termin an keinen Entwurf — die Route
    hängt am Einheitenknoten. Dieser Weg nimmt Gruppe und Fach vom Slot.

    Geprüft wird nicht nur, dass etwas entsteht, sondern dass es **benutzbar** ist:
    Der Editor muss die Stunde ohne Einheit laden können. Täte er es nicht, hätten wir
    einen Entwurf angelegt, den niemand öffnen kann.
    """
    from datetime import date

    slot_id = str(uuid4())
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO lesson_slots
                (id, group_id, date, start_period, periods, halbjahr, kategorie, thema)
            VALUES (%s, 100, %s, 7, 1, 1, 'unterricht', 'Titration')
        """, (slot_id, date.today()))
    conn.commit()
    try:
        resp = await test_client.post(
            f"/planning/slots/{slot_id}/lesson", headers=auth_headers
        )
        assert resp.status_code == 201, resp.text
        lesson_id = resp.json()["id"]
        # Das Thema des Termins wird der Titel — nicht „Neue Stunde".
        assert resp.json()["title"] == "Titration"

        # Der Editor muss sie laden können, ohne Einheit.
        gelesen = await test_client.get(
            f"/planning/lessons/{lesson_id}", headers=auth_headers
        )
        assert gelesen.status_code == 200, gelesen.text
        assert gelesen.json()["ue"] is None
        assert gelesen.json()["group_id"] == 100
        assert gelesen.json()["nav"]["total"] == 1

        # Und der Termin führt sie — sonst fände die Startseite sie nie wieder.
        ov = await test_client.get("/planning/groups/100/overview", headers=auth_headers)
        slot = next(s for s in ov.json()["slots"]
                    if s["id"].replace("-", "") == slot_id.replace("-", ""))
        assert slot["stunde_node_id"].replace("-", "") == lesson_id.replace("-", "")
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lesson_slots WHERE id = %s", (slot_id,))
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_entwurf_am_termin_ist_idempotent(
    test_client, auth_headers, seed_planning_fixtures, db_url
):
    """⚠️ **Zweimal klicken darf keinen zweiten Entwurf erzeugen.**

    Der Aufruf hängt am Klick auf den Stundentitel — Doppelklick und zweiter Tab sind
    keine Ausnahme, sondern Alltag. Der Slot führt nur *eine* Stunde: Der Überzählige
    wäre über keine Oberfläche erreichbar und bliebe für immer liegen.
    """
    from datetime import date

    slot_id = str(uuid4())
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO lesson_slots
                (id, group_id, date, start_period, periods, halbjahr, kategorie)
            VALUES (%s, 100, %s, 8, 1, 1, 'unterricht')
        """, (slot_id, date.today()))
    conn.commit()
    try:
        erst = await test_client.post(
            f"/planning/slots/{slot_id}/lesson", headers=auth_headers
        )
        zweit = await test_client.post(
            f"/planning/slots/{slot_id}/lesson", headers=auth_headers
        )
        assert erst.json()["id"] == zweit.json()["id"]
        assert erst.json()["neu"] is True
        assert zweit.json()["neu"] is False

        # Ohne Thema am Termin braucht die Stunde einen tragfähigen Vorgabetitel.
        assert erst.json()["title"] == "Neue Stunde"

        with conn.cursor() as cur:
            cur.execute("""
                SELECT count(*) FROM context_nodes
                WHERE content_type = 'unterrichtsstunde' AND status = 'active'
                  AND write_scope_group_id = 100 AND title = 'Neue Stunde'
            """)
            assert cur.fetchone()[0] == 1, "Der zweite Klick hat einen Entwurf erzeugt."
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lesson_slots WHERE id = %s", (slot_id,))
            cur.execute("""
                DELETE FROM context_nodes
                WHERE content_type = 'unterrichtsstunde'
                  AND write_scope_group_id = 100 AND title = 'Neue Stunde'
            """)
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_entwurf_am_termin_nur_fuer_die_eigene_gruppe(
    test_client, auth_teacher2, seed_planning_fixtures, db_url
):
    """Wer nicht in der Gruppe unterrichtet, legt dort auch keinen Entwurf an."""
    from datetime import date

    slot_id = str(uuid4())
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO lesson_slots
                (id, group_id, date, start_period, periods, halbjahr, kategorie)
            VALUES (%s, 100, %s, 9, 1, 1, 'unterricht')
        """, (slot_id, date.today()))
    conn.commit()
    try:
        resp = await test_client.post(
            f"/planning/slots/{slot_id}/lesson", headers=auth_teacher2
        )
        assert resp.status_code == 403, resp.text
        with conn.cursor() as cur:
            cur.execute("SELECT stunde_node_id FROM lesson_slots WHERE id = %s", (slot_id,))
            assert cur.fetchone()[0] is None
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lesson_slots WHERE id = %s", (slot_id,))
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_entwurf_am_termin_mit_einheit_haengt_sich_ein(
    test_client, auth_headers, seed_planning_fixtures, db_url
):
    """Gibt es eine Einheit, gehört die Stunde hinein — der Weg über den Slot darf sie
    nicht aus der Jahresplanung herausfallen lassen."""
    from datetime import date

    slot_id = str(uuid4())
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO lesson_slots
                (id, group_id, date, start_period, periods, halbjahr, kategorie)
            VALUES (%s, 100, %s, 10, 1, 1, 'unterricht')
        """, (slot_id, date.today()))
    conn.commit()
    try:
        ue_id = (
            await test_client.post(
                "/planning/groups/100/units",
                json={"titel": "Säuren und Basen", "farbe": 0},
                headers=auth_headers,
            )
        ).json()["id"]
        await test_client.patch(
            f"/planning/slots/{slot_id}", json={"ue_node_id": ue_id}, headers=auth_headers
        )

        resp = await test_client.post(
            f"/planning/slots/{slot_id}/lesson", headers=auth_headers
        )
        assert resp.status_code == 201, resp.text
        gelesen = await test_client.get(
            f"/planning/lessons/{resp.json()['id']}", headers=auth_headers
        )
        assert gelesen.json()["ue"] is not None, (
            "Die Stunde hängt an keiner Einheit, obwohl der Termin eine trägt."
        )
        assert gelesen.json()["ue"]["id"] == ue_id
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lesson_slots WHERE id = %s", (slot_id,))
        conn.commit()
        conn.close()


@pytest.fixture
def regelbetrieb(monkeypatch):
    """Der **Regelbetrieb** — ohne `STUDENT_SUBJECTS_OPT_IN`.

    ⚠️ **Ausdrücklich gesetzt, nicht geerbt.** Die Entwicklungs-`.env` dieses Projekts
    steht auf `true`; ein Test, der die Betriebsart von dort nimmt, grünt oder rotet je
    nach Maschine. Gemerkt an einem Test, der grün war, weil der Erprobungsbetrieb ihm
    *alle* Daten weggefiltert hatte — er prüfte nur Abwesenheit.

    Die Freigabe selbst prüft `test_mein_tag_schueler_achtet_auf_die_freigabe`.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "student_subjects_opt_in", False)


# ── GET /planning/mein-tag/schueler (Startseite, AP5) ─────────────────────────


@pytest.mark.asyncio
async def test_mein_tag_schueler_traegt_keine_planungsfelder(
    test_client, auth_student, seed_planning_fixtures, db_url, regelbetrieb
):
    """⚠️ **Thema, Einheit und Entwurf sind Material der Lehrkraft.**

    `docs/user/datenschutz.md`, „Was Schüler:innen mitbekommen": Die Vorbereitung einer
    Lehrkraft — worauf sie hinauswill, welche Einheit sie ansetzt, was im Entwurf steht —
    gehört ihr. Eine Startseite, die das ausliefert, verrät es auch dann, wenn die
    Oberfläche es nicht anzeigt: Es steht im JSON.

    Geprüft wird deshalb die **Antwort**, nicht die Darstellung.
    """
    from datetime import date

    heute = date.today()
    slot_id = str(uuid4())
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO lesson_slots
                (id, group_id, date, start_period, periods, halbjahr, kategorie, thema)
            VALUES (%s, 100, %s, 4, 2, 1, 'unterricht', 'Geheime Vorbereitung')
        """, (slot_id, heute))
    conn.commit()
    try:
        resp = await test_client.get("/planning/mein-tag/schueler", headers=auth_student)
        assert resp.status_code == 200, resp.text
        daten = resp.json()

        fach = next(f for f in daten["heute"]["faecher"] if f["stunde"] == "4.–5.")
        assert fach["fach"]  # der Gruppenname steht da
        assert fach["hinweis"] is None  # regulärer Unterricht sagt nichts

        # ⚠️ Der Wächter: **kein** Planungsfeld, in keiner Stunde, in keinem der Tage.
        verboten = {
            "thema", "ue_node_id", "ue_titel", "stunde_node_id", "hat_entwurf",
            "kategorie", "anpassung_noetig", "slot_id",
        }
        for tag in ("heute", "naechster"):
            for f in (daten[tag] or {}).get("faecher", []):
                gefunden = verboten & set(f)
                assert not gefunden, f"Planungsfelder in der Schülerantwort: {gefunden}"

        # Und die Gegenrichtung: Das Thema darf auch nicht im ganzen JSON auftauchen.
        assert "Geheime Vorbereitung" not in resp.text
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lesson_slots WHERE id = %s", (slot_id,))
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_mein_tag_schueler_nennt_den_ausfall(
    test_client, auth_student, seed_planning_fixtures, db_url, regelbetrieb
):
    """Eine ausgefallene Stunde als gewöhnliche zu listen wäre eine Falschauskunft —
    und sie wegzulassen auch. Also steht der Grund da, als **ein Wort**."""
    from datetime import date

    heute = date.today()
    slot_id = str(uuid4())
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO lesson_slots
                (id, group_id, date, start_period, periods, halbjahr, kategorie)
            VALUES (%s, 100, %s, 6, 1, 1, 'ausfall')
        """, (slot_id, heute))
    conn.commit()
    try:
        resp = await test_client.get("/planning/mein-tag/schueler", headers=auth_student)
        fach = next(f for f in resp.json()["heute"]["faecher"] if f["stunde"] == "6.")
        assert fach["hinweis"] == "fällt aus"
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lesson_slots WHERE id = %s", (slot_id,))
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_mein_tag_schueler_zeigt_nur_eigene_gruppen(
    test_client, auth_student, seed_planning_fixtures, db_url, regelbetrieb
):
    """⚠️ Der Mitgliedschaftsfilter ist auch hier die Zugriffsregel — und er fragt nach
    `role_in_group = 'student'`: Die Lehrkraft-Zeile derselben Gruppe darf nicht greifen,
    sonst sähe jede Lehrkraft ihren Tag zweimal und in der falschen Form."""
    from datetime import date

    heute = date.today()
    slot_id = str(uuid4())
    eigener_slot = str(uuid4())
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO groups (id, name, slug, type, subject_id)
            VALUES (102, 'Fremde Lerngruppe', 'fremde-lerngruppe-test', 'teaching_group', 100)
            ON CONFLICT (id) DO NOTHING
        """)
        cur.execute("""
            INSERT INTO lesson_slots
                (id, group_id, date, start_period, periods, halbjahr, kategorie)
            VALUES (%s, 102, %s, 1, 1, 1, 'unterricht')
        """, (slot_id, heute))
        # Die eigene Stunde als Vergleichspunkt — ohne sie prüft der Test nur, dass
        # überhaupt nichts ankommt, und das wäre auch bei einem kaputten Endpunkt wahr.
        cur.execute("""
            INSERT INTO lesson_slots
                (id, group_id, date, start_period, periods, halbjahr, kategorie)
            VALUES (%s, 100, %s, 1, 1, 1, 'unterricht')
        """, (eigener_slot, heute))
    conn.commit()
    try:
        resp = await test_client.get("/planning/mein-tag/schueler", headers=auth_student)
        gruppen = {f["group_id"] for f in resp.json()["heute"]["faecher"]}
        # ⚠️ **Erst die positive Aussage.** Der erste Entwurf dieses Tests prüfte nur die
        # Abwesenheit der fremden Gruppe — und war grün, weil der Erprobungsbetrieb aus
        # der `.env` *beide* herausfilterte. Ein Test, der nichts findet, beweist nichts.
        assert 100 in gruppen, "Die eigene Gruppe fehlt — der Test misst nichts."
        assert 102 not in gruppen, "Der Stundenplan einer fremden Gruppe steht in der Antwort."
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lesson_slots WHERE id IN (%s, %s)",
                        (slot_id, eigener_slot))
            cur.execute("DELETE FROM groups WHERE id = 102")
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_mein_tag_schueler_achtet_auf_die_freigabe(
    test_client, auth_student, seed_planning_fixtures, db_url, monkeypatch
):
    """⚠️ **Im Erprobungsbetrieb zählt `student_visible` — serverseitig.**

    Für die Fachübersicht filtert das Frontend; das genügt dort, weil die Liste nur
    Namen trägt. Hier ginge es um den **Stundenplan** einer nicht freigegebenen Gruppe.
    Der hat in der Antwort nichts verloren, auch nicht ungenutzt im JSON.
    """
    from datetime import date
    from app.config import settings

    heute = date.today()
    slot_id = str(uuid4())
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO lesson_slots
                (id, group_id, date, start_period, periods, halbjahr, kategorie)
            VALUES (%s, 100, %s, 2, 1, 1, 'unterricht')
        """, (slot_id, heute))
        cur.execute("UPDATE groups SET student_visible = false WHERE id = 100")
    conn.commit()
    try:
        # Regelbetrieb: Die Freigabe ist folgenlos, die Stunde steht da.
        monkeypatch.setattr(settings, "student_subjects_opt_in", False)
        resp = await test_client.get("/planning/mein-tag/schueler", headers=auth_student)
        assert any(f["stunde"] == "2." for f in resp.json()["heute"]["faecher"])

        # Erprobungsbetrieb ohne Freigabe: nichts.
        monkeypatch.setattr(settings, "student_subjects_opt_in", True)
        resp = await test_client.get("/planning/mein-tag/schueler", headers=auth_student)
        assert not any(f["stunde"] == "2." for f in resp.json()["heute"]["faecher"]), (
            "Der Stundenplan einer nicht freigegebenen Gruppe steht in der Antwort."
        )

        # Mit Freigabe wieder sichtbar — sonst prüfte der Test nur, dass irgendetwas fehlt.
        with conn.cursor() as cur:
            cur.execute("UPDATE groups SET student_visible = true WHERE id = 100")
        conn.commit()
        resp = await test_client.get("/planning/mein-tag/schueler", headers=auth_student)
        assert any(f["stunde"] == "2." for f in resp.json()["heute"]["faecher"])
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lesson_slots WHERE id = %s", (slot_id,))
            cur.execute("UPDATE groups SET student_visible = false WHERE id = 100")
        conn.commit()
        conn.close()


# ── Stundenzahl als Text (Paket 4, AP1) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_jahresuebersicht_haelt_eine_stundenzahl_als_text_aus(
    test_client, auth_headers, seed_planning_fixtures, db_url
):
    """⚠️ **Eine Zeichenkette in `metadata['std']` legte die ganze Jahresübersicht lahm.**

    `_build_balance` rechnete `max(0, zugewiesen - soll_std)` — mit `"12"` warf das
    `TypeError`, und `GET /groups/{id}/overview` antwortete mit **500**. Sichtbar wurde
    das nicht als Fehlermeldung, sondern als „meine neue Unterrichtseinheit wird nicht
    gespeichert": Der Refresh nach dem Anlegen scheiterte, die Seite blieb unverändert,
    der zweite Klick erzeugte eine Dublette (Jan, 24.09.2026).

    `context_nodes.metadata` ist JSONB und erzwingt nichts — im Dev-Bestand standen
    **18 von 24** Kapiteln als Text da. Die Typannotation `soll_std: int | None` war
    schlicht unwahr; eine Annotation prüft nichts.
    """
    kapitel_id = str(uuid4())
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO context_nodes
                (id, category, content_type, title, read_scope, write_scope,
                 status, metadata)
            VALUES (%s, 'knowledge', 'kapitel', 'Kapitel mit Text-Stundenzahl',
                    'school', 'school', 'active', '{"std": "12"}'::jsonb)
        """, (kapitel_id,))
    conn.commit()
    try:
        ue_id = (
            await test_client.post(
                "/planning/groups/100/units",
                json={"titel": "Einheit am Text-Kapitel", "farbe": 0,
                      "kapitel_node_id": kapitel_id},
                headers=auth_headers,
            )
        ).json()["id"]

        resp = await test_client.get("/planning/groups/100/overview", headers=auth_headers)
        assert resp.status_code == 200, resp.text

        eintrag = next(i for i in resp.json()["balance"]["items"]
                       if i["ue_node_id"] == ue_id)
        assert eintrag["soll_std"] == 12, "Die Stundenzahl kam nicht als Zahl an."
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM context_edges WHERE to_node_id = %s", (kapitel_id,))
            cur.execute("DELETE FROM context_nodes WHERE id = %s", (kapitel_id,))
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_unbrauchbare_stundenzahl_wird_zu_keiner_angabe(
    test_client, auth_headers, seed_planning_fixtures, db_url
):
    """Aus „12-14" eine 12 zu machen wäre eine Erfindung — die Übersicht muss trotzdem
    antworten, nur eben ohne Sollwert."""
    kapitel_id = str(uuid4())
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO context_nodes
                (id, category, content_type, title, read_scope, write_scope,
                 status, metadata)
            VALUES (%s, 'knowledge', 'kapitel', 'Kapitel mit Spanne',
                    'school', 'school', 'active', '{"std": "12-14"}'::jsonb)
        """, (kapitel_id,))
    conn.commit()
    try:
        ue_id = (
            await test_client.post(
                "/planning/groups/100/units",
                json={"titel": "Einheit an der Spanne", "farbe": 0,
                      "kapitel_node_id": kapitel_id},
                headers=auth_headers,
            )
        ).json()["id"]

        resp = await test_client.get("/planning/groups/100/overview", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        eintrag = next(i for i in resp.json()["balance"]["items"]
                       if i["ue_node_id"] == ue_id)
        assert eintrag["soll_std"] is None
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM context_edges WHERE to_node_id = %s", (kapitel_id,))
            cur.execute("DELETE FROM context_nodes WHERE id = %s", (kapitel_id,))
        conn.commit()
        conn.close()
