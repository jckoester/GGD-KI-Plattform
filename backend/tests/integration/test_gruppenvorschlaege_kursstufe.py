"""Vorschläge „Klasse × Fach" entstehen nicht für die Kursstufe (Jan, 19.09.2026).

Der Jahrgang zerfällt dort in Kurse, die quer zu den Klassen liegen — „11 × Chemie" ist
keine Lerngruppe, sondern ein ganzer Jahrgang. Wer den Vorschlag annimmt, legt eine Gruppe
an, die es nicht gibt.

Erkannt wird die Kursstufe an der **Bezeichnung** (`ist_kursstufe`), nicht an einer
Jahrgangsliste: Sek I trägt immer ein Buchstabensuffix (`5A`…`10D`), die Kursstufe heißt
schlicht `11`/`12` — in G9 `12`/`13`, verbreitet auch `J1`/`K1`. Damit trägt die Regel
beide Schularten ohne Konfiguration.
"""
import pytest
import pytest_asyncio
from sqlalchemy import delete, insert, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Group, GroupMembership, Subject
from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio

KLASSEN = ["9A", "11", "J1", "10D", "13"]


@pytest_asyncio.fixture
async def aufbau(async_engine):
    """Eine Fachschaft und fünf „Klassen" — Sek I und Kursstufe gemischt."""
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    ids = []
    async with factory() as s:
        fach = Subject(name="KursstufeChemie", slug="ks-chemie-test")
        s.add(fach)
        await s.flush()
        fach_id = fach.id

        fs = Group(name="FS KursstufeChemie", slug="fs-ks-chemie-test",
                   type="subject_department", subject_id=fach_id)
        s.add(fs)
        await s.flush()
        ids.append(fs.id)

        for name in KLASSEN:
            k = Group(name=name, slug=f"ks-test-{name.lower()}", type="school_class")
            s.add(k)
            await s.flush()
            ids.append(k.id)

        for gid in ids:
            await s.execute(insert(GroupMembership).values(
                group_id=gid, pseudonym=TEACHER1_PSEUDO, role_in_group="teacher"))
        await s.commit()
    yield fach_id
    async with factory() as s:
        await s.execute(delete(GroupMembership).where(GroupMembership.group_id.in_(ids)))
        await s.execute(delete(Group).where(Group.id.in_(ids)))
        await s.execute(delete(Subject).where(Subject.id == fach_id))
        await s.commit()


async def _vorschlaege(client, headers, fach_id) -> set[str]:
    resp = await client.get("/groups/teaching/potential", headers=headers)
    assert resp.status_code == 200, resp.text
    return {i["class_name"] for i in resp.json()["items"] if i["subject_id"] == fach_id}


async def test_nur_sek_i_wird_vorgeschlagen(test_client, auth_headers, aufbau):
    assert await _vorschlaege(test_client, auth_headers, aufbau) == {"9A", "10D"}


@pytest.mark.parametrize("kursstufe", ["11", "J1", "13"])
async def test_keine_kursstufe(test_client, auth_headers, aufbau, kursstufe):
    """`13` deckt G9 mit ab — die Regel hängt an der Schreibweise, nicht am Jahrgang."""
    assert kursstufe not in await _vorschlaege(test_client, auth_headers, aufbau)
