"""Nur Stunden und Einheiten der eigenen Gruppe in einen Slot (Patch 0.12.x).

Bis 0.12.0 setzten vier Wege die Verweise eines Slots ungeprüft: `PATCH
/planning/slots/{id}` (`stunde_node_id`, `ue_node_id`), die Planungs-Operation
`set_unit` und das Werkzeug `assign_slots_to_unit` — die letzten beiden mit IDs, die das
Modell liefert. Eine Stunde der Gruppe 10 stand so im Plan der Gruppe 9, und wer sie dort
bearbeitete, änderte still den Plan der anderen. Regel und Begründung:
`app/planning/zuordnung.py`.
"""
import unittest.mock as m
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import psycopg2
import pytest

from app.chat.tools import ToolContext
from app.db.models import ContextNode, LessonSlot
from app.planning.assistant_tools import (
    _handle_apply_plan_operations,
    _handle_assign_slots_to_unit,
)

TEACHER1_PSEUDO = "teacher1-pseudo"
EIGENE, FREMDE = 330, 331


@pytest.fixture(scope="module")
def zwei_gruppen(db_url, run_migrations):
    """Zwei Gruppen desselben Fachs, beide bei derselben Lehrkraft — der schwierige Fall:
    Auch eine Gruppe, in der man selbst unterrichtet, ist eine *andere* Gruppe."""
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) "
                    "VALUES (330, 'nwt-zuordnung', 'NwT Zuordnung', 0) ON CONFLICT (id) DO NOTHING")
        for gid, name in ((EIGENE, "NwT 9 Zuordnung"), (FREMDE, "NwT 10 Zuordnung")):
            cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                        "VALUES (%s, %s, %s, 'teaching_group', 330) ON CONFLICT (id) DO NOTHING",
                        (gid, name, f"nwt-zuordnung-{gid}"))
            cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                        "VALUES (%s, %s, 'teacher', 'eigen') ON CONFLICT DO NOTHING",
                        (gid, TEACHER1_PSEUDO))
    conn.commit()
    conn.close()


# ── PATCH /planning/slots/{id} ───────────────────────────────────────────────

async def _slots(client, headers, gid):
    await client.put(f"/planning/groups/{gid}/pattern", headers=headers,
                     json={"halbjahr": 1, "patterns": [{"weekday": 0, "start_period": 3, "periods": 1}]})
    await client.post(f"/planning/groups/{gid}/slots/generate", headers=headers,
                      json={"halbjahr": 1, "regenerate": True})
    return (await client.get(f"/planning/groups/{gid}/overview", headers=headers)).json()["slots"]


async def _einheit(client, headers, gid):
    resp = await client.post(f"/planning/groups/{gid}/units", headers=headers,
                             json={"titel": f"Zahnräder {gid}", "farbe": 1})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _stunde(client, headers, ue_id, slot_id):
    resp = await client.post(f"/planning/units/{ue_id}/lessons", headers=headers,
                             json={"titel": "Zahnräder und Übersetzung", "slot_id": slot_id})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _patch(client, headers, slot_id, **felder):
    return await client.patch(f"/planning/slots/{slot_id}", headers=headers, json=felder)


@pytest.mark.asyncio
async def test_eigene_stunde_und_einheit_lassen_sich_setzen_und_loesen(
    test_client, auth_headers, zwei_gruppen
):
    slots = await _slots(test_client, auth_headers, EIGENE)
    ue = await _einheit(test_client, auth_headers, EIGENE)
    stunde = await _stunde(test_client, auth_headers, ue, slots[0]["id"])

    # Dieselbe Stunde in einen zweiten Slot derselben Gruppe: erlaubt.
    resp = await _patch(test_client, auth_headers, slots[1]["id"], ue_node_id=ue, stunde_node_id=stunde)
    assert resp.status_code == 200, resp.text
    assert resp.json()["stunde_node_id"] == stunde

    # Lösen geht immer.
    resp = await _patch(test_client, auth_headers, slots[1]["id"], stunde_node_id=None, ue_node_id=None)
    assert resp.status_code == 200
    assert resp.json()["stunde_node_id"] is None and resp.json()["ue_node_id"] is None


@pytest.mark.asyncio
async def test_stunde_einer_anderen_gruppe_wird_abgelehnt(test_client, auth_headers, zwei_gruppen):
    eigene_slots = await _slots(test_client, auth_headers, EIGENE)
    fremde_slots = await _slots(test_client, auth_headers, FREMDE)
    fremde_ue = await _einheit(test_client, auth_headers, FREMDE)
    fremde_stunde = await _stunde(test_client, auth_headers, fremde_ue, fremde_slots[0]["id"])

    ziel = eigene_slots[2]["id"]
    resp = await _patch(test_client, auth_headers, ziel, stunde_node_id=fremde_stunde)
    assert resp.status_code == 422
    assert "keine Unterrichtsstunde dieser Gruppe" in resp.json()["detail"]

    resp = await _patch(test_client, auth_headers, ziel, ue_node_id=fremde_ue)
    assert resp.status_code == 422
    assert "keine Unterrichtseinheit dieser Gruppe" in resp.json()["detail"]

    # Nichts davon ist angekommen.
    slots = (await test_client.get(f"/planning/groups/{EIGENE}/overview", headers=auth_headers)).json()["slots"]
    zielslot = next(s for s in slots if s["id"] == ziel)
    assert zielslot["stunde_node_id"] is None and zielslot["ue_node_id"] is None


@pytest.mark.asyncio
async def test_falscher_typ_wird_abgelehnt(test_client, auth_headers, zwei_gruppen):
    """Eine Einheit ist keine Stunde — auch in der eigenen Gruppe nicht."""
    slots = await _slots(test_client, auth_headers, EIGENE)
    ue = await _einheit(test_client, auth_headers, EIGENE)
    resp = await _patch(test_client, auth_headers, slots[3]["id"], stunde_node_id=ue)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unbekannte_id_meldet_dasselbe_wie_eine_fremde(test_client, auth_headers, zwei_gruppen):
    """Wer eine ID einer fremden Gruppe schickt, soll nicht erfahren, ob es sie gibt."""
    slots = await _slots(test_client, auth_headers, EIGENE)
    unbekannt = str(uuid4())
    resp = await _patch(test_client, auth_headers, slots[4]["id"], stunde_node_id=unbekannt)
    assert resp.status_code == 422
    assert resp.json()["detail"] == f"{unbekannt} ist keine Unterrichtsstunde dieser Gruppe."


# ── Die beiden Wege des Assistenten ──────────────────────────────────────────

def _ctx(db_session):
    return ToolContext(db=db_session, user=SimpleNamespace(sub="teach-zuordnung"),
                       group_id=EIGENE, conversation_id=None)


def _einheit_knoten(gid):
    return ContextNode(
        id=uuid4(), category="artifact", content_type="unterrichtseinheit", title=f"UE {gid}",
        read_scope="group_teachers", write_scope="group_teachers",
        read_scope_group_id=gid, write_scope_group_id=gid, status="active",
    )


def _patch_commit(db_session):
    async def _commit_als_flush():
        await db_session.flush()
    return m.patch.object(db_session, "commit", new=_commit_als_flush)


@pytest.mark.asyncio
async def test_operation_set_unit_lehnt_fremde_einheit_ab(db_session, zwei_gruppen):
    fremd, eigen = _einheit_knoten(FREMDE), _einheit_knoten(EIGENE)
    slot = LessonSlot(id=uuid4(), group_id=EIGENE, date=date(2026, 9, 14), halbjahr=1,
                      periods=1, start_period=3, kategorie="unterricht")
    db_session.add_all([fremd, eigen, slot])
    await db_session.flush()

    with _patch_commit(db_session):
        aus = await _handle_apply_plan_operations({
            "operations": [{"op": "set_unit", "slot_id": str(slot.id), "unit_node_id": str(fremd.id)}],
            "summary": "fremde UE",
        }, _ctx(db_session))
    assert not aus.get("ok")
    assert any("keine Unterrichtseinheit dieser Gruppe" in f for f in aus["errors"])
    assert slot.ue_node_id is None

    with _patch_commit(db_session):
        aus = await _handle_apply_plan_operations({
            "operations": [{"op": "set_unit", "slot_id": str(slot.id), "unit_node_id": str(eigen.id)}],
            "summary": "eigene UE",
        }, _ctx(db_session))
    assert aus["ok"] is True
    assert slot.ue_node_id == eigen.id


@pytest.mark.asyncio
async def test_werkzeug_assign_slots_to_unit_lehnt_fremde_einheit_ab(db_session, zwei_gruppen):
    fremd = _einheit_knoten(FREMDE)
    slot = LessonSlot(id=uuid4(), group_id=EIGENE, date=date(2026, 9, 21), halbjahr=1,
                      periods=1, start_period=3, kategorie="unterricht")
    db_session.add_all([fremd, slot])
    await db_session.flush()

    with _patch_commit(db_session):
        aus = await _handle_assign_slots_to_unit(
            {"unit_node_id": str(fremd.id), "slot_ids": [str(slot.id)]}, _ctx(db_session))
    assert "keine Unterrichtseinheit dieser Gruppe" in aus.get("error", "")
    assert slot.ue_node_id is None
