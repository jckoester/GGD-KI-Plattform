"""Darstellungsstufe speichern und lesen (Schritt 2).

Die Stufe liegt in `user_preferences.preferences` — einem JSONB-Feld, kein Schemawechsel.
Geprüft wird hier vor allem, was **daneben** passieren darf und was nicht: Die übrigen
Einstellungen einer Nutzer:in dürfen beim Setzen der Stufe nicht verloren gehen.

Die Richtung der Prüfung ist bewusst ungleich: Beim **Schreiben** wird ein ungültiger Wert
abgewiesen (er kommt nicht aus der Oberfläche, sondern aus einem Fehler — ihn still zu
korrigieren verbärge beides). Beim **Lesen** wird geklemmt (ein Altwert darf nie zu einer
leeren Navigation führen).
"""
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def aufraeumen(async_engine):
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    yield
    async with factory() as s:
        await s.execute(text("DELETE FROM user_preferences WHERE pseudonym = :p"),
                        {"p": TEACHER1_PSEUDO})
        await s.commit()


async def test_stufe_setzen_und_wiederlesen(test_client, auth_headers):
    resp = await test_client.patch("/preferences", json={"ui_level": 3}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["ui_level"] == 3

    gelesen = await test_client.get("/preferences", headers=auth_headers)
    assert gelesen.json()["ui_level"] == 3


async def test_zurueckschalten_geht_genauso(test_client, auth_headers):
    """Leitprinzip 3: rückschaltbar, ohne dass etwas verloren geht."""
    await test_client.patch("/preferences", json={"ui_level": 4}, headers=auth_headers)
    resp = await test_client.patch("/preferences", json={"ui_level": 1}, headers=auth_headers)
    assert resp.json()["ui_level"] == 1


async def test_andere_einstellungen_ueberleben(test_client, auth_headers):
    """Der teuerste Fehler wäre, beim Setzen der Stufe den Rest zu überschreiben."""
    await test_client.patch("/preferences", json={"theme": "dark", "show_cost": True},
                            headers=auth_headers)
    await test_client.patch("/preferences", json={"ui_level": 2}, headers=auth_headers)

    prefs = (await test_client.get("/preferences", headers=auth_headers)).json()
    assert prefs == {"theme": "dark", "show_cost": True, "ui_level": 2}


@pytest.mark.parametrize("wert", [0, -1, 5, 99])
async def test_stufe_ausserhalb_des_bereichs_wird_abgewiesen(test_client, auth_headers, wert):
    """Eine Lehrkraft hat vier Stufen; 0 hätte die Navigation geleert."""
    resp = await test_client.patch("/preferences", json={"ui_level": wert},
                                   headers=auth_headers)
    assert resp.status_code == 422
    assert "zwischen 1 und 4" in resp.json()["detail"]


async def test_unsinniger_wert_wird_abgewiesen(test_client, auth_headers):
    resp = await test_client.patch("/preferences", json={"ui_level": "hoch"},
                                   headers=auth_headers)
    assert resp.status_code == 422


async def test_abgewiesener_wert_hinterlaesst_nichts(test_client, auth_headers):
    """Geprüft wird vor dem Speichern — sonst stünde die halbe Änderung schon da."""
    await test_client.patch("/preferences", json={"theme": "light"}, headers=auth_headers)
    await test_client.patch("/preferences", json={"theme": "dark", "ui_level": 9},
                            headers=auth_headers)

    prefs = (await test_client.get("/preferences", headers=auth_headers)).json()
    assert prefs == {"theme": "light"}, "weder die Stufe noch das Thema dürfen ankommen"


async def test_schuelerin_hat_nur_zwei_stufen(test_client, auth_headers_student):
    resp = await test_client.patch("/preferences", json={"ui_level": 3},
                                   headers=auth_headers_student)
    assert resp.status_code == 422
    assert "zwischen 1 und 2" in resp.json()["detail"]
