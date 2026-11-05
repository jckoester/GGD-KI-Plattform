"""Assistenten der Gruppe aus Schülersicht (0.32, Päckchen AJ, Plan Schritt 2).

Erfordert TEST_DATABASE_URL. Die Testdatenbank kennt weitere Assistenten; geprüft wird deshalb
immer, wo **die eigenen** dieses Tests landen, nicht die ganze Liste.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Assistant, Group, GroupMembership, Subject
from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio

KOLLEGIN = "schuelersicht-kollegin"


@pytest_asyncio.fixture
async def welt(async_engine):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    kennung = uuid.uuid4().hex[:8]
    async with fabrik() as db:
        fach = Subject(slug=f"ss-{kennung}", name="Schülersichtfach")
        db.add(fach)
        await db.flush()

        def gruppe(name, **mehr):
            return Group(name=name, slug=f"ss-{uuid.uuid4().hex[:8]}", type="teaching_group",
                         subject_id=fach.id, **mehr)

        g = gruppe("Robotik", jahrgang=9)          # festgelegt
        andere = gruppe("Robotik 2")                # fremd
        ohne = gruppe("Robotik ohne Stufe")         # nicht ableitbar
        abgeleitet = gruppe("Chemie 8b")            # aus dem Namen
        fachschaft = Group(name="FS", slug=f"fs-{kennung}", type="subject_department",
                           subject_id=fach.id)
        db.add_all([g, andere, ohne, abgeleitet, fachschaft])
        await db.flush()
        for grp in (g, ohne, abgeleitet):
            db.add(GroupMembership(group_id=grp.id, pseudonym=TEACHER1_PSEUDO,
                                   role_in_group="teacher", herkunft="eigen"))

        def assistent(name, **felder):
            vorgabe = dict(system_prompt="P", status="active", audience="student", scope="all_students",
                           created_by=KOLLEGIN, model="chat-standard")
            return Assistant(name=f"{name} {kennung}", **{**vorgabe, **felder})

        a = {
            "gruppe": assistent("Für die Gruppe", scope="teaching_group", scope_group_id=g.id),
            "versteckt": assistent("Versteckt", scope="teaching_group", scope_group_id=g.id,
                                   visibility="hidden"),
            "schulweit": assistent("Schulweit 8-10", min_grade=8, max_grade=10,
                                   suggest="fallback", tags=["chemie", "physik"]),
            "oberstufe": assistent("Oberstufe", min_grade=11),
            "fremde_gruppe": assistent("Fremde Gruppe", scope="teaching_group",
                                       scope_group_id=andere.id),
            "eigen_sichtbar": assistent("Eigen sichtbar", created_by=TEACHER1_PSEUDO,
                                        scope="teaching_group", scope_group_id=g.id),
            "eigen_entwurf": assistent("Eigen Entwurf", created_by=TEACHER1_PSEUDO,
                                       status="draft", scope="private"),
            "eigen_privat": assistent("Eigen privat", created_by=TEACHER1_PSEUDO, scope="private"),
            "eigen_fachschaft": assistent("Eigen Fachschaft", created_by=TEACHER1_PSEUDO,
                                          scope="subject_department", scope_group_id=fachschaft.id),
            "eigen_lehrkraefte": assistent("Eigen Lehrkräfte", created_by=TEACHER1_PSEUDO,
                                           scope="teachers", audience="teacher"),
            "eigen_stufe": assistent("Eigen Stufe", created_by=TEACHER1_PSEUDO, min_grade=11),
            "eigen_modell": assistent("Eigen Modell", created_by=TEACHER1_PSEUDO,
                                      model="chat-komplex"),
        }
        db.add_all(a.values())
        await db.commit()
        ids = {k: v.id for k, v in a.items()}
        gruppen = {"g": g.id, "andere": andere.id, "ohne": ohne.id, "abgeleitet": abgeleitet.id,
                   "fachschaft": fachschaft.id}
    yield {"a": ids, **gruppen}
    async with fabrik() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.id.in_(list(ids.values()))))
        await db.execute(sa.delete(Group).where(Group.id.in_(list(gruppen.values()))))
        await db.execute(sa.delete(Subject).where(Subject.id == fach.id))
        await db.commit()


@pytest.fixture(autouse=True)
def modelle():
    """Freigabe der Stufe ohne Proxy: nur `chat-standard`."""
    with patch("app.groups.schuelersicht.erlaubte_modelle_fuer",
               AsyncMock(return_value={"chat-standard"})) as attrappe:
        yield attrappe


async def _sicht(client, headers, gruppe, **param):
    antwort = await client.get(f"/groups/{gruppe}/student-assistants", headers=headers,
                               params=param)
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


def _ids(liste):
    return {e["id"] for e in liste}


async def test_was_die_gruppe_sieht(test_client, auth_headers, welt):
    a = welt["a"]
    sicht = await _sicht(test_client, auth_headers, welt["g"])
    assert (sicht["jahrgang"], sicht["jahrgang_quelle"], sicht["modelle_bekannt"]) == (9, "festgelegt", True)
    assert {a["gruppe"], a["versteckt"], a["eigen_sichtbar"]} <= _ids(sicht["fuer_die_gruppe"])
    assert a["schulweit"] in _ids(sicht["schulweit"])
    unsichtbar_fuer_die_gruppe = {a["oberstufe"], a["fremde_gruppe"], a["eigen_entwurf"],
                                  a["eigen_privat"], a["eigen_fachschaft"], a["eigen_lehrkraefte"],
                                  a["eigen_stufe"], a["eigen_modell"]}
    sichtbar = _ids(sicht["fuer_die_gruppe"]) | _ids(sicht["schulweit"])
    assert not unsichtbar_fuer_die_gruppe & sichtbar


async def test_ausgeblendet_und_eigen_sind_markiert(test_client, auth_headers, welt):
    a = welt["a"]
    gruppe = {e["id"]: e for e in (await _sicht(test_client, auth_headers, welt["g"]))["fuer_die_gruppe"]}
    assert gruppe[a["versteckt"]]["ausgeblendet"] is True
    assert gruppe[a["gruppe"]]["ausgeblendet"] is False
    assert gruppe[a["eigen_sichtbar"]]["eigen"] is True
    assert gruppe[a["gruppe"]]["eigen"] is False


async def test_eigene_unsichtbare_mit_grund(test_client, auth_headers, welt):
    a = welt["a"]
    sicht = await _sicht(test_client, auth_headers, welt["g"])
    # Nur die dieses Tests — die Testdatenbank bringt einen eigenen Assistenten von TEACHER1 mit.
    gruende = {e["id"]: e["grund"] for e in sicht["eigene_unsichtbar"] if e["id"] in a.values()}
    assert gruende == {
        a["eigen_entwurf"]: "entwurf",
        a["eigen_privat"]: "privat",
        a["eigen_fachschaft"]: "fachschaft",
        a["eigen_lehrkraefte"]: "nur_lehrkraefte",
        a["eigen_stufe"]: "stufe",
        a["eigen_modell"]: "modell",
    }, "nur eigene, und keine, die die Gruppe sieht"


async def test_jahrgang_unbekannt_ohne_stufenfilter(test_client, auth_headers, welt, modelle):
    a = welt["a"]
    sicht = await _sicht(test_client, auth_headers, welt["ohne"])
    assert (sicht["jahrgang"], sicht["jahrgang_quelle"], sicht["modelle_bekannt"]) == (None, None, False)
    modelle.assert_not_awaited()
    schulweit = _ids(sicht["schulweit"])
    assert {a["schulweit"], a["oberstufe"]} <= schulweit, "ohne Stufe kein Stufenfilter"


async def test_jahrgang_gewaehlt(test_client, auth_headers, welt):
    a = welt["a"]
    sicht = await _sicht(test_client, auth_headers, welt["ohne"], jahrgang=12)
    assert (sicht["jahrgang"], sicht["jahrgang_quelle"]) == (12, "gewaehlt")
    schulweit = _ids(sicht["schulweit"])
    assert a["oberstufe"] in schulweit and a["schulweit"] not in schulweit


async def test_jahrgang_aus_dem_namen(test_client, auth_headers, welt):
    sicht = await _sicht(test_client, auth_headers, welt["abgeleitet"])
    assert (sicht["jahrgang"], sicht["jahrgang_quelle"]) == (8, "abgeleitet")


async def test_nur_lehrkraefte_der_gruppe(test_client, auth_headers_teacher2, auth_headers_student,
                                          auth_headers, welt):
    pfad = f"/groups/{welt['g']}/student-assistants"
    assert (await test_client.get(pfad, headers=auth_headers_teacher2)).status_code == 403
    assert (await test_client.get(pfad, headers=auth_headers_student)).status_code == 403
    assert (await test_client.get(f"/groups/{welt['fachschaft']}/student-assistants",
                                  headers=auth_headers)).status_code == 404


async def test_liefert_vorschlag_und_schlagwoerter(test_client, auth_headers, welt):
    """Für die Ordnung nach Fach im Reiter (0.33.1)."""
    sicht = await _sicht(test_client, auth_headers, welt["g"])
    eintrag = next(e for e in sicht["schulweit"] if e["id"] == welt["a"]["schulweit"])
    assert (eintrag["suggest"], eintrag["tags"]) == ("fallback", ["chemie", "physik"])

