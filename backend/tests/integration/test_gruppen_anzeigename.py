"""Anzeigename einer Unterrichtsgruppe (Sammlung 0.10.2, Punkt 3).

Die Namen kommen aus dem Schulkonto (`unterricht.ch2-ks-abi28` → `ch2-ks-abi28`). Eine
Lehrkraft darf ihrer Gruppe einen lesbaren Namen geben — der rohe bleibt daneben stehen,
weil er dem Schulkonto gehört und die Stundenplan-Zuordnung auf ihm rechnet.
"""
import pytest
import pytest_asyncio
from sqlalchemy import delete, insert, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Group, GroupMembership
from tests.integration.conftest import TEACHER1_PSEUDO, TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def gruppe(async_engine):
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        res = await s.execute(text(
            "INSERT INTO groups (name, slug, type, sso_group_id) "
            "VALUES ('ch2-ks-abi28', 'anz-ch2', 'teaching_group', 'unterricht.ch2-ks-abi28') "
            "RETURNING id"
        ))
        gid = res.scalar_one()
        await s.execute(insert(GroupMembership).values(
            group_id=gid, pseudonym=TEACHER1_PSEUDO, role_in_group="teacher"))
        await s.commit()
    yield gid
    async with factory() as s:
        await s.execute(delete(GroupMembership).where(GroupMembership.group_id == gid))
        await s.execute(delete(Group).where(Group.id == gid))
        await s.commit()


async def _meine(client, headers) -> dict:
    resp = await client.get("/groups/me", headers=headers)
    assert resp.status_code == 200, resp.text
    return {g["id"]: g for g in resp.json()["items"]}


async def test_ohne_anzeigename_gilt_der_name_aus_dem_schulkonto(
    test_client, auth_headers, gruppe
):
    eintrag = (await _meine(test_client, auth_headers))[gruppe]
    assert eintrag["name"] == "ch2-ks-abi28"
    assert eintrag["display_name"] is None


async def test_gesetzter_anzeigename_ersetzt_den_namen_in_der_antwort(
    test_client, auth_headers, gruppe
):
    """Aufgelöst wird im Backend: 41 Stellen im Frontend zeigen einen Gruppennamen."""
    resp = await test_client.patch(
        f"/groups/teaching/{gruppe}/name",
        json={"display_name": "  Chemie LK Abi 28  "},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Chemie LK Abi 28", "Leerzeichen werden abgeschnitten"

    eintrag = (await _meine(test_client, auth_headers))[gruppe]
    assert eintrag["name"] == "Chemie LK Abi 28"
    assert eintrag["display_name"] == "Chemie LK Abi 28"


async def test_leerer_name_nimmt_die_umbenennung_zurueck(
    test_client, auth_headers, gruppe
):
    await test_client.patch(f"/groups/teaching/{gruppe}/name",
                            json={"display_name": "Irgendwas"}, headers=auth_headers)
    resp = await test_client.patch(f"/groups/teaching/{gruppe}/name",
                                   json={"display_name": "   "}, headers=auth_headers)
    assert resp.status_code == 200
    eintrag = (await _meine(test_client, auth_headers))[gruppe]
    assert eintrag["name"] == "ch2-ks-abi28"
    assert eintrag["display_name"] is None


async def test_fremde_lehrkraft_darf_nicht_umbenennen(
    test_client, auth_headers_teacher2, gruppe
):
    """Dieselbe Bedingung wie bei der Jahresplanung: Mitglied mit Rolle `teacher`."""
    resp = await test_client.patch(
        f"/groups/teaching/{gruppe}/name",
        json={"display_name": "Nicht meine Gruppe"},
        headers=auth_headers_teacher2,
    )
    assert resp.status_code == 403


async def test_der_rohe_name_bleibt_in_der_datenbank(
    test_client, auth_headers, gruppe, async_engine
):
    """Die Stundenplan-Zuordnung rechnet auf ihm — sie ist damit gegen Umbenennen immun."""
    await test_client.patch(f"/groups/teaching/{gruppe}/name",
                            json={"display_name": "CH Abi28"}, headers=auth_headers)
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        g = await s.get(Group, gruppe)
        assert g.name == "ch2-ks-abi28"
        assert g.display_name == "CH Abi28"
        assert g.anzeigename == "CH Abi28"
