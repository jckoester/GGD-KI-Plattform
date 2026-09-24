"""Den Jahrgang einer Unterrichtsgruppe festlegen und zurücknehmen (Paket 4, AP3).

⚠️ **Warum es die Festlegung gibt.** Der Jahrgang kam ausschließlich aus
`group_source_classes`. Gruppen aus dem Stundenplan und Kursstufenkurse tragen dort
nichts — und ohne Jahrgang bot die Curriculum-Auflösung **alle** Curricula des Fachs an,
einem Abi-28-Kurs also „CH Kl. 8" (Befund Jan, 24.09.2026).

Abgeleitet wird weiterhin (`app/groups/jahrgang.py`); diese Spalte ist die **Korrektur**
für alles, was die Ableitung nicht trifft — dasselbe Muster wie `erbt_mitglieder`.
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
        gid = (await s.execute(text(
            "INSERT INTO groups (name, slug, type) "
            "VALUES ('jg-testkurs', 'jg-testkurs', 'teaching_group') RETURNING id"
        ))).scalar_one()
        await s.execute(insert(GroupMembership).values(
            group_id=gid, pseudonym=TEACHER1_PSEUDO, role_in_group="teacher"))
        await s.commit()
    yield gid
    async with factory() as s:
        await s.execute(delete(GroupMembership).where(GroupMembership.group_id == gid))
        await s.execute(delete(Group).where(Group.id == gid))
        await s.commit()


def _pfad(gid):
    return f"/groups/teaching/{gid}/jahrgang"


async def test_neue_gruppe_hat_keine_festlegung(test_client, auth_headers, gruppe):
    """`null` heißt „nicht festgelegt", nicht „hat keinen" — dann wird abgeleitet."""
    resp = await test_client.get("/groups/me", headers=auth_headers)
    meine = {g["id"]: g for g in resp.json()["items"]}
    assert meine[gruppe]["jahrgang"] is None


async def test_festlegen_und_zuruecknehmen(test_client, auth_headers, gruppe):
    resp = await test_client.patch(_pfad(gruppe), json={"jahrgang": 11},
                                   headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["jahrgang"] == 11

    # ⚠️ **`null` ist kein Fehler, sondern eine Rücknahme.** Eine versehentlich gesetzte
    # Zahl muss sich loswerden lassen, ohne dass jemand raten muss, welcher Wert der
    # „richtige" war — danach leitet die Plattform wieder ab.
    resp = await test_client.patch(_pfad(gruppe), json={"jahrgang": None},
                                   headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["jahrgang"] is None


@pytest.mark.parametrize("wert", [0, 14, -1, 99])
async def test_unplausible_stufe_wird_abgewiesen(test_client, auth_headers, gruppe, wert):
    """Ohne Schranke würde aus einem Tippfehler eine Zahl, die niemandem auffällt."""
    resp = await test_client.patch(_pfad(gruppe), json={"jahrgang": wert},
                                   headers=auth_headers)
    assert resp.status_code == 422, resp.text


async def test_fremde_gruppe_darf_niemand_setzen(test_client, auth_headers_teacher2, gruppe):
    resp = await test_client.patch(_pfad(gruppe), json={"jahrgang": 11},
                                   headers=auth_headers_teacher2)
    assert resp.status_code == 403, resp.text


async def test_die_festlegung_wirkt_auf_die_curriculum_aufloesung(
    test_client, auth_headers, gruppe, async_engine
):
    """⚠️ **Der Datenweg, nicht nur der Endpunkt.**

    Dass die Spalte gesetzt wird, ist die halbe Zusage; die andere ist, dass die
    Auflösung sie auch liest. Getrennt geprüft wäre beides grün und die Wirkung trotzdem
    keine — genau so ist am selben Tag ein toter Link entstanden.
    """
    from app.planning.curriculum_resolver import group_grade

    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        assert await group_grade(s, gruppe) is None, "Vorbedingung: nichts ableitbar."

    await test_client.patch(_pfad(gruppe), json={"jahrgang": 11}, headers=auth_headers)

    async with factory() as s:
        assert await group_grade(s, gruppe) == 11
