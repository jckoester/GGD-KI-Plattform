"""Bewertungen eigener Assistenten (0.33, Päckchen AK, Plan Schritt 1). Erfordert TEST_DATABASE_URL.

Die Erstellerin ist eine Lehrkraft **ohne** Admin-Rolle — sonst liefe der Zugriff über das
Admin-Recht an der eigentlichen Regel vorbei.
"""
import time
from datetime import date

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.vorschau import Vorschau
from app.db.models import Assistant, RatingCount
from tests.integration.conftest import TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio

W1, W2 = date(2021, 3, 1), date(2021, 3, 8)


@pytest_asyncio.fixture
async def fabrik(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def assistent(fabrik):
    """Ein Assistent von TEACHER2 mit Zählern über zwei Wochen und zwei Modelle."""
    erzeugt = []

    async def anlegen(zaehler=()):
        async with fabrik() as db:
            a = Assistant(name=f"AK-Test {len(erzeugt)}", system_prompt="P", model="chat-standard",
                          status="active", audience="student", scope="private",
                          created_by=TEACHER2_PSEUDO)
            db.add(a)
            await db.flush()
            for woche, modell, rolle, plus, minus in zaehler:
                db.add(RatingCount(woche=woche, assistant_id=a.id, modell=modell, rolle=rolle,
                                   plus=plus, minus=minus))
            await db.commit()
            erzeugt.append(a.id)
            return a.id

    yield anlegen
    async with fabrik() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.id.in_(erzeugt)))
        await db.commit()


GENUG = [
    (W1, "chat-standard", "student", 5, 2),
    (W2, "chat-komplex", "student", 3, 1),   # zusammen 8 : 3 — über der Schwelle
    (W1, "chat-standard", "teacher", 2, 0),  # Lehrkräfte: 2 — darunter
]


def _kopf(jwt_service, pseudonym, *rollen, **mehr):
    token, _ = jwt_service.issue(pseudonym=pseudonym, roles=list(rollen), grade=None, **mehr)
    return {"Cookie": f"session={token}"}


async def test_erstellerin_sieht_gesamtstand(test_client, auth_headers_teacher2, assistent):
    aid = await assistent(GENUG)
    antwort = await test_client.get(f"/assistants/{aid}/ratings", headers=auth_headers_teacher2)
    assert antwort.status_code == 200, antwort.text
    assert antwort.json() == {
        "schueler": {"zu_wenige": False, "plus": 8, "minus": 3, "anteil": 73},
        "lehrkraefte": {"zu_wenige": True, "plus": None, "minus": None, "anteil": None},
        "mindestzahl": 10,
    }


async def test_unter_der_schwelle_keine_zahlen(test_client, auth_headers_teacher2, assistent):
    """9 Bewertungen: nicht einmal die Zahl steht in der Antwort."""
    aid = await assistent([(W1, "chat-standard", "student", 1, 8)])
    daten = (await test_client.get(f"/assistants/{aid}/ratings", headers=auth_headers_teacher2)).json()
    assert daten["schueler"] == {"zu_wenige": True, "plus": None, "minus": None, "anteil": None}
    assert "8" not in str(daten["schueler"])


async def test_ohne_bewertungen_zu_wenige(test_client, auth_headers_teacher2, assistent):
    """Etwa eine Kopie: Sie beginnt bei null (F6)."""
    aid = await assistent()
    daten = (await test_client.get(f"/assistants/{aid}/ratings", headers=auth_headers_teacher2)).json()
    assert daten["schueler"]["zu_wenige"] and daten["lehrkraefte"]["zu_wenige"]


async def test_wer_es_sieht(test_client, jwt_service, auth_headers, auth_headers_student, assistent):
    aid = await assistent(GENUG)
    pfad = f"/assistants/{aid}/ratings"
    fremd = _kopf(jwt_service, "ak-fremde-lehrkraft", "teacher")
    assert (await test_client.get(pfad, headers=fremd)).status_code == 403
    assert (await test_client.get(pfad, headers=auth_headers_student)).status_code == 403
    assert (await test_client.get(pfad, headers=auth_headers)).status_code == 200, "Admin"
    assert (await test_client.get("/assistants/999999/ratings", headers=auth_headers)).status_code == 404


async def test_in_der_vorschau_nicht(test_client, jwt_service, assistent):
    """In der Vorschau zählt Eigentum nicht — wie beim Editor."""
    aid = await assistent(GENUG)
    jetzt = int(time.time())
    kopf = _kopf(jwt_service, TEACHER2_PSEUDO, "student",
                 preview=Vorschau(echte_rollen=["teacher"], beginn=jetzt, sitzung_ablauf=jetzt + 3600),
                 exp=jetzt + 3600)
    assert (await test_client.get(f"/assistants/{aid}/ratings", headers=kopf)).status_code == 403


async def test_eigene_liste_traegt_den_stand(test_client, auth_headers_teacher2, assistent):
    viel = await assistent(GENUG)
    wenig = await assistent()
    antwort = await test_client.get("/assistants/mine?limit=200", headers=auth_headers_teacher2)
    assert antwort.status_code == 200, antwort.text
    je_id = {a["id"]: a["bewertung"] for a in antwort.json()["items"]}
    assert je_id[viel]["schueler"]["anteil"] == 73
    assert je_id[wenig]["schueler"] == {"zu_wenige": True, "plus": None, "minus": None, "anteil": None}
