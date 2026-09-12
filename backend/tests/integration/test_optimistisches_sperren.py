"""Optimistisches Sperren an den beiden Schreibendpunkten, die ein Sync-Client benutzt.

Der Fall, den es verhindert: Ein Client liest einen Stand, jemand ändert ihn in der
Oberfläche, der Client schreibt seinen alten Stand zurück — und die Änderung ist weg,
ohne dass irgendwo etwas aufgefallen wäre.
"""

import psycopg2
import pytest

from tests.integration.test_planning_api import TEACHER1_PSEUDO

GRUPPE = 730
FACH = 730


@pytest.fixture(scope="module")
def sperr_gruppe(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO subjects (id, slug, name, sort_order) "
            "VALUES (%s, 'sperrkunde', 'Sperrkunde', 0) ON CONFLICT (id) DO NOTHING",
            (FACH,),
        )
        cur.execute(
            "INSERT INTO groups (id, name, slug, type, subject_id) "
            "VALUES (%s, '9s Sperre', 'sperre-9s', 'teaching_group', %s) "
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


@pytest.fixture
async def slot(test_client, auth_headers, sperr_gruppe):
    await test_client.put(
        f"/planning/groups/{GRUPPE}/pattern",
        json={"halbjahr": 1, "patterns": [{"weekday": 3, "start_period": 1, "periods": 1}]},
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
    return frei[0]


@pytest.fixture
async def stunde(test_client, auth_headers, slot):
    ue = await test_client.post(
        f"/planning/groups/{GRUPPE}/units",
        json={"titel": "Sperr-UE", "farbe": 3},
        headers=auth_headers,
    )
    assert ue.status_code == 201, ue.text
    lesson = await test_client.post(
        f"/planning/units/{ue.json()['id']}/lessons",
        json={"slot_id": slot["id"], "titel": "Sperr-Stunde"},
        headers=auth_headers,
    )
    assert lesson.status_code == 201, lesson.text
    gelesen = await test_client.get(
        f"/planning/lessons/{lesson.json()['id']}", headers=auth_headers
    )
    assert gelesen.status_code == 200, gelesen.text
    return gelesen.json()


class TestSlot:
    async def test_passender_stand_darf_schreiben(self, test_client, auth_headers, slot):
        resp = await test_client.patch(
            f"/planning/slots/{slot['id']}",
            json={"thema": "Mit Vorbedingung", "expected_updated_at": slot["updated_at"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["thema"] == "Mit Vorbedingung"
        # Die Antwort trägt den neuen Stand — Grundlage für den nächsten Schreibversuch.
        assert resp.json()["updated_at"] != slot["updated_at"]

    async def test_veralteter_stand_wird_abgelehnt(self, test_client, auth_headers, slot):
        """Der eigentliche Fall: zwischendurch hat jemand anderes geschrieben."""
        ersterfolg = await test_client.patch(
            f"/planning/slots/{slot['id']}",
            json={"thema": "Aus der Oberfläche"},
            headers=auth_headers,
        )
        assert ersterfolg.status_code == 200

        resp = await test_client.patch(
            f"/planning/slots/{slot['id']}",
            json={"thema": "Vom Spiegel", "expected_updated_at": slot["updated_at"]},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["grund"] == "veraltet"

    async def test_abgelehnter_schreibversuch_aendert_nichts(
        self, test_client, auth_headers, slot
    ):
        await test_client.patch(
            f"/planning/slots/{slot['id']}",
            json={"thema": "Aus der Oberfläche"},
            headers=auth_headers,
        )
        await test_client.patch(
            f"/planning/slots/{slot['id']}",
            json={"thema": "Vom Spiegel", "expected_updated_at": slot["updated_at"]},
            headers=auth_headers,
        )
        ov = await test_client.get(
            f"/planning/groups/{GRUPPE}/overview", headers=auth_headers
        )
        aktuell = next(s for s in ov.json()["slots"] if s["id"] == slot["id"])
        assert aktuell["thema"] == "Aus der Oberfläche"

    async def test_ohne_vorbedingung_bleibt_es_beim_alten(
        self, test_client, auth_headers, slot
    ):
        """Die Oberfläche schickt nichts — sie darf durch alle Änderungen hindurch."""
        await test_client.patch(
            f"/planning/slots/{slot['id']}", json={"thema": "erst"}, headers=auth_headers
        )
        resp = await test_client.patch(
            f"/planning/slots/{slot['id']}", json={"thema": "dann"}, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["thema"] == "dann"

    async def test_erfolgreicher_schreibversuch_bewegt_den_stempel(
        self, test_client, auth_headers, slot
    ):
        """Sonst wäre die Vorbedingung beim zweiten Versuch sofort wieder erfüllt."""
        resp = await test_client.patch(
            f"/planning/slots/{slot['id']}",
            json={"thema": "x", "expected_updated_at": slot["updated_at"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["updated_at"] > slot["updated_at"]


class TestStunde:
    async def test_passender_stand_darf_schreiben(self, test_client, auth_headers, stunde):
        resp = await test_client.patch(
            f"/planning/lessons/{stunde['id']}",
            json={"stundenziel": "Mit Vorbedingung",
                  "expected_updated_at": stunde["updated_at"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["updated_at"] != stunde["updated_at"]

    async def test_veralteter_stand_wird_abgelehnt(self, test_client, auth_headers, stunde):
        await test_client.patch(
            f"/planning/lessons/{stunde['id']}",
            json={"stundenziel": "Aus der Oberfläche"},
            headers=auth_headers,
        )
        resp = await test_client.patch(
            f"/planning/lessons/{stunde['id']}",
            json={"stundenziel": "Vom Spiegel",
                  "expected_updated_at": stunde["updated_at"]},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert "erwartet" in resp.json()["detail"]

    async def test_abgelehnter_versuch_legt_keinen_snapshot_an(
        self, test_client, auth_headers, stunde
    ):
        """Sonst füllt ein Client mit veraltetem Stand den Verlauf mit leeren Einträgen."""
        vorher = len(
            (await test_client.get(
                f"/planning/groups/{GRUPPE}/snapshots", headers=auth_headers
            )).json()
        )
        resp = await test_client.patch(
            f"/planning/lessons/{stunde['id']}",
            json={"stundenziel": "zu spät", "expected_updated_at": "2020-01-01T00:00:00Z"},
            headers=auth_headers,
        )
        assert resp.status_code == 409
        nachher = len(
            (await test_client.get(
                f"/planning/groups/{GRUPPE}/snapshots", headers=auth_headers
            )).json()
        )
        assert nachher == vorher, "abgelehnter Schreibversuch hat einen Snapshot erzeugt"

    async def test_der_zurueckgegebene_stand_traegt_den_naechsten_versuch(
        self, test_client, auth_headers, stunde
    ):
        """Zwei Schreibvorgänge hintereinander, ohne zwischendurch neu zu lesen."""
        erste = await test_client.patch(
            f"/planning/lessons/{stunde['id']}",
            json={"stundenziel": "eins", "expected_updated_at": stunde["updated_at"]},
            headers=auth_headers,
        )
        assert erste.status_code == 200, erste.text
        zweite = await test_client.patch(
            f"/planning/lessons/{stunde['id']}",
            json={"stundenziel": "zwei",
                  "expected_updated_at": erste.json()["updated_at"]},
            headers=auth_headers,
        )
        assert zweite.status_code == 200, zweite.text
