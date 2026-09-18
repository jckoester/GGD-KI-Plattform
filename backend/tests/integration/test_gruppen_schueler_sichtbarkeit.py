"""Freigabe einer Unterrichtsgruppe für ihre Schüler:innen (Beta-Fachsichtbarkeit, Schritt 3).

Für einen begrenzten Testbetrieb: Nimmt eine Lehrkraft mit einem Teil ihrer Lerngruppen
teil, sollen ihre Schüler:innen nur die dazugehörigen Fächer sehen. Gelesen wird die
Freigabe erst bei `STUDENT_SUBJECTS_OPT_IN=true` — der **Endpunkt** arbeitet aber
unabhängig davon, damit eine Lehrkraft vorbereiten kann und beim Abschalten des Modus
nichts verloren geht. Genau das halten die Tests hier fest.

Der Wächter ist `require_group_teacher`, dieselbe Bedingung wie beim Anzeigenamen (0062)
und in der Jahresplanung.
"""
import pytest
import pytest_asyncio
from sqlalchemy import delete, insert, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Group, GroupMembership
from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def gruppe(async_engine):
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        res = await s.execute(text(
            "INSERT INTO groups (name, slug, type, sso_group_id) "
            "VALUES ('ch2-ks-abi28', 'sicht-ch2', 'teaching_group', 'unterricht.sicht-ch2') "
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


@pytest_asyncio.fixture
async def klasse(async_engine):
    """Eine Gruppe, die **keine** Unterrichtsgruppe ist — für den 404-Fall."""
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        res = await s.execute(text(
            "INSERT INTO groups (name, slug, type) "
            "VALUES ('9d', 'sicht-9d', 'school_class') RETURNING id"
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


def _pfad(gid: int) -> str:
    return f"/groups/teaching/{gid}/student-visible"


async def _meine(client, headers) -> dict:
    resp = await client.get("/groups/me", headers=headers)
    assert resp.status_code == 200, resp.text
    return {g["id"]: g for g in resp.json()["items"]}


async def test_neue_gruppe_ist_nicht_freigegeben(test_client, auth_headers, gruppe):
    """`false` als Vorgabe ist die sichere Richtung — nichts ist sichtbar, was nicht freigegeben wurde."""
    assert (await _meine(test_client, auth_headers))[gruppe]["student_visible"] is False


async def test_freigeben_und_zuruecknehmen(test_client, auth_headers, gruppe):
    resp = await test_client.patch(_pfad(gruppe), json={"student_visible": True},
                                   headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["student_visible"] is True
    assert (await _meine(test_client, auth_headers))[gruppe]["student_visible"] is True

    resp = await test_client.patch(_pfad(gruppe), json={"student_visible": False},
                                   headers=auth_headers)
    assert resp.status_code == 200
    assert (await _meine(test_client, auth_headers))[gruppe]["student_visible"] is False


async def test_der_endpunkt_haengt_nicht_am_betriebsschalter(
    test_client, auth_headers, gruppe, monkeypatch
):
    """Vorbereiten muss möglich sein, auch wenn der Modus gerade aus ist."""
    from app.api import groups as groups_module

    monkeypatch.setattr(groups_module.settings, "student_subjects_opt_in", False)
    resp = await test_client.patch(_pfad(gruppe), json={"student_visible": True},
                                   headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["student_visible"] is True


async def test_fremde_lehrkraft_darf_nicht_freigeben(
    test_client, auth_headers_teacher2, gruppe
):
    resp = await test_client.patch(_pfad(gruppe), json={"student_visible": True},
                                   headers=auth_headers_teacher2)
    assert resp.status_code == 403


async def test_schuelerin_darf_nicht_freigeben(test_client, auth_headers_student, gruppe):
    """Auch nicht als Mitglied — der Wächter verlangt die Rolle `teacher` in der Gruppe."""
    resp = await test_client.patch(_pfad(gruppe), json={"student_visible": True},
                                   headers=auth_headers_student)
    assert resp.status_code == 403


async def test_klasse_ist_keine_unterrichtsgruppe(test_client, auth_headers, klasse):
    """404 statt 403: Die Freigabe gibt es für Klassen und Fachschaften gar nicht."""
    resp = await test_client.patch(_pfad(klasse), json={"student_visible": True},
                                   headers=auth_headers)
    assert resp.status_code == 404
