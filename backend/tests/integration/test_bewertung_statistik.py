"""Statistik der Antwortbewertung (0.31, Päckchen T, Plan Schritt 6). Erfordert TEST_DATABASE_URL.

Die Zeilen liegen in Wochen des Jahres 2020 — dort zählt sonst niemand.
"""
from datetime import date

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Assistant, RatingCount

pytestmark = pytest.mark.asyncio

W1, W2 = date(2020, 1, 6), date(2020, 1, 13)
ZEITRAUM = {"from_date": "2020-01-01", "to_date": "2020-01-31"}


@pytest_asyncio.fixture
async def zahlen(async_engine):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        await db.execute(sa.delete(RatingCount).where(RatingCount.woche.between(W1, W2)))
        a = Assistant(name="T-Statistik", system_prompt="P", model="chat-standard")
        db.add(a)
        await db.flush()
        db.add_all([
            RatingCount(woche=W1, assistant_id=a.id, modell="m-a", rolle="student", plus=3, minus=1),
            RatingCount(woche=W2, assistant_id=a.id, modell="m-b", rolle="student", plus=1, minus=0),
            RatingCount(woche=W2, assistant_id=a.id, modell="m-a", rolle="teacher", plus=0, minus=2),
            RatingCount(woche=W1, assistant_id=None, modell="m-a", rolle="student", plus=1, minus=1),
            # Alles zurückgenommen — taucht nicht auf.
            RatingCount(woche=W1, assistant_id=None, modell="m-leer", rolle="student"),
        ])
        await db.commit()
    yield a.id
    async with fabrik() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.id == a.id))
        await db.execute(sa.delete(RatingCount).where(RatingCount.woche.between(W1, W2)))
        await db.commit()


async def _hole(client, headers, **param):
    antwort = await client.get("/admin/stats/ratings", headers=headers,
                               params={**ZEITRAUM, **param})
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


async def test_je_assistent_nach_rolle(test_client, auth_headers, zahlen):
    daten = await _hole(test_client, auth_headers)
    zeilen = {z["schluessel"]: z for z in daten["zeilen"]}
    assert zeilen[str(zahlen)] == {
        "schluessel": str(zahlen), "name": "T-Statistik", "plus_schueler": 4,
        "minus_schueler": 1, "plus_lehrkraft": 0, "minus_lehrkraft": 2}
    assert zeilen[None]["name"] is None and zeilen[None]["plus_schueler"] == 1
    assert len(zeilen) == 2, "Die Zeile ohne Daumen fehlt"
    assert daten["zeilen"][0]["schluessel"] == str(zahlen), "die meisten Bewertungen zuerst"


async def test_je_modell(test_client, auth_headers, zahlen):
    daten = await _hole(test_client, auth_headers, gruppierung="modell")
    zeilen = {z["schluessel"]: z for z in daten["zeilen"]}
    assert set(zeilen) == {"m-a", "m-b"}
    assert (zeilen["m-a"]["plus_schueler"], zeilen["m-a"]["minus_lehrkraft"]) == (4, 2)


async def test_je_woche(test_client, auth_headers, zahlen):
    daten = await _hole(test_client, auth_headers)
    assert daten["wochen"] == [
        {"woche": "2020-01-06", "plus": 4, "minus": 2},
        {"woche": "2020-01-13", "plus": 1, "minus": 2},
    ]


async def test_zeitraum_wochenweise(test_client, auth_headers, zahlen):
    """Ein Zeitraum ab Mittwoch der ersten Woche schließt deren Montag noch ein."""
    daten = await _hole(test_client, auth_headers, from_date="2020-01-08", to_date="2020-01-08")
    assert [w["woche"] for w in daten["wochen"]] == ["2020-01-06"]


async def test_nur_statistik_und_admin(test_client, auth_headers_teacher2, auth_headers_student):
    for kopf in (auth_headers_teacher2, auth_headers_student):
        assert (await test_client.get("/admin/stats/ratings", headers=kopf)).status_code == 403


async def test_zeitraum_verkehrt(test_client, auth_headers):
    antwort = await test_client.get("/admin/stats/ratings", headers=auth_headers,
                                    params={"from_date": "2020-02-01", "to_date": "2020-01-01"})
    assert antwort.status_code == 422
