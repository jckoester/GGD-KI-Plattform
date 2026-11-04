"""`GET /groups/me` liefert den wirksamen Jahrgang (0.32.1, Vorschau-Dialog). Erfordert TEST_DATABASE_URL."""
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Group, GroupMembership, GroupSourceClass, Subject
from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def gruppen(async_engine):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    k = uuid.uuid4().hex[:8]
    async with fabrik() as db:
        fach = Subject(slug=f"gmj-{k}", name="Jahrgangsfach")
        db.add(fach)
        await db.flush()

        def ug(name, **mehr):
            return Group(name=name, slug=f"gmj-{uuid.uuid4().hex[:8]}", type="teaching_group",
                         subject_id=fach.id, **mehr)

        fest = ug("Robotik fest", jahrgang=10)
        aus_name = ug("Chemie 8b")
        aus_klasse = ug("Kurs ohne Stufe im Namen")
        unbekannt = ug("Robotik")
        klasse = Group(name="7c", slug=f"gmj-k-{k}", type="school_class")
        db.add_all([fest, aus_name, aus_klasse, unbekannt, klasse])
        await db.flush()
        db.add(GroupSourceClass(group_id=aus_klasse.id, class_group_id=klasse.id))
        for g in (fest, aus_name, aus_klasse, unbekannt, klasse):
            db.add(GroupMembership(group_id=g.id, pseudonym=TEACHER1_PSEUDO,
                                   role_in_group="teacher", herkunft="eigen"))
        await db.commit()
        ids = {"fest": fest.id, "aus_name": aus_name.id, "aus_klasse": aus_klasse.id,
               "unbekannt": unbekannt.id, "klasse": klasse.id}
    yield ids
    async with fabrik() as db:
        await db.execute(sa.delete(Group).where(Group.id.in_(list(ids.values()))))
        await db.execute(sa.delete(Subject).where(Subject.id == fach.id))
        await db.commit()


async def test_wirksamer_jahrgang(test_client, auth_headers, gruppen):
    antwort = await test_client.get("/groups/me", headers=auth_headers)
    assert antwort.status_code == 200, antwort.text
    je_id = {g["id"]: g for g in antwort.json()["items"]}
    assert je_id[gruppen["fest"]]["jahrgang_wirksam"] == 10
    assert je_id[gruppen["aus_name"]]["jahrgang_wirksam"] == 8
    assert je_id[gruppen["aus_klasse"]]["jahrgang_wirksam"] == 7
    assert je_id[gruppen["unbekannt"]]["jahrgang_wirksam"] is None
    # Die gespeicherte Festlegung bleibt daneben unverändert.
    assert je_id[gruppen["aus_name"]]["jahrgang"] is None
    assert je_id[gruppen["klasse"]]["jahrgang_wirksam"] is None, "nur Unterrichtsgruppen"
