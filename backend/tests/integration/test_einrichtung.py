"""Einrichtung beim ersten Login (0.43, Plan Schritt 1): wann sie fällig ist, was sie speichert.

Fällig heißt: Rolle `teacher`, keine Vorschau, kein gespeicherter Stand, Konto seit dem Stichtag
(F2 a). Der Stand liegt in `user_preferences` — der Test liest ihn über `/preferences` zurück.
"""
import time
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.auth.jwt import Vorschau
from app.crons import cleanup_service
from app.einrichtung.router import EINRICHTUNG_AB

pytestmark = pytest.mark.asyncio

NEU = "einrichtung-neu-pseudo"
ALT = "einrichtung-alt-pseudo"
ADMIN = "einrichtung-admin-pseudo"
SCHUELER = "einrichtung-schueler-pseudo"
PERSONEN = [NEU, ALT, ADMIN, SCHUELER]


@pytest_asyncio.fixture
async def konten(async_engine):
    neu = datetime.now(timezone.utc)
    alt = datetime.combine(EINRICHTUNG_AB - timedelta(days=30), datetime.min.time(), timezone.utc)

    async def aufraeumen():
        async with async_engine.begin() as conn:
            await conn.execute(text("DELETE FROM user_preferences WHERE pseudonym = ANY(:p)"), {"p": PERSONEN})
            await conn.execute(text("DELETE FROM pseudonym_audit WHERE pseudonym = ANY(:p)"), {"p": PERSONEN})
            await conn.execute(text("UPDATE site_config SET value = NULL WHERE key = 'einrichtung_hinweis'"))

    await aufraeumen()
    async with async_engine.begin() as conn:
        for p, rolle, seit in ((NEU, "teacher", neu), (ALT, "teacher", alt),
                               (ADMIN, "teacher", neu), (SCHUELER, "student", neu)):
            await conn.execute(
                text("INSERT INTO pseudonym_audit (pseudonym, role, created_at) VALUES (:p, :r, :t)"),
                {"p": p, "r": rolle, "t": seit})
        await conn.execute(text(
            "INSERT INTO site_config (key, value) VALUES ('einrichtung_hinweis', NULL) "
            "ON CONFLICT (key) DO NOTHING"))
    yield
    await aufraeumen()


def _kopf(jwt_service, pseudonym, rollen, grade=None, **extra):
    token, _ = jwt_service.issue(pseudonym=pseudonym, roles=rollen, grade=grade, **extra)
    return {"Cookie": f"session={token}"}


async def _lesen(client, kopf):
    resp = await client.get("/einrichtung", headers=kopf)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_neue_lehrkraft_faellig(test_client, konten, jwt_service):
    d = await _lesen(test_client, _kopf(jwt_service, NEU, ["teacher"]))
    assert d["faellig"] is True
    assert d["stand"] is None and d["seite"] is None
    assert d["hinweis"] is None
    assert set(d["stundenplan"]) == {"configured", "kuerzel_gesetzt"}
    assert d["stundenplan"]["kuerzel_gesetzt"] is False


async def test_fristen_aus_den_loeschlaeufen(test_client, konten, jwt_service):
    """Die Zahlen auf „Gut zu wissen“ sind die der Löschläufe, keine eigene Angabe."""
    d = await _lesen(test_client, _kopf(jwt_service, NEU, ["teacher"]))
    assert d["fristen"] == {"chat_tage": cleanup_service._CONVERSATION_RETENTION_DAYS,
                            "konto_tage": cleanup_service._ACCOUNT_RETENTION_DAYS}


async def test_bestand_nicht_faellig(test_client, konten, jwt_service):
    assert (await _lesen(test_client, _kopf(jwt_service, ALT, ["teacher"])))["faellig"] is False


async def test_admin_mit_lehrkraft_ja_reiner_admin_nein(test_client, konten, jwt_service):
    """F10: Rollen sind additiv — Admin mit `teacher` bekommt die Einrichtung, ein reiner Admin nicht."""
    assert (await _lesen(test_client, _kopf(jwt_service, ADMIN, ["teacher", "admin"])))["faellig"] is True
    kopf = _kopf(jwt_service, ADMIN, ["admin"])
    assert (await _lesen(test_client, kopf))["faellig"] is False
    resp = await test_client.put("/einrichtung", headers=kopf, json={"stand": "erledigt", "seite": 6})
    assert resp.status_code == 403


async def test_schueler_nicht_faellig(test_client, konten, jwt_service):
    kopf = _kopf(jwt_service, SCHUELER, ["student"], "8")
    assert (await _lesen(test_client, kopf))["faellig"] is False
    resp = await test_client.put("/einrichtung", headers=kopf, json={"stand": "erledigt", "seite": 6})
    assert resp.status_code == 403


async def test_vorschau_nicht_faellig_und_gesperrt(test_client, konten, jwt_service):
    jetzt = int(time.time())
    kopf = _kopf(jwt_service, NEU, ["student"], "9",
                 preview=Vorschau(echte_rollen=["teacher"], beginn=jetzt, sitzung_ablauf=jetzt + 3600),
                 exp=jetzt + 3600)
    assert (await _lesen(test_client, kopf))["faellig"] is False
    resp = await test_client.put("/einrichtung", headers=kopf, json={"stand": "spaeter", "seite": 2})
    assert resp.status_code == 403


@pytest.mark.parametrize("stand", ["spaeter", "erledigt", "abgewaehlt"])
async def test_stand_speichern(test_client, konten, jwt_service, stand):
    kopf = _kopf(jwt_service, NEU, ["teacher"])
    resp = await test_client.put("/einrichtung", headers=kopf, json={"stand": stand, "seite": 3})
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert (d["faellig"], d["stand"], d["seite"]) == (False, stand, 3)
    gespeichert = (await test_client.get("/preferences", headers=kopf)).json()["einrichtung"]
    assert gespeichert["version"] == 1 and gespeichert["stand"] == stand and gespeichert["seite"] == 3
    assert gespeichert["am"]


async def test_bestand_kann_die_einrichtung_trotzdem_durchgehen(test_client, konten, jwt_service):
    """Wiederaufruf unter „Unterricht“: auch ohne Fälligkeit speicherbar."""
    kopf = _kopf(jwt_service, ALT, ["teacher"])
    resp = await test_client.put("/einrichtung", headers=kopf, json={"stand": "erledigt", "seite": 6})
    assert resp.status_code == 200
    assert resp.json()["stand"] == "erledigt"


@pytest.mark.parametrize("body", [
    {"stand": "fertig", "seite": 1},
    {"stand": "erledigt", "seite": 0},
    {"stand": "erledigt", "seite": 7},
    {"stand": "erledigt"},
    {"seite": 2},
])
async def test_ungueltige_werte(test_client, konten, jwt_service, body):
    resp = await test_client.put("/einrichtung", headers=_kopf(jwt_service, NEU, ["teacher"]), json=body)
    assert resp.status_code == 422


async def test_kuerzel_gesetzt(test_client, konten, async_engine, jwt_service):
    async with async_engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO user_preferences (pseudonym, preferences) "
            "VALUES (:p, '{\"webuntis_kuerzel\": \"KOE\"}'::jsonb)"), {"p": NEU})
    d = await _lesen(test_client, _kopf(jwt_service, NEU, ["teacher"]))
    assert d["stundenplan"]["kuerzel_gesetzt"] is True
    assert "KOE" not in str(d), "nur ob, nicht welches"


async def test_hinweis_der_schule(test_client, konten, jwt_service, auth_headers):
    resp = await test_client.put("/admin/site-texts/einrichtung_hinweis", headers=auth_headers,
                                 json={"content": "Bei Fragen: Raum 112."})
    assert resp.status_code == 200, resp.text
    kopf = _kopf(jwt_service, NEU, ["teacher"])
    assert (await _lesen(test_client, kopf))["hinweis"] == "Bei Fragen: Raum 112."
    await test_client.put("/admin/site-texts/einrichtung_hinweis", headers=auth_headers,
                          json={"content": "   "})
    assert (await _lesen(test_client, kopf))["hinweis"] is None
