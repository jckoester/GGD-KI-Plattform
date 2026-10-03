"""Eine im Planer bearbeitete Stunde lässt sich über `PATCH /context/nodes` speichern.

Bis 0.12.0 nicht: Der Validator dort verlangte ein eigenes Phasenformat (`titel`,
`status` Pflicht), der Planer schreibt `name` und keinen `status` — 422. Seit dem Patch
prüft der Validator mit dem Schema des Planers (`validate_unterrichtsstunde_metadata`).
"""
import psycopg2
import pytest

GRUPPE = 332
TEACHER1_PSEUDO = "teacher1-pseudo"


@pytest.fixture(scope="module")
def gruppe(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) "
                    "VALUES (332, 'nwt-kontextpatch', 'NwT Kontextpatch', 0) ON CONFLICT (id) DO NOTHING")
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                    "VALUES (332, 'NwT 9 Kontextpatch', 'nwt-kontextpatch', 'teaching_group', 332) "
                    "ON CONFLICT (id) DO NOTHING")
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                    "VALUES (332, %s, 'teacher', 'eigen') ON CONFLICT DO NOTHING", (TEACHER1_PSEUDO,))
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_planer_stunde_laesst_sich_ueber_den_kontext_patch_speichern(
    test_client, auth_headers, gruppe
):
    h = auth_headers
    ue = (await test_client.post(f"/planning/groups/{GRUPPE}/units", headers=h,
                                 json={"titel": "Zahnräder", "farbe": 0})).json()["id"]
    stunde = (await test_client.post(f"/planning/units/{ue}/lessons", headers=h,
                                     json={"titel": "Übersetzung"})).json()["id"]

    # So, wie der Planer Phasen speichert.
    resp = await test_client.patch(f"/planning/lessons/{stunde}", headers=h, json={"phasen": [
        {"name": "Einstieg", "dauer_min": 10, "prio": "kern",
         "material": [{"typ": "text", "wert": "Video Zahnräder"}]},
        {"name": "Erarbeitung", "dauer_min": 25, "prio": "kern"},
    ]})
    assert resp.status_code == 200, resp.text

    knoten = (await test_client.get(f"/context/nodes/{stunde}", headers=h)).json()
    metadaten = knoten["metadata"]
    assert [p["name"] for p in metadaten["phasen"]] == ["Einstieg", "Erarbeitung"]

    # Derselbe Stand über den allgemeinen Weg — bis 0.12.0 ein 422.
    metadaten["stundenziel"] = "Übersetzungsverhältnis berechnen"
    resp = await test_client.patch(f"/context/nodes/{stunde}", headers=h,
                                   json={"metadata": metadaten})
    assert resp.status_code == 200, resp.text
    assert resp.json()["metadata"]["stundenziel"] == "Übersetzungsverhältnis berechnen"


@pytest.mark.asyncio
async def test_kaputte_phase_wird_weiter_abgelehnt(test_client, auth_headers, gruppe):
    """Die Prüfung ist nicht weg, sie prüft nur das richtige Format."""
    h = auth_headers
    ue = (await test_client.post(f"/planning/groups/{GRUPPE}/units", headers=h,
                                 json={"titel": "Zahnräder 2", "farbe": 0})).json()["id"]
    stunde = (await test_client.post(f"/planning/units/{ue}/lessons", headers=h,
                                     json={"titel": "Kaputt"})).json()["id"]
    # Ohne Namen — eine Phase ohne Dauer ist seit 0.13 gültig (P1).
    resp = await test_client.patch(f"/context/nodes/{stunde}", headers=h,
                                   json={"metadata": {"phasen": [{"dauer_min": 10}]}})
    assert resp.status_code == 422
    assert "name" in resp.text
