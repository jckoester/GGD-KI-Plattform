"""Phasenfelder überleben das Speichern (0.13, P2).

Nachgestellt am 03.10.2026 auf der Dev-Instanz: Nachbereitung mit {Erarbeitung: offen}
→ Phasenstatus erledigt / offen / erledigt. Dann `PATCH /planning/lessons/{id}` mit genau
den Feldern, die der Planer schickt → None / None / None. Die als „offen" nachbereitete
Phase war im Reflow verschwunden. Dasselbe beim Planungsassistenten. Regel:
`app/planning/phasen.py`, `uebernimm_zusatzfelder`.
"""
import psycopg2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ContextNode
from app.planning.operations import StrikePhase, TransferPhases, apply_operations
from app.planning.reflow_service import build_reflow_context

GRUPPE = 335
TEACHER1_PSEUDO = "teacher1-pseudo"
SCHEMAFELDER = ("id", "name", "dauer_min", "beschreibung", "prio", "sozialform", "methode", "material")


@pytest.fixture(scope="module")
def gruppe(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) "
                    "VALUES (335, 'nwt-phasenfelder', 'NwT Phasenfelder', 0) ON CONFLICT (id) DO NOTHING")
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                    "VALUES (335, 'NwT 9 Phasenfelder', 'nwt-phasenfelder', 'teaching_group', 335) "
                    "ON CONFLICT (id) DO NOTHING")
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                    "VALUES (335, %s, 'teacher', 'eigen') ON CONFLICT DO NOTHING", (TEACHER1_PSEUDO,))
    conn.commit()
    conn.close()


async def _slots(client, h):
    await client.put(f"/planning/groups/{GRUPPE}/pattern", headers=h,
                     json={"halbjahr": 1, "patterns": [{"weekday": 0, "start_period": 3, "periods": 1}]})
    await client.post(f"/planning/groups/{GRUPPE}/slots/generate", headers=h,
                      json={"halbjahr": 1, "regenerate": True})
    return (await client.get(f"/planning/groups/{GRUPPE}/overview", headers=h)).json()["slots"]


async def _stunde(client, h, slot_id, titel="Übersetzung"):
    ue = (await client.post(f"/planning/groups/{GRUPPE}/units", headers=h,
                            json={"titel": "Zahnräder", "farbe": 0})).json()["id"]
    stunde = (await client.post(f"/planning/units/{ue}/lessons", headers=h,
                                json={"titel": titel, "slot_id": slot_id})).json()["id"]
    resp = await client.patch(f"/planning/lessons/{stunde}", headers=h, json={"phasen": [
        {"name": "Einstieg", "dauer_min": 10}, {"name": "Erarbeitung", "dauer_min": 20},
        {"name": "Sicherung", "dauer_min": 10},
    ]})
    assert resp.status_code == 200, resp.text
    return stunde


async def _phasen(client, h, stunde):
    return (await client.get(f"/context/nodes/{stunde}", headers=h)).json()["metadata"]["phasen"]


async def _wie_der_planer_speichern(client, h, stunde, aendern=None, phasen=None):
    """Nur die Schemafelder zurückschicken — so, wie `lessons/[nodeId]/+page.svelte` mappt."""
    phasen = phasen if phasen is not None else [
        {k: p.get(k) for k in SCHEMAFELDER} for p in await _phasen(client, h, stunde)]
    for p in phasen:
        p.update((aendern or {}).get(p.get("name"), {}))
    resp = await client.patch(f"/planning/lessons/{stunde}", headers=h, json={"phasen": phasen})
    assert resp.status_code == 200, resp.text


def _sitzungen(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_nachbereitung_ueberlebt_das_speichern_im_planer(test_client, auth_headers, gruppe, async_engine):
    h = auth_headers
    slot = (await _slots(test_client, h))[0]["id"]
    stunde = await _stunde(test_client, h, slot)
    erarbeitung = next(p["id"] for p in await _phasen(test_client, h, stunde) if p["name"] == "Erarbeitung")

    resp = await test_client.post(f"/planning/slots/{slot}/review", headers=h,
                                  json={"phasen_status": {erarbeitung: "offen"}})
    assert resp.status_code == 200, resp.text
    assert [p["status"] for p in await _phasen(test_client, h, stunde)] == ["erledigt", "offen", "erledigt"]

    # Speichern mit geänderter Beschreibung — bis 0.12 danach None / None / None.
    await _wie_der_planer_speichern(test_client, h, stunde,
                                    aendern={"Erarbeitung": {"beschreibung": "AB Übersetzung"}})
    phasen = await _phasen(test_client, h, stunde)
    assert [p["status"] for p in phasen] == ["erledigt", "offen", "erledigt"]
    assert phasen[1]["beschreibung"] == "AB Übersetzung"

    async with _sitzungen(async_engine)() as db:
        ctx = await build_reflow_context(db, GRUPPE, trigger="open_phases", slot_ids=[slot])
    assert [p.name for p in ctx.offene_phasen.phasen] == ["Erarbeitung"]


@pytest.mark.asyncio
async def test_streichen_bleibt_und_name_und_dauer_gehoeren_dem_editor(
    test_client, auth_headers, gruppe, async_engine
):
    h = auth_headers
    slot = (await _slots(test_client, h))[1]["id"]
    stunde = await _stunde(test_client, h, slot)
    sicherung = next(p["id"] for p in await _phasen(test_client, h, stunde) if p["name"] == "Sicherung")

    async with _sitzungen(async_engine)() as db:
        ergebnis = await apply_operations(
            db, GRUPPE, [StrikePhase(op="strike_phase", lesson_id=stunde, phase_id=sicherung)],
            summary="Sicherung gestrichen")
    assert not ergebnis.errors

    await _wie_der_planer_speichern(test_client, h, stunde,
                                    aendern={"Sicherung": {"name": "Sicherung kurz", "dauer_min": 5}})
    gestrichen = next(p for p in await _phasen(test_client, h, stunde) if p["id"] == sicherung)
    assert gestrichen["status"] == "gestrichen" and gestrichen["kuerzung"] is True
    assert gestrichen["name"] == "Sicherung kurz" and gestrichen["dauer_min"] == 5


@pytest.mark.asyncio
async def test_uebertragsmarke_bleibt(test_client, auth_headers, gruppe, async_engine):
    h = auth_headers
    slots = await _slots(test_client, h)
    quelle = await _stunde(test_client, h, slots[2]["id"], "Quelle")
    ziel = await _stunde(test_client, h, slots[3]["id"], "Ziel")
    erarbeitung = next(p["id"] for p in await _phasen(test_client, h, quelle) if p["name"] == "Erarbeitung")

    async with _sitzungen(async_engine)() as db:
        ergebnis = await apply_operations(db, GRUPPE, [TransferPhases(
            op="transfer_phases", from_lesson_id=quelle, to_lesson_id=ziel, phase_ids=[erarbeitung])],
            summary="Erarbeitung übertragen")
    assert not ergebnis.errors

    await _wie_der_planer_speichern(test_client, h, ziel)
    uebertragen = next(p for p in await _phasen(test_client, h, ziel) if p["id"] == erarbeitung)
    assert uebertragen["uebertrag_von"] == quelle


@pytest.mark.asyncio
async def test_neue_phase_ohne_felder_weggelassene_phase_weg(test_client, auth_headers, gruppe):
    h = auth_headers
    slot = (await _slots(test_client, h))[4]["id"]
    stunde = await _stunde(test_client, h, slot)
    vorher = await _phasen(test_client, h, stunde)
    await test_client.post(f"/planning/slots/{slot}/review", headers=h, json={"phasen_status": {}})

    # Einstieg bleibt, Erarbeitung und Sicherung fallen weg, eine neue Phase kommt dazu.
    behalten = {k: vorher[0].get(k) for k in SCHEMAFELDER}
    await _wie_der_planer_speichern(test_client, h, stunde,
                                    phasen=[behalten, {"name": "Neu", "dauer_min": 15}])
    nachher = await _phasen(test_client, h, stunde)
    assert [p["name"] for p in nachher] == ["Einstieg", "Neu"]
    assert nachher[0]["status"] == "erledigt"
    assert "status" not in nachher[1]   # auch kein null


@pytest.mark.asyncio
async def test_planungsassistent_behaelt_den_status(test_client, auth_headers, gruppe, async_engine):
    from types import SimpleNamespace

    from app.chat.tools import ToolContext
    from app.planning.assistant_tools import _handle_update_lesson_phases

    h = auth_headers
    slot = (await _slots(test_client, h))[5]["id"]
    stunde = await _stunde(test_client, h, slot)
    phasen = await _phasen(test_client, h, stunde)
    await test_client.post(f"/planning/slots/{slot}/review", headers=h,
                           json={"phasen_status": {phasen[1]["id"]: "offen"}})

    async with _sitzungen(async_engine)() as db:
        ctx = ToolContext(db=db, user=SimpleNamespace(sub=TEACHER1_PSEUDO), group_id=GRUPPE,
                          conversation_id=None)
        aus = await _handle_update_lesson_phases({"node_id": stunde, "phasen": [
            {"id": phasen[1]["id"], "name": "Erarbeitung (überarbeitet)", "dauer_min": 25},
            {"name": "Vertiefung", "dauer_min": 10, "prio": "vertiefung"},
        ]}, ctx)
    assert "error" not in aus, aus

    nachher = await _phasen(test_client, h, stunde)
    assert nachher[0]["status"] == "offen" and nachher[0]["name"] == "Erarbeitung (überarbeitet)"
    assert "status" not in nachher[1]
