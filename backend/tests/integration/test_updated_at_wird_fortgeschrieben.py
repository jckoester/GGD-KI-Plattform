"""`updated_at` muss sich bei jedem Schreibzugriff über die API bewegen.

**Warum das ein eigener Wächter ist.** `updated_at` ist das einzige Änderungssignal, das
ein Client von außen hat — der geplante Obsidian-Sync hängt daran, und die Liste „Meine
Bausteine" sortiert danach. Ein Zeitstempel, der stehen bleibt, macht keinen Fehler
sichtbar: Die Antwort ist richtig, die Änderung ist gespeichert, nur *sieht* sie von
außen aus wie keine. Gemessen am 12.09.2026 blieb er auf dem gesamten Kontextpfad stehen
— eine über `/context/nodes` geänderte Unterrichtsstunde galt als unverändert, obwohl
dieselbe Stunde über `/planning/lessons` korrekt fortgeschrieben wurde.

**Geprüft wird über HTTP, nicht am Modell.** Ein Test gegen `onupdate=` am Mapper würde
nur die gewählte Technik festschreiben; hier zählt die Zusage nach außen. Rohes SQL
(`app/calendar/sync.py`) umgeht jeden Mapper-Mechanismus und muss trotzdem liefern.

Die Datei deckt die Wege ab, die ein Spiegel benutzt — nicht jeden Schreibendpunkt des
Projekts. Kommt ein Weg dazu, den der Sync spiegelt, gehört er hierher.
"""

import asyncio

import psycopg2
import pytest

from tests.integration.test_planning_api import TEACHER1_PSEUDO

GRUPPE = 710
FACH = 710


@pytest.fixture(scope="module")
def sync_gruppe(db_url, run_migrations):
    """Eigene Gruppe, damit die Zeitstempel nicht an fremden Testdaten hängen."""
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO subjects (id, slug, name, sort_order) "
            "VALUES (%s, 'zeitstempel', 'Zeitstempelkunde', 0) ON CONFLICT (id) DO NOTHING",
            (FACH,),
        )
        cur.execute(
            "INSERT INTO groups (id, name, slug, type, subject_id) "
            "VALUES (%s, '9z Zeitstempel', 'zeitstempel-9z', 'teaching_group', %s) "
            "ON CONFLICT (id) DO NOTHING",
            (GRUPPE, FACH),
        )
        cur.execute(
            "INSERT INTO group_memberships (group_id, pseudonym, role_in_group) "
            "VALUES (%s, %s, 'teacher') ON CONFLICT DO NOTHING",
            (GRUPPE, TEACHER1_PSEUDO),
        )
    conn.commit()
    conn.close()
    return sync_url


def _stand(db_url: str, node_id, tabelle="context_nodes"):
    """`updated_at` direkt aus der DB — nicht aus der Antwort.

    Mehrere Lese-Schemata führen das Feld gar nicht (`UnitRead`, `LessonRead`). Die
    Datenbank ist die Instanz, gegen die der Wächter prüft; ob ein Schema den Wert
    ausliefert, ist eine zweite Frage (siehe `test_leseschemata_liefern_updated_at`).
    """
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute(f"SELECT updated_at FROM {tabelle} WHERE id = %s", (str(node_id),))
        zeile = cur.fetchone()
    conn.close()
    assert zeile is not None, f"{tabelle}/{node_id} nicht gefunden"
    return zeile[0]


async def _bewegt_sich(db_url, node_id, aktion, tabelle="context_nodes"):
    """Führt `aktion` aus und gibt (vorher, nachher, HTTP-Status) zurück.

    Die Pause ist nötig, weil der Zeitstempel sonst *zufällig* gleich sein könnte —
    dann prüfte der Wächter die Uhrauflösung statt des Verhaltens.
    """
    vorher = _stand(db_url, node_id, tabelle)
    await asyncio.sleep(1.05)
    antwort = await aktion()
    return vorher, _stand(db_url, node_id, tabelle), antwort


@pytest.fixture
async def knoten(test_client, auth_headers, sync_gruppe):
    """Ein einfacher Kontextknoten."""
    resp = await test_client.post(
        "/context/nodes",
        json={
            "category": "knowledge",
            "content_type": "methode",
            "title": "Zeitstempel-Probe",
            "content": "erste Fassung",
            "read_scope": "school",
            "write_scope": "school",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
async def stunde(test_client, auth_headers, sync_gruppe):
    """Eine Unterrichtsstunde samt Slot und Unterrichtseinheit."""
    await test_client.put(
        f"/planning/groups/{GRUPPE}/pattern",
        json={"halbjahr": 1, "patterns": [{"weekday": 2, "start_period": 4, "periods": 1}]},
        headers=auth_headers,
    )
    await test_client.post(
        f"/planning/groups/{GRUPPE}/slots/generate",
        json={"halbjahr": 1, "regenerate": False},
        headers=auth_headers,
    )
    ov = await test_client.get(f"/planning/groups/{GRUPPE}/overview", headers=auth_headers)
    frei = [s for s in ov.json()["slots"] if s["stunde_node_id"] is None]
    assert frei, "kein freier Slot — frühere Tests haben alle belegt"
    slot = frei[0]

    ue = await test_client.post(
        f"/planning/groups/{GRUPPE}/units",
        json={"titel": "Zeitstempel-UE", "farbe": 1},
        headers=auth_headers,
    )
    assert ue.status_code == 201, ue.text

    lesson = await test_client.post(
        f"/planning/units/{ue.json()['id']}/lessons",
        json={"slot_id": slot["id"], "titel": "Zeitstempel-Stunde"},
        headers=auth_headers,
    )
    assert lesson.status_code == 201, lesson.text
    return {"slot": slot, "ue": ue.json(), "stunde": lesson.json()}


class TestKontextpfad:
    """Der Pfad, auf dem der Zeitstempel bis 12.09.2026 stehen blieb."""

    async def test_inhalt_aendern(self, test_client, auth_headers, knoten, sync_gruppe):
        vorher, nachher, resp = await _bewegt_sich(
            sync_gruppe,
            knoten["id"],
            lambda: test_client.patch(
                f"/context/nodes/{knoten['id']}",
                json={"content": "zweite Fassung"},
                headers=auth_headers,
            ),
        )
        assert resp.status_code == 200, resp.text
        assert nachher > vorher, f"PATCH /context/nodes hat updated_at nicht bewegt ({vorher})"

    async def test_titel_aendern(self, test_client, auth_headers, knoten, sync_gruppe):
        vorher, nachher, resp = await _bewegt_sich(
            sync_gruppe,
            knoten["id"],
            lambda: test_client.patch(
                f"/context/nodes/{knoten['id']}/title",
                json={"title": "Zeitstempel-Probe, umbenannt"},
                headers=auth_headers,
            ),
        )
        assert resp.status_code == 200, resp.text
        assert nachher > vorher, f"PATCH /title hat updated_at nicht bewegt ({vorher})"

    async def test_archivieren_datiert_den_grabstein(
        self, test_client, auth_headers, knoten, sync_gruppe
    ):
        """Archivieren ist der **weiche** Weg und der einzige, der eine Spur hinterlässt.

        `DELETE /context/nodes/{id}` löscht hart (ADR-019: 409, wenn Fremde verweisen) —
        danach gibt es keine Zeile und keinen Zeitstempel mehr. Ein Spiegel erkennt den
        Fall nur am Fehlen, nicht an einem Datum. Was er datieren kann, ist das
        Archivieren, und genau darauf bildet er „archiviert" ab.
        """
        vorher, nachher, resp = await _bewegt_sich(
            sync_gruppe,
            knoten["id"],
            lambda: test_client.patch(
                f"/context/nodes/{knoten['id']}/verwalten",
                json={"status": "archived"},
                headers=auth_headers,
            ),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["archived_at"] is not None, "archived_at nicht gesetzt"
        assert nachher > vorher, f"Archivieren hat updated_at nicht bewegt ({vorher})"


class TestPlanungspfad:
    """Slot und Stunde waren schon richtig — die Unterrichtseinheit nicht."""

    async def test_slot_aendern(self, test_client, auth_headers, stunde, sync_gruppe):
        slot_id = stunde["slot"]["id"]
        vorher, nachher, resp = await _bewegt_sich(
            sync_gruppe,
            slot_id,
            lambda: test_client.patch(
                f"/planning/slots/{slot_id}",
                json={"thema": "Zeitstempel-Thema"},
                headers=auth_headers,
            ),
            tabelle="lesson_slots",
        )
        assert resp.status_code == 200, resp.text
        assert nachher > vorher, f"PATCH /planning/slots hat updated_at nicht bewegt ({vorher})"

    async def test_stunde_aendern(self, test_client, auth_headers, stunde, sync_gruppe):
        stunde_id = stunde["stunde"]["id"]
        vorher, nachher, resp = await _bewegt_sich(
            sync_gruppe,
            stunde_id,
            lambda: test_client.patch(
                f"/planning/lessons/{stunde_id}",
                json={"stundenziel": "Zeitstempel verstehen"},
                headers=auth_headers,
            ),
        )
        assert resp.status_code == 200, resp.text
        assert nachher > vorher, f"PATCH /planning/lessons hat updated_at nicht bewegt ({vorher})"

    async def test_einheit_aendern(self, test_client, auth_headers, stunde, sync_gruppe):
        ue_id = stunde["ue"]["id"]
        vorher, nachher, resp = await _bewegt_sich(
            sync_gruppe,
            ue_id,
            lambda: test_client.patch(
                f"/planning/groups/{GRUPPE}/units/{ue_id}",
                json={"titel": "Zeitstempel-UE, umbenannt"},
                headers=auth_headers,
            ),
        )
        assert resp.status_code == 200, resp.text
        assert nachher > vorher, f"PATCH /planning/units hat updated_at nicht bewegt ({vorher})"


class TestAbgeleiteteSchreibungen:
    """Die Gegenrichtung: Ein neu berechnetes Embedding ist **keine** Änderung.

    `onupdate` feuert auch bei Core-`update()`, also auch im nächtlichen Backfill
    (`docker-compose.yml`, 3:15 Uhr). Ohne Ausklammern sähe nach einem Modellwechsel jeder
    Knoten geändert aus — „Meine Bausteine" sortierte sich um, ein Spiegel schriebe alle
    Notizen neu. Der Knoten liest sich nach einem Embedding-Lauf aber genau wie vorher.
    """

    async def test_embedding_schreiben_bewegt_nichts(self, db_session):
        import sqlalchemy as sa

        from app.db.models import ContextNode, ohne_aenderungsstempel

        node = ContextNode(
            category="knowledge", content_type="methode", title="Abgeleitet-Probe",
            content="eins", read_scope="school", write_scope="school",
            status="active", owner_pseudonym="abgeleitet-probe",
        )
        db_session.add(node)
        await db_session.flush()

        async def stand():
            await db_session.flush()
            return (await db_session.execute(
                sa.select(ContextNode.updated_at).where(ContextNode.id == node.id)
            )).scalar()

        vorher = await stand()
        await asyncio.sleep(0.05)
        await db_session.execute(
            sa.update(ContextNode).where(ContextNode.id == node.id)
            .values(embedding=None, **ohne_aenderungsstempel())
        )
        assert await stand() == vorher, "Embedding-Schreibung hat updated_at bewegt"

        # Gegenprobe gegen den stummen Fehlschlag: Ohne den Zusatz **muss** sich der
        # Stempel bewegen. Täte er das nicht, prüfte der Test oben nichts — er wäre auch
        # dann grün, wenn `onupdate` ganz fehlte.
        await asyncio.sleep(0.05)
        await db_session.execute(
            sa.update(ContextNode).where(ContextNode.id == node.id).values(content="zwei")
        )
        assert await stand() > vorher, (
            "Ohne `ohne_aenderungsstempel()` bewegt sich der Stempel nicht — "
            "dann sagt die Prüfung darüber nichts aus"
        )


class TestLeseschemata:
    """Ein fortgeschriebener Zeitstempel nützt nichts, den niemand ausliefert."""

    async def test_stunde_liefert_updated_at(self, test_client, auth_headers, stunde):
        resp = await test_client.get(
            f"/planning/lessons/{stunde['stunde']['id']}", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        assert "updated_at" in resp.json(), "LessonRead führt kein updated_at"

    async def test_einheit_liefert_updated_at(self, test_client, auth_headers, stunde):
        resp = await test_client.get(
            f"/planning/groups/{GRUPPE}/units", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        einheiten = resp.json()
        assert einheiten, "keine Unterrichtseinheiten geliefert"
        assert "updated_at" in einheiten[0], "UnitRead führt kein updated_at"
