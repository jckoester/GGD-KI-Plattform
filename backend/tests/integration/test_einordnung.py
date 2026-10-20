"""Der Entwurf eines Termins gehört zur Einheit des Termins (0.15, `app/planning/einordnung.py`).

Bis 0.15 zog nur das Anlegen eines Entwurfs die Kante `part_of` zur Einheit mit. Wer einem
Termin mit Entwurf nachträglich eine Einheit zuwies, änderte nur den Termin — die
Entwurfsansicht zeigte keine Einheit, der Stundenassistent bekam weder Einheit noch Kapitel.
Hier jeder Weg, auf dem sich die Einheit eines Termins ändert.
"""
from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg2
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ContextEdge, ContextNode, LessonSlot, SlotPlanSnapshot
from tests.integration.conftest import TEACHER1_PSEUDO

GRUPPE = 791


@pytest.fixture(scope="module")
def gruppe(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) VALUES (%s, %s, %s, 0) "
                    "ON CONFLICT (id) DO NOTHING", (GRUPPE, f"einordnung-{GRUPPE}", f"Einordnung {GRUPPE}"))
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) VALUES "
                    "(%s, %s, %s, 'teaching_group', %s) ON CONFLICT (id) DO NOTHING",
                    (GRUPPE, f"9e Einordnung {GRUPPE}", f"einordnung-{GRUPPE}", GRUPPE))
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                    "VALUES (%s, %s, 'teacher', 'eigen') ON CONFLICT DO NOTHING", (GRUPPE, TEACHER1_PSEUDO))
    conn.commit()
    yield conn
    with conn.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE read_scope_group_id = %s", (GRUPPE,))
        cur.execute("DELETE FROM groups WHERE id = %s", (GRUPPE,))
        cur.execute("DELETE FROM subjects WHERE id = %s", (GRUPPE,))
    conn.commit()
    conn.close()


def _sitzungen(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def _einheit(client, h, titel):
    resp = await client.post(f"/planning/groups/{GRUPPE}/units", headers=h, json={"titel": titel, "farbe": 0})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _termin_mit_entwurf(client, h, async_engine, tag: int):
    """Ein Termin ohne Einheit, dazu ein Entwurf — so wie vor dem Jahresplan angelegt."""
    slot_id = uuid4()
    async with _sitzungen(async_engine)() as db:
        db.add(LessonSlot(id=slot_id, group_id=GRUPPE, date=date(2031, 5, tag), halbjahr=2,
                          periods=2, start_period=3, kategorie="unterricht"))
        await db.commit()
    resp = await client.post(f"/planning/slots/{slot_id}/lesson", headers=h)
    assert resp.status_code == 201, resp.text
    return str(slot_id), resp.json()["id"]


async def _einheiten_des_entwurfs(async_engine, stunde) -> list[str]:
    async with _sitzungen(async_engine)() as db:
        return [str(i) for i in (await db.execute(
            sa.select(ContextEdge.to_node_id)
            .join(ContextNode, ContextNode.id == ContextEdge.to_node_id)
            .where(ContextEdge.from_node_id == UUID(stunde), ContextEdge.relation == "part_of",
                   ContextNode.content_type == "unterrichtseinheit")
        )).scalars()]


@pytest.mark.asyncio
async def test_jahresplan_zuordnung_zieht_den_entwurf_mit(test_client, auth_headers, gruppe, async_engine):
    """Zuweisen, umhängen, entfernen — der Entwurf folgt jedes Mal dem Termin."""
    h = auth_headers
    slot, stunde = await _termin_mit_entwurf(test_client, h, async_engine, 5)
    aromaten, energetik = await _einheit(test_client, h, "Aromaten"), await _einheit(test_client, h, "Energetik")
    assert await _einheiten_des_entwurfs(async_engine, stunde) == []

    for einheit, erwartet in ((aromaten, [aromaten]), (energetik, [energetik]), (None, [])):
        resp = await test_client.patch(f"/planning/slots/{slot}", headers=h, json={"ue_node_id": einheit})
        assert resp.status_code == 200, resp.text
        assert await _einheiten_des_entwurfs(async_engine, stunde) == erwartet

    # Und die Entwurfsansicht sieht es auch: Sie liest dieselbe Kante.
    await test_client.patch(f"/planning/slots/{slot}", headers=h, json={"ue_node_id": aromaten})
    ansicht = (await test_client.get(f"/planning/lessons/{stunde}", headers=h)).json()
    assert str(ansicht["ue"]["id"]) == aromaten


@pytest.mark.asyncio
async def test_der_stundenassistent_sieht_die_einheit(test_client, auth_headers, gruppe, async_engine):
    from app.chat.tools import ToolContext
    from app.planning.assistant_tools import _handle_get_lesson_detail

    h = auth_headers
    slot, stunde = await _termin_mit_entwurf(test_client, h, async_engine, 6)
    einheit = await _einheit(test_client, h, "Aromaten")
    await test_client.patch(f"/planning/slots/{slot}", headers=h, json={"ue_node_id": einheit})

    async with _sitzungen(async_engine)() as db:
        ctx = ToolContext(db=db, user=SimpleNamespace(sub=TEACHER1_PSEUDO), group_id=None, conversation_id=None)
        z = (await _handle_get_lesson_detail({"node_id": stunde}, ctx))["zusammenhang"]
    assert z["einheit"] == {"id": einheit, "titel": "Aromaten"}


@pytest.mark.asyncio
async def test_einen_entwurf_an_einen_termin_mit_einheit_haengen(test_client, auth_headers, gruppe, async_engine):
    """Die andere Richtung: Der Termin hat die Einheit schon, der Entwurf kommt dazu."""
    h = auth_headers
    alt, stunde = await _termin_mit_entwurf(test_client, h, async_engine, 7)
    # Ein Entwurf hängt an höchstens einem Termin (0.19) — erst am alten lösen.
    await test_client.patch(f"/planning/slots/{alt}", headers=h, json={"stunde_node_id": None})
    einheit = await _einheit(test_client, h, "Aromaten")
    ziel = uuid4()
    async with _sitzungen(async_engine)() as db:
        db.add(LessonSlot(id=ziel, group_id=GRUPPE, date=date(2031, 5, 8), halbjahr=2, periods=2,
                          start_period=3, kategorie="unterricht", ue_node_id=UUID(einheit)))
        await db.commit()

    resp = await test_client.patch(f"/planning/slots/{ziel}", headers=h, json={"stunde_node_id": stunde})
    assert resp.status_code == 200, resp.text
    assert await _einheiten_des_entwurfs(async_engine, stunde) == [einheit]


@pytest.mark.asyncio
async def test_jahresplan_assistent_weist_termine_zu(test_client, auth_headers, gruppe, async_engine):
    from app.planning.service import assign_slots_to_unit

    h = auth_headers
    slot, stunde = await _termin_mit_entwurf(test_client, h, async_engine, 11)
    einheit = await _einheit(test_client, h, "Aromaten")
    async with _sitzungen(async_engine)() as db:
        await assign_slots_to_unit(db, GRUPPE, SimpleNamespace(sub=TEACHER1_PSEUDO),
                                   UUID(einheit), [UUID(slot)])
    assert await _einheiten_des_entwurfs(async_engine, stunde) == [einheit]


@pytest.mark.asyncio
async def test_operation_einheit_setzen(test_client, auth_headers, gruppe, async_engine):
    from app.planning.operations import apply_operations, parse_operations

    h = auth_headers
    slot, stunde = await _termin_mit_entwurf(test_client, h, async_engine, 12)
    einheit = await _einheit(test_client, h, "Aromaten")
    async with _sitzungen(async_engine)() as db:
        ergebnis = await apply_operations(
            db, GRUPPE, parse_operations([{"op": "set_unit", "slot_id": slot, "unit_node_id": einheit}]),
            summary="Test", created_by=TEACHER1_PSEUDO)
        assert not ergebnis.errors, ergebnis.errors
    assert await _einheiten_des_entwurfs(async_engine, stunde) == [einheit]


@pytest.mark.asyncio
async def test_snapshot_wiederherstellen(test_client, auth_headers, gruppe, async_engine):
    """Der Snapshot vor dem Zuweisen kennt keine Einheit — danach auch der Entwurf nicht mehr."""
    h = auth_headers
    slot, stunde = await _termin_mit_entwurf(test_client, h, async_engine, 13)
    einheit = await _einheit(test_client, h, "Aromaten")
    await test_client.patch(f"/planning/slots/{slot}", headers=h, json={"ue_node_id": einheit})
    assert await _einheiten_des_entwurfs(async_engine, stunde) == [einheit]

    async with _sitzungen(async_engine)() as db:
        snapshot = (await db.execute(
            sa.select(SlotPlanSnapshot.id).where(SlotPlanSnapshot.group_id == GRUPPE,
                                                 SlotPlanSnapshot.reason == "edit")
            .order_by(SlotPlanSnapshot.created_at.desc()).limit(1)
        )).scalar_one()
    resp = await test_client.post(f"/planning/snapshots/{snapshot}/restore", headers=h)
    assert resp.status_code == 200, resp.text
    assert await _einheiten_des_entwurfs(async_engine, stunde) == []


@pytest.mark.asyncio
async def test_snapshot_mit_gleicher_einheit_und_anderem_entwurf(test_client, auth_headers, gruppe, async_engine):
    """Der Snapshot bringt einen anderen Entwurf zurück, die Einheit bleibt dieselbe. Im
    Snapshot stehen die Kennungen als Zeichenketten — ein Vergleich mit den UUIDs der Kanten
    hielt die richtige Kante für falsch und nahm dem Entwurf seine Einheit."""
    h = auth_headers
    slot, stunde = await _termin_mit_entwurf(test_client, h, async_engine, 14)
    einheit = await _einheit(test_client, h, "Aromaten")
    await test_client.patch(f"/planning/slots/{slot}", headers=h, json={"ue_node_id": einheit})
    anderer_termin, andere = await _termin_mit_entwurf(test_client, h, async_engine, 15)
    # Ein Entwurf hängt an höchstens einem Termin (0.19) — erst am anderen lösen.
    await test_client.patch(f"/planning/slots/{anderer_termin}", headers=h, json={"stunde_node_id": None})
    resp = await test_client.patch(f"/planning/slots/{slot}", headers=h, json={"stunde_node_id": andere})
    assert resp.status_code == 200, resp.text

    async with _sitzungen(async_engine)() as db:
        snapshot = (await db.execute(
            sa.select(SlotPlanSnapshot.id).where(SlotPlanSnapshot.group_id == GRUPPE,
                                                 SlotPlanSnapshot.reason == "edit")
            .order_by(SlotPlanSnapshot.created_at.desc()).limit(1)
        )).scalar_one()
    resp = await test_client.post(f"/planning/snapshots/{snapshot}/restore", headers=h)
    assert resp.status_code == 200, resp.text
    assert await _einheiten_des_entwurfs(async_engine, stunde) == [einheit]
