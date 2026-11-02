"""Vorschau betreten und verlassen (0.29, Schritt 2). Erfordert TEST_DATABASE_URL."""
import time
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.vorschau import Vorschau
from app.db.models import Assistant, Group, GroupMembership, Subject
from tests.integration.conftest import STUDENT_PSEUDO, TEACHER1_PSEUDO, TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def fabrik(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def welt(fabrik):
    kennung = uuid.uuid4().hex[:8]
    async with fabrik() as db:
        fach = Subject(slug=f"ein-{kennung}", name="Eintrittsfach")
        db.add(fach)
        await db.flush()
        eigene = Group(name="Eintritt 9a", slug=f"e-{kennung}", type="teaching_group",
                       subject_id=fach.id)
        fremde = Group(name="Eintritt 9b", slug=f"f-{kennung}", type="teaching_group",
                       subject_id=fach.id)
        db.add_all([eigene, fremde])
        await db.flush()
        db.add_all([
            GroupMembership(group_id=eigene.id, pseudonym=TEACHER1_PSEUDO,
                            role_in_group="teacher", herkunft="eigen"),
            GroupMembership(group_id=fremde.id, pseudonym=TEACHER2_PSEUDO,
                            role_in_group="teacher", herkunft="eigen"),
            GroupMembership(group_id=fremde.id, pseudonym=TEACHER1_PSEUDO,
                            role_in_group="student", herkunft="eigen"),
        ])
        eigen = Assistant(name=f"Eigen {kennung}", system_prompt="P", status="draft",
                          audience="student", scope="all_students", created_by=TEACHER1_PSEUDO,
                          creator_role="teacher", model="")
        fremd = Assistant(name=f"Fremd {kennung}", system_prompt="P", status="active",
                          audience="student", scope="all_students", created_by=TEACHER2_PSEUDO,
                          creator_role="teacher", model="")
        db.add_all([eigen, fremd])
        await db.commit()
        return {"eigene": eigene.id, "fremde": fremde.id, "eigen": eigen.id, "fremd": fremd.id}


def _sitzung(jwt_service, pseudonym=TEACHER1_PSEUDO, roles=("teacher",), *, exp=None):
    token, _ = jwt_service.issue(pseudonym=pseudonym, roles=list(roles), grade=None, exp=exp)
    return token


def _cookie(token):
    return {"Cookie": f"session={token}"}


async def _ereignisse(fabrik, ereignis):
    async with fabrik() as db:
        return (await db.execute(sa.text(
            "SELECT actor_pseudonym, actor_role, payload FROM audit_log"
            " WHERE event_type = :e ORDER BY id"), {"e": ereignis})).all()


async def test_eintritt_und_rueckweg(test_client, jwt_service, welt, fabrik):
    ablauf_sitzung = int(time.time()) + 10 * 24 * 3600
    sitzung = _sitzung(jwt_service, exp=ablauf_sitzung)
    antwort = await test_client.post("/auth/vorschau", headers=_cookie(sitzung), json={
        "jahrgang": 9, "gruppe_id": welt["eigene"], "assistent_id": welt["eigen"]})
    assert antwort.status_code == 200, antwort.text
    vorschau_token = antwort.cookies.get("session")
    assert vorschau_token and vorschau_token != sitzung
    assert antwort.json()["ablauf"] <= int(time.time()) + 3600

    ich = (await test_client.get("/auth/me", headers=_cookie(vorschau_token))).json()
    assert (ich["roles"], ich["grade"]) == (["student"], "9")
    eintritt = (await _ereignisse(fabrik, "preview_entered"))[-1]
    assert eintritt[0] == TEACHER1_PSEUDO and eintritt[1] == "teacher"
    assert eintritt[2] == {"jahrgang": 9, "gruppe_id": welt["eigene"],
                           "assistent_id": welt["eigen"]}

    zurueck = await test_client.delete("/auth/vorschau", headers=_cookie(vorschau_token))
    assert zurueck.status_code == 200, zurueck.text
    neu = zurueck.cookies.get("session")
    payload = jwt_service.verify(neu)
    assert payload.roles == ["teacher"] and payload.preview is None
    assert payload.exp == ablauf_sitzung, "Die Vorschau verlängert die Sitzung nicht"
    # Das Vorschau-Token ist danach widerrufen.
    assert (await test_client.get("/auth/me", headers=_cookie(vorschau_token))).status_code == 401
    austritt = (await _ereignisse(fabrik, "preview_exited"))[-1]
    assert austritt[2]["grund"] == "beendet"


async def test_vorschau_endet_spaetestens_mit_der_sitzung(test_client, jwt_service, welt):
    bald = int(time.time()) + 600
    antwort = await test_client.post("/auth/vorschau", headers=_cookie(_sitzung(jwt_service, exp=bald)),
                                     json={"jahrgang": 7})
    assert antwort.json()["ablauf"] == bald


async def test_rueckweg_nach_ablauf_genau_einmal(test_client, jwt_service, fabrik):
    jetzt = int(time.time())
    abgelaufen, _ = jwt_service.issue(
        pseudonym=TEACHER1_PSEUDO, roles=["student"], grade="9",
        preview=Vorschau(echte_rollen=["teacher"], beginn=jetzt - 3700,
                         sitzung_ablauf=jetzt + 86400),
        exp=jetzt - 100,
    )
    assert (await test_client.get("/auth/me", headers=_cookie(abgelaufen))).status_code == 401
    zurueck = await test_client.delete("/auth/vorschau", headers=_cookie(abgelaufen))
    assert zurueck.status_code == 200, zurueck.text
    assert jwt_service.verify(zurueck.cookies.get("session")).roles == ["teacher"]
    assert (await _ereignisse(fabrik, "preview_exited"))[-1][2]["grund"] == "abgelaufen"
    nochmal = await test_client.delete("/auth/vorschau", headers=_cookie(abgelaufen))
    assert nochmal.status_code == 401


async def test_kein_rueckweg_wenn_die_sitzung_vorbei_ist(test_client, jwt_service):
    jetzt = int(time.time())
    token, _ = jwt_service.issue(
        pseudonym=TEACHER1_PSEUDO, roles=["student"], grade="9",
        preview=Vorschau(echte_rollen=["teacher"], beginn=jetzt - 3700,
                         sitzung_ablauf=jetzt - 10),
        exp=jetzt - 100,
    )
    assert (await test_client.delete("/auth/vorschau", headers=_cookie(token))).status_code == 401


async def test_rueckweg_ohne_vorschau(test_client, jwt_service):
    antwort = await test_client.delete("/auth/vorschau", headers=_cookie(_sitzung(jwt_service)))
    assert antwort.status_code == 409


@pytest.mark.parametrize("fall,erwartet", [
    ("schuelerin", 403),
    ("jahrgang", 422),
    ("fremde_gruppe", 404),
    ("fremder_assistent", 404),
    ("verschachtelt", 409),
])
async def test_eintritt_abgewiesen(test_client, jwt_service, welt, fall, erwartet):
    sitzung = _sitzung(jwt_service)
    rumpf = {"jahrgang": 9}
    if fall == "schuelerin":
        sitzung = _sitzung(jwt_service, STUDENT_PSEUDO, ("student",))
    elif fall == "jahrgang":
        rumpf["jahrgang"] = 99
    elif fall == "fremde_gruppe":
        # Mitglied ist sie dort — aber als Schülerin, nicht als Lehrkraft.
        rumpf["gruppe_id"] = welt["fremde"]
    elif fall == "fremder_assistent":
        rumpf["assistent_id"] = welt["fremd"]
    elif fall == "verschachtelt":
        drin = await test_client.post("/auth/vorschau", headers=_cookie(sitzung), json=rumpf)
        sitzung = drin.cookies.get("session")
    antwort = await test_client.post("/auth/vorschau", headers=_cookie(sitzung), json=rumpf)
    assert antwort.status_code == erwartet, antwort.text
