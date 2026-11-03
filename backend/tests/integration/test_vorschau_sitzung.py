"""Eine ganze Vorschau-Sitzung über die Schnittstelle (0.29, Schritt 6).

Der Weg aus dem Editor: eigener Entwurf, eigene Gruppe → Assistentenliste → Chat mit dem
Entwurf → Rückmeldung → zurück. Hält zusammen, was die Einzeltests der Schritte 1–5 je für
sich prüfen. Erfordert TEST_DATABASE_URL.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Assistant, Conversation, Group, GroupMembership, Subject
from tests.integration.conftest import TEACHER1_PSEUDO, TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio


class _BisHierher(Exception):
    pass


@pytest_asyncio.fixture
async def welt(async_engine):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    k = uuid.uuid4().hex[:8]
    async with fabrik() as db:
        fach = Subject(slug=f"vs-{k}", name="Sitzungsfach")
        db.add(fach)
        await db.flush()
        g = Group(name="VS 8b", slug=f"vs-{k}", type="teaching_group", subject_id=fach.id)
        db.add(g)
        await db.flush()
        db.add(GroupMembership(group_id=g.id, pseudonym=TEACHER1_PSEUDO,
                               role_in_group="teacher", herkunft="eigen"))

        def a(**kw):
            basis = dict(system_prompt="Du hilfst.", audience="student", creator_role="teacher",
                         model="", scope="all_students", status="active")
            return Assistant(**{**basis, **kw})

        entwurf = a(name=f"Entwurf {k}", status="draft", created_by=TEACHER1_PSEUDO,
                    min_grade=7, max_grade=9)
        anderer_entwurf = a(name=f"Anderer Entwurf {k}", status="draft", created_by=TEACHER1_PSEUDO)
        privat = a(name=f"Privat {k}", scope="private", audience="all", created_by=TEACHER1_PSEUDO)
        gruppe = a(name=f"Für 8b {k}", scope="teaching_group", scope_group_id=g.id,
                   created_by=TEACHER2_PSEUDO)
        fuer_lehrkraefte = a(name=f"Nur Lehrkräfte {k}", audience="teacher", scope="teachers",
                             created_by=TEACHER2_PSEUDO)
        db.add_all([entwurf, anderer_entwurf, privat, gruppe, fuer_lehrkraefte])
        await db.commit()
        return {"g": g.id, "fabrik": fabrik, **{n: x.id for n, x in [
            ("entwurf", entwurf), ("anderer_entwurf", anderer_entwurf), ("privat", privat),
            ("gruppe", gruppe), ("fuer_lehrkraefte", fuer_lehrkraefte)]}}


async def test_eine_sitzung_aus_dem_editor(test_client, jwt_service, welt):
    sitzung, _ = jwt_service.issue(pseudonym=TEACHER1_PSEUDO, roles=["teacher"], grade=None)

    # 1. Eintritt aus dem Editor: Entwurf, Klasse 8, Gruppe 8b.
    rein = await test_client.post("/auth/vorschau", headers={"Cookie": f"session={sitzung}"},
                                  json={"jahrgang": 8, "gruppe_id": welt["g"],
                                        "assistent_id": welt["entwurf"]})
    assert rein.status_code == 200, rein.text
    kopf = {"Cookie": f"session={rein.cookies.get('session')}"}

    # 2. Die Assistentenliste ist die einer Schüler:in der 8b.
    liste = {x["id"] for x in (await test_client.get("/assistants", headers=kopf)).json()["items"]}
    assert welt["entwurf"] in liste, "Der Eintrittsassistent ist sichtbar, auch als Entwurf"
    assert welt["gruppe"] in liste, "Was für die Gruppe freigegeben ist, sieht sie"
    for unsichtbar in ("anderer_entwurf", "privat", "fuer_lehrkraefte"):
        assert welt[unsichtbar] not in liste, unsichtbar

    # 3. Chat mit dem Entwurf — bis zum Kontext; die Konversation trägt die Vorschau.
    gesehen = {}

    async def anhalten(*, chat_id, db, **_):
        gesehen["k"] = await db.get(Conversation, chat_id)
        raise _BisHierher

    with patch("app.chat.router.kontext_fuer_frage", AsyncMock(side_effect=anhalten)):
        with pytest.raises(_BisHierher):
            await test_client.post("/chat", headers=kopf, json={
                "messages": [{"role": "user", "content": "Hallo, wie fange ich an?"}],
                "assistant_id": welt["entwurf"]})
    k = gesehen["k"]
    assert k.preview_context == {"jahrgang": "8", "gruppe_id": welt["g"],
                                 "assistent_id": welt["entwurf"],
                                 "beginn": k.preview_context["beginn"]}

    # Der Chat-Lauf oben bricht ab und rollt zurück; für die Listen ein gespeicherter.
    async with welt["fabrik"]() as db:
        probe = Conversation(pseudonym=TEACHER1_PSEUDO, model_used="m", title="Probe",
                             preview_context={"jahrgang": "8"})
        db.add(probe)
        await db.commit()
        probe_id = str(probe.id)

    # 4. Rückmeldung aus der Vorschau.
    meldung = await test_client.post("/feedback", headers=kopf, json={
        "category": "suggestion", "content": "Der Entwurf erklärt den Einstieg gut.",
        "app_version": "0.29.0"})
    assert meldung.status_code == 201

    # 5. Ändern geht nicht — etwa die Einstellungen.
    assert (await test_client.patch("/preferences", headers=kopf,
                                    json={"ui_level": 1})).status_code == 403

    # 6. Zurück: wieder Lehrkraft, der Vorschau-Chat steht in der eigenen Liste.
    raus = await test_client.delete("/auth/vorschau", headers=kopf)
    assert raus.status_code == 200
    normal = {"Cookie": f"session={raus.cookies.get('session')}"}
    assert (await test_client.get("/auth/me", headers=normal)).json()["roles"] == ["teacher"]
    eigene = {x["id"] for x in (await test_client.get(
        "/conversations", headers=normal, params={"limit": 100})).json()["items"]}
    vorschau = {x["id"] for x in (await test_client.get(
        "/conversations", headers=normal, params={"limit": 100, "vorschau": "true"})).json()["items"]}
    assert probe_id in vorschau and probe_id not in eigene
    liste = {x["id"] for x in (await test_client.get("/assistants", headers=normal)).json()["items"]}
    assert welt["privat"] in liste, "Außerhalb der Vorschau sieht sie ihre eigenen wieder"
