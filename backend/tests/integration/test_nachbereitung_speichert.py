"""Nachbereitung und „Rückgängig" landen in der Datenbank (0.13.1).

Gemessen am 04.10.2026: `review_service.py` änderte die gespeicherten Phasen in place.
Damit änderte sich auch der Vergleichswert, an dem SQLAlchemy erkennt, ob es schreiben
muss — geschrieben wurde nur, wenn sich zufällig `refs_offen` oder `reflexion` mit
änderten. Nach „Rückgängig" blieben die Stati stehen, eine zweite Nachbereitung kam nie
an. Dazu überschrieb jede Nachbereitung gespeicherte Stati mit „erledigt", die
Auto-Nachbereitung (`phasen_status={}`) also jede Streichung.

Gelesen wird über die API, also in einer eigenen Sitzung — ein Test, der das Objekt der
schreibenden Sitzung ansieht, sähe den Stand im Speicher und wäre grün.
"""
import psycopg2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.planning.operations import StrikePhase, apply_operations
from app.planning.review_service import complete_review

GRUPPE = 336
TEACHER1_PSEUDO = "teacher1-pseudo"


@pytest.fixture(scope="module")
def gruppe(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) "
                    "VALUES (336, 'nwt-nachbereitung', 'NwT Nachbereitung', 0) ON CONFLICT (id) DO NOTHING")
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                    "VALUES (336, 'NwT 9 Nachbereitung', 'nwt-nachbereitung', 'teaching_group', 336) "
                    "ON CONFLICT (id) DO NOTHING")
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                    "VALUES (336, %s, 'teacher', 'eigen') ON CONFLICT DO NOTHING", (TEACHER1_PSEUDO,))
    conn.commit()
    conn.close()


async def _slots(client, h):
    await client.put(f"/planning/groups/{GRUPPE}/pattern", headers=h,
                     json={"halbjahr": 1, "patterns": [{"weekday": 0, "start_period": 3, "periods": 1}]})
    await client.post(f"/planning/groups/{GRUPPE}/slots/generate", headers=h,
                      json={"halbjahr": 1, "regenerate": True})
    return (await client.get(f"/planning/groups/{GRUPPE}/overview", headers=h)).json()["slots"]


async def _stunde(client, h, slot_id):
    ue = (await client.post(f"/planning/groups/{GRUPPE}/units", headers=h,
                            json={"titel": "Zahnräder", "farbe": 0})).json()["id"]
    stunde = (await client.post(f"/planning/units/{ue}/lessons", headers=h,
                                json={"titel": "Übersetzung", "slot_id": slot_id})).json()["id"]
    resp = await client.patch(f"/planning/lessons/{stunde}", headers=h, json={"phasen": [
        {"name": "Einstieg", "dauer_min": 10}, {"name": "Erarbeitung", "dauer_min": 20},
        {"name": "Sicherung", "dauer_min": 10},
    ]})
    assert resp.status_code == 200, resp.text
    return stunde


async def _phasen(client, h, stunde):
    return (await client.get(f"/context/nodes/{stunde}", headers=h)).json()["metadata"]["phasen"]


async def _stati(client, h, stunde):
    return [p.get("status") for p in await _phasen(client, h, stunde)]


async def _kennung(client, h, stunde, name):
    return next(p["id"] for p in await _phasen(client, h, stunde) if p["name"] == name)


def _sitzungen(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def _streiche(async_engine, stunde, phase_id):
    async with _sitzungen(async_engine)() as db:
        ergebnis = await apply_operations(
            db, GRUPPE, [StrikePhase(op="strike_phase", lesson_id=stunde, phase_id=phase_id)],
            summary="gestrichen")
    assert not ergebnis.errors


@pytest.mark.asyncio
async def test_rueckgaengig_und_zweite_nachbereitung_werden_gespeichert(test_client, auth_headers, gruppe):
    h = auth_headers
    slot = (await _slots(test_client, h))[0]["id"]
    stunde = await _stunde(test_client, h, slot)
    erarbeitung = await _kennung(test_client, h, stunde, "Erarbeitung")
    sicherung = await _kennung(test_client, h, stunde, "Sicherung")

    resp = await test_client.post(f"/planning/slots/{slot}/review", headers=h,
                                  json={"phasen_status": {erarbeitung: "offen"}})
    assert resp.status_code == 200, resp.text
    assert await _stati(test_client, h, stunde) == ["erledigt", "offen", "erledigt"]

    resp = await test_client.delete(f"/planning/slots/{slot}/review", headers=h)
    assert resp.status_code == 200, resp.text
    # Bis 0.13.0: erledigt / offen / erledigt — der Termin galt als nicht nachbereitet,
    # die Phasen trugen weiter den alten Stand.
    assert await _stati(test_client, h, stunde) == [None, None, None]

    resp = await test_client.post(f"/planning/slots/{slot}/review", headers=h,
                                  json={"phasen_status": {erarbeitung: "erledigt", sicherung: "gestrichen"}})
    assert resp.status_code == 200, resp.text
    assert await _stati(test_client, h, stunde) == ["erledigt", "erledigt", "gestrichen"]


@pytest.mark.asyncio
async def test_auto_nachbereitung_laesst_eine_streichung_stehen(
    test_client, auth_headers, gruppe, async_engine
):
    h = auth_headers
    slot = (await _slots(test_client, h))[1]["id"]
    stunde = await _stunde(test_client, h, slot)
    await _streiche(async_engine, stunde, await _kennung(test_client, h, stunde, "Sicherung"))

    # Genau der Aufruf aus `crons/lesson_review_service.py`: keine Stati.
    async with _sitzungen(async_engine)() as db:
        await complete_review(db, slot, group_id=GRUPPE, phasen_status={}, auto=True)

    # Bis 0.13.0: erledigt / erledigt / erledigt
    assert await _stati(test_client, h, stunde) == ["erledigt", "erledigt", "gestrichen"]


@pytest.mark.asyncio
async def test_rueckgaengig_gibt_den_status_von_vorher_zurueck(
    test_client, auth_headers, gruppe, async_engine
):
    """Streichen → nachbereiten → im Planer speichern → „Rückgängig": wieder gestrichen.

    Ohne `status_vorher` war die Phase danach entstrichen — „Rückgängig" löschte jeden
    Status, auch den, der schon vor der Nachbereitung da war. Das Speichern dazwischen
    prüft, dass die Marke die Planer-Nutzlast übersteht (Regel aus 0.13 P2).
    """
    h = auth_headers
    slot = (await _slots(test_client, h))[3]["id"]
    stunde = await _stunde(test_client, h, slot)
    sicherung = await _kennung(test_client, h, stunde, "Sicherung")
    await _streiche(async_engine, stunde, sicherung)

    resp = await test_client.post(f"/planning/slots/{slot}/review", headers=h,
                                  json={"phasen_status": {sicherung: "erledigt"}})
    assert resp.status_code == 200, resp.text

    schemafelder = ("id", "name", "dauer_min", "beschreibung", "prio", "sozialform", "methode", "material")
    resp = await test_client.patch(f"/planning/lessons/{stunde}", headers=h, json={"phasen": [
        {k: p.get(k) for k in schemafelder} for p in await _phasen(test_client, h, stunde)]})
    assert resp.status_code == 200, resp.text

    resp = await test_client.delete(f"/planning/slots/{slot}/review", headers=h)
    assert resp.status_code == 200, resp.text
    phasen = await _phasen(test_client, h, stunde)
    assert [p.get("status") for p in phasen] == [None, None, "gestrichen"]
    assert not any("status_vorher" in p for p in phasen)


@pytest.mark.asyncio
async def test_ausdruecklicher_status_geht_vor(test_client, auth_headers, gruppe, async_engine):
    """Die Lehrkraft hat das letzte Wort: Sie hat die gestrichene Phase doch gehalten."""
    h = auth_headers
    slot = (await _slots(test_client, h))[2]["id"]
    stunde = await _stunde(test_client, h, slot)
    sicherung = await _kennung(test_client, h, stunde, "Sicherung")
    await _streiche(async_engine, stunde, sicherung)

    resp = await test_client.post(f"/planning/slots/{slot}/review", headers=h,
                                  json={"phasen_status": {sicherung: "erledigt"}})
    assert resp.status_code == 200, resp.text
    assert await _stati(test_client, h, stunde) == ["erledigt", "erledigt", "erledigt"]
