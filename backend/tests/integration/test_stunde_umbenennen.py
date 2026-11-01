"""Umbenennen eines Stundenentwurfs zieht das Thema des Termins nach (Befund Prod, 01.11.2026).

Die Jahresplanung zeigt `lesson_slots.thema`. Bis zur Behebung blieb ein umbenannter Entwurf
dort beim alten Namen oder bei „Thema eingeben …“. Ein bewusst anderes Thema bleibt stehen.
Erfordert TEST_DATABASE_URL.
"""
import psycopg2
import pytest

GRUPPE = 341
TEACHER1_PSEUDO = "teacher1-pseudo"


@pytest.fixture(scope="module")
def gruppe(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) "
                    "VALUES (341, 'nwt-umbenennen', 'NwT Umbenennen', 0) ON CONFLICT (id) DO NOTHING")
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                    "VALUES (341, 'NwT 9 Umbenennen', 'nwt-umbenennen', 'teaching_group', 341) "
                    "ON CONFLICT (id) DO NOTHING")
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                    "VALUES (341, %s, 'teacher', 'eigen') ON CONFLICT DO NOTHING", (TEACHER1_PSEUDO,))
    conn.commit()
    conn.close()


async def _slots(client, h):
    await client.put(f"/planning/groups/{GRUPPE}/pattern", headers=h,
                     json={"halbjahr": 1, "patterns": [{"weekday": 0, "start_period": 3, "periods": 1}]})
    await client.post(f"/planning/groups/{GRUPPE}/slots/generate", headers=h,
                      json={"halbjahr": 1, "regenerate": True})
    return (await client.get(f"/planning/groups/{GRUPPE}/overview", headers=h)).json()["slots"]


async def _thema(client, h, slot_id):
    slots = (await client.get(f"/planning/groups/{GRUPPE}/overview", headers=h)).json()["slots"]
    return next(s["thema"] for s in slots if s["id"] == slot_id)


@pytest.mark.asyncio
async def test_umbenennen_zieht_das_thema_nach(test_client, auth_headers, gruppe):
    h = auth_headers
    slots = await _slots(test_client, h)
    leer, alt, eigen = slots[0]["id"], slots[1]["id"], slots[2]["id"]
    ue = (await test_client.post(f"/planning/groups/{GRUPPE}/units", headers=h,
                                 json={"titel": "Zahnräder", "farbe": 0})).json()["id"]

    # Termin ohne Thema, mit dem alten Titel und mit eigenem Thema — je eine Stunde.
    await test_client.patch(f"/planning/slots/{alt}", headers=h, json={"thema": "Übersetzung"})
    await test_client.patch(f"/planning/slots/{eigen}", headers=h, json={"thema": "Mein Thema"})
    stunden = {}
    for slot in (leer, alt, eigen):
        resp = await test_client.post(f"/planning/units/{ue}/lessons", headers=h,
                                      json={"titel": "Übersetzung", "slot_id": slot})
        assert resp.status_code in (200, 201), resp.text
        stunden[slot] = resp.json()["id"]
    # Beim Anlegen ohne Thema ist der Termin leer — genau der gemeldete Fall.
    await test_client.patch(f"/planning/slots/{leer}", headers=h, json={"thema": None})

    for slot, stunde in stunden.items():
        resp = await test_client.patch(f"/planning/lessons/{stunde}", headers=h,
                                       json={"titel": "Übersetzungsverhältnis"})
        assert resp.status_code == 200, resp.text

    assert await _thema(test_client, h, leer) == "Übersetzungsverhältnis"
    assert await _thema(test_client, h, alt) == "Übersetzungsverhältnis"
    assert await _thema(test_client, h, eigen) == "Mein Thema"
