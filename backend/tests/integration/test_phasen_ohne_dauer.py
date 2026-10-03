"""Phasen ohne Dauer über die Planungs-Schnittstelle (0.13, P1).

Eine Skizze aus dem Vault hat noch keine Minuten. Bis 0.12 lehnte die Plattform eine
solche Phase mit 422 ab; jetzt heißt `"dauer_min": null` „noch nicht festgelegt" — und
Lesen, Exportieren und der Reflow müssen damit umgehen.
"""
import psycopg2
import pytest

GRUPPE = 334
TEACHER1_PSEUDO = "teacher1-pseudo"


@pytest.fixture(scope="module")
def gruppe(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) "
                    "VALUES (334, 'nwt-skizze', 'NwT Skizze', 0) ON CONFLICT (id) DO NOTHING")
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                    "VALUES (334, 'NwT 9 Skizze', 'nwt-skizze', 'teaching_group', 334) "
                    "ON CONFLICT (id) DO NOTHING")
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                    "VALUES (334, %s, 'teacher', 'eigen') ON CONFLICT DO NOTHING", (TEACHER1_PSEUDO,))
    conn.commit()
    conn.close()


async def _stunde(client, headers):
    ue = (await client.post(f"/planning/groups/{GRUPPE}/units", headers=headers,
                            json={"titel": "Zahnräder", "farbe": 0})).json()["id"]
    return (await client.post(f"/planning/units/{ue}/lessons", headers=headers,
                              json={"titel": "Übersetzung"})).json()["id"]


@pytest.mark.asyncio
async def test_phase_ohne_dauer_wird_gespeichert_und_gelesen(test_client, auth_headers, gruppe):
    h = auth_headers
    stunde = await _stunde(test_client, h)
    resp = await test_client.patch(f"/planning/lessons/{stunde}", headers=h, json={"phasen": [
        {"name": "Einstieg: Video Zahnräder"},
        {"name": "Erarbeitung", "dauer_min": 25, "prio": "kern"},
    ]})
    assert resp.status_code == 200, resp.text

    knoten = (await test_client.get(f"/context/nodes/{stunde}", headers=h)).json()
    gespeichert = knoten["metadata"]["phasen"]
    assert "dauer_min" in gespeichert[0] and gespeichert[0]["dauer_min"] is None
    assert gespeichert[1]["dauer_min"] == 25

    gelesen = (await test_client.get(f"/planning/lessons/{stunde}", headers=h)).json()
    assert [p["dauer_min"] for p in gelesen["phasen"]] == [None, 25]


@pytest.mark.asyncio
@pytest.mark.parametrize("format", ["md", "docx"])
async def test_export_mit_phase_ohne_dauer(test_client, auth_headers, gruppe, format):
    h = auth_headers
    stunde = await _stunde(test_client, h)
    await test_client.patch(f"/planning/lessons/{stunde}", headers=h, json={"phasen": [
        {"name": "Einstieg"}, {"name": "Sicherung", "dauer_min": 10},
    ]})
    resp = await test_client.get(f"/planning/lessons/{stunde}/export?format={format}", headers=h)
    assert resp.status_code == 200, resp.text
    if format == "md":
        assert "## Einstieg (Kern)" in resp.text
        assert "None" not in resp.text
