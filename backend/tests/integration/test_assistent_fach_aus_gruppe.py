"""Fach aus der Gruppe (0.27, Plan Schritt 4, F2 a).

Bei Gruppen-Scope setzt der Server das Fach der Gruppe und überschreibt eine Eingabe — beim
Anlegen und beim Ändern. Eine Gruppe ohne Fach (AG) lässt die Eingabe stehen; ohne
Gruppen-Scope gilt sie ohnehin. Erfordert TEST_DATABASE_URL.
"""
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Assistant, Group, Subject

pytestmark = pytest.mark.asyncio

PRAEFIX = "FAG "


@pytest_asyncio.fixture
async def bestand(async_engine):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        chemie = Subject(slug="fag-chemie", name="FAG Chemie")
        deutsch = Subject(slug="fag-deutsch", name="FAG Deutsch")
        db.add_all([chemie, deutsch])
        await db.flush()
        gruppe = Group(name="FAG 8c Chemie", slug="fag-8c-chemie", type="teaching_group", subject_id=chemie.id)
        ag = Group(name="FAG Robotik-AG", slug="fag-robotik", type="activity_group")
        db.add_all([gruppe, ag])
        await db.commit()
        werte = {"chemie": chemie.id, "deutsch": deutsch.id, "gruppe": gruppe.id, "ag": ag.id}
    yield werte
    async with fabrik() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.name.like(f"{PRAEFIX}%")))
        await db.execute(sa.delete(Group).where(Group.slug.like("fag-%")))
        await db.execute(sa.delete(Subject).where(Subject.slug.like("fag-%")))
        await db.commit()


async def _anlegen(client, headers, **mehr):
    resp = await client.post("/assistants", json={
        "name": PRAEFIX + "A", "system_prompt": "P", "audience": "student", **mehr,
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_anlegen_nimmt_das_fach_der_gruppe(test_client, auth_headers, bestand):
    a = await _anlegen(test_client, auth_headers, scope="teaching_group",
                       scope_group_id=bestand["gruppe"], subject_id=bestand["deutsch"])
    assert a["subject_id"] == bestand["chemie"]


async def test_aendern_ueberschreibt_ein_abweichendes_fach(test_client, auth_headers, bestand):
    a = await _anlegen(test_client, auth_headers, subject_id=bestand["deutsch"])
    assert a["subject_id"] == bestand["deutsch"]          # privat: die Eingabe gilt
    resp = await test_client.patch(f"/assistants/{a['id']}", json={
        "scope": "teaching_group", "scope_group_id": bestand["gruppe"]}, headers=auth_headers)
    assert resp.json()["subject_id"] == bestand["chemie"]
    resp = await test_client.patch(f"/assistants/{a['id']}", json={"subject_id": bestand["deutsch"]},
                                   headers=auth_headers)
    assert resp.json()["subject_id"] == bestand["chemie"]


async def test_gruppe_ohne_fach_laesst_die_eingabe_stehen(test_client, auth_headers, bestand):
    a = await _anlegen(test_client, auth_headers, scope="activity_group",
                       scope_group_id=bestand["ag"], subject_id=bestand["deutsch"])
    assert a["subject_id"] == bestand["deutsch"]
