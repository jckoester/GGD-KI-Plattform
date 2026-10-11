"""Die Ergebnisse der Planungswerkzeuge lassen sich als JSON ans Modell geben.

⚠️ **Gefunden 11.10.2026** bei der Messung zu Schritt 8 von Päckchen A: `get_plan_balance`
lieferte die Kennung einer Einheit als UUID-Objekt (`model_dump()` ohne `mode="json"`). Der
Chat scheiterte an `json.dumps`, der Antwortstrom riss ab — bei jeder Gruppe mit Einheit,
seit es den Jahresplanungs-Assistenten gibt. Die Unit-Tests sahen es nicht: Sie rufen die
Werkzeuge ohne Einheit auf, und dann ist die Liste leer.
"""
import json
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import psycopg2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import LessonSlot
from tests.integration.conftest import TEACHER1_PSEUDO

GRUPPE = 794


@pytest.fixture(scope="module")
def gruppe(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) VALUES (%s, %s, %s, 0) "
                    "ON CONFLICT (id) DO NOTHING", (GRUPPE, f"json-{GRUPPE}", f"JSON {GRUPPE}"))
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) VALUES "
                    "(%s, %s, %s, 'teaching_group', %s) ON CONFLICT (id) DO NOTHING",
                    (GRUPPE, f"9j JSON {GRUPPE}", f"json-{GRUPPE}", GRUPPE))
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                    "VALUES (%s, %s, 'teacher', 'eigen') ON CONFLICT DO NOTHING", (GRUPPE, TEACHER1_PSEUDO))
    conn.commit()
    yield
    with conn.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE read_scope_group_id = %s OR write_scope_group_id = %s",
                    (GRUPPE, GRUPPE))
        cur.execute("DELETE FROM groups WHERE id = %s", (GRUPPE,))
        cur.execute("DELETE FROM subjects WHERE id = %s", (GRUPPE,))
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_werkzeuge_mit_bilanz_liefern_json(gruppe, async_engine):
    from app.chat.tools import ToolContext
    from app.planning.assistant_tools import (
        _handle_assign_slots_to_unit,
        _handle_create_teaching_unit,
        _handle_get_plan_balance,
    )

    sitzungen = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    slot_id = uuid4()
    async with sitzungen() as db:
        db.add(LessonSlot(id=slot_id, group_id=GRUPPE, date=date(2031, 6, 2), halbjahr=2,
                          periods=1, start_period=1, kategorie="unterricht"))
        await db.commit()
        ctx = ToolContext(db=db, user=SimpleNamespace(sub=TEACHER1_PSEUDO, roles=["teacher"]),
                          group_id=GRUPPE, conversation_id=None)

        angelegt = await _handle_create_teaching_unit({"titel": "Potenzen"}, ctx)
        zugewiesen = await _handle_assign_slots_to_unit(
            {"unit_node_id": angelegt["ue_node_id"], "slot_ids": [str(slot_id)]}, ctx)
        bilanz = await _handle_get_plan_balance({}, ctx)

    assert bilanz["items"], "ohne Einheit in der Bilanz prüft der Test nichts"
    for ergebnis in (angelegt, zugewiesen, bilanz):
        json.dumps(ergebnis)
