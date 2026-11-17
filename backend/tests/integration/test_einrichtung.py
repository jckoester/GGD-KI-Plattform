"""Einrichtung beim ersten Login (0.43, Plan Schritt 1; Schüler:innen 0.47, Schritt 3): wann sie
fällig ist, was sie speichert.

Fällig heißt: Rolle `teacher` oder `student`, keine Vorschau, kein gespeicherter Stand, Konto seit
dem Stichtag **der Rolle** (F2 a bzw. F1 a). Der Stand liegt in `user_preferences` — der Test liest
ihn über `/preferences` zurück.
"""
import time
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.auth.jwt import Vorschau
from app.crons import cleanup_service
from app.einrichtung.router import EINRICHTUNG_AB, HINWEIS_SCHLUESSEL

pytestmark = pytest.mark.asyncio

NEU = "einrichtung-neu-pseudo"
ALT = "einrichtung-alt-pseudo"
ADMIN = "einrichtung-admin-pseudo"
SCHUELER = "einrichtung-schueler-pseudo"
SCHUELER_ALT = "einrichtung-schueler-alt-pseudo"
#: Zwischen den Stichtagen entstanden: für Lehrkräfte neu, für Schüler:innen Bestand.
DAZWISCHEN = "einrichtung-dazwischen-pseudo"
PERSONEN = [NEU, ALT, ADMIN, SCHUELER, SCHUELER_ALT, DAZWISCHEN]

HINWEISE = tuple(HINWEIS_SCHLUESSEL.values())


def _seit(tag):
    """Mittag des Tages — ein Konto „am Stichtag“, unabhängig von der Zeitzone."""
    return datetime.combine(tag, datetime.min.time(), timezone.utc) + timedelta(hours=12)


@pytest_asyncio.fixture
async def konten(async_engine):
    jetzt = datetime.now(timezone.utc)
    # „Neu“ je Rolle: heute, frühestens aber der Stichtag der Rolle (er darf in der Zukunft liegen,
    # solange 0.47 nicht ausgerollt ist).
    neu = max(jetzt, _seit(EINRICHTUNG_AB["teacher"]))
    neu_schueler = max(jetzt, _seit(EINRICHTUNG_AB["student"]))
    alt = _seit(EINRICHTUNG_AB["teacher"] - timedelta(days=30))
    dazwischen = _seit(EINRICHTUNG_AB["student"] - timedelta(days=1))
    assert EINRICHTUNG_AB["teacher"] < EINRICHTUNG_AB["student"]

    async def aufraeumen():
        async with async_engine.begin() as conn:
            await conn.execute(text("DELETE FROM user_preferences WHERE pseudonym = ANY(:p)"), {"p": PERSONEN})
            await conn.execute(text("DELETE FROM pseudonym_audit WHERE pseudonym = ANY(:p)"), {"p": PERSONEN})
            await conn.execute(text("UPDATE site_config SET value = NULL WHERE key = ANY(:k)"),
                               {"k": list(HINWEISE)})

    await aufraeumen()
    async with async_engine.begin() as conn:
        for p, rolle, seit in ((NEU, "teacher", neu), (ALT, "teacher", alt),
                               (ADMIN, "teacher", neu), (SCHUELER, "student", neu_schueler),
                               (SCHUELER_ALT, "student", alt), (DAZWISCHEN, "student", dazwischen)):
            await conn.execute(
                text("INSERT INTO pseudonym_audit (pseudonym, role, created_at) VALUES (:p, :r, :t)"),
                {"p": p, "r": rolle, "t": seit})
        for k in HINWEISE:
            await conn.execute(text(
                "INSERT INTO site_config (key, value) VALUES (:k, NULL) ON CONFLICT (key) DO NOTHING"),
                {"k": k})
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


async def test_neue_schuelerin_faellig_und_speichert(test_client, konten, jwt_service):
    """0.47: Schüler:innen haben eine Einrichtung — fällig und speicherbar wie bei Lehrkräften."""
    kopf = _kopf(jwt_service, SCHUELER, ["student"], "8")
    assert (await _lesen(test_client, kopf))["faellig"] is True
    resp = await test_client.put("/einrichtung", headers=kopf, json={"stand": "spaeter", "seite": 2})
    assert resp.status_code == 200, resp.text
    assert (resp.json()["faellig"], resp.json()["stand"], resp.json()["seite"]) == (False, "spaeter", 2)


async def test_schueler_bestand_nicht_faellig_aber_speicherbar(test_client, konten, jwt_service):
    """F1 a: Wer vor dem Stichtag kam, bekommt den Dialog nicht von selbst — aber über das Profil."""
    kopf = _kopf(jwt_service, SCHUELER_ALT, ["student"], "8")
    assert (await _lesen(test_client, kopf))["faellig"] is False
    resp = await test_client.put("/einrichtung", headers=kopf, json={"stand": "erledigt", "seite": 5})
    assert resp.status_code == 200


async def test_stichtag_je_rolle(test_client, konten, jwt_service):
    """Zwischen beiden Stichtagen entstanden: als Lehrkraft neu, als Schüler:in Bestand.

    Mit einem Stichtag für alle bekäme jedes Schüler-Konto seit dem 14.11. den Dialog.
    """
    assert (await _lesen(test_client, _kopf(jwt_service, DAZWISCHEN, ["teacher"])))["faellig"] is True
    assert (await _lesen(test_client, _kopf(jwt_service, DAZWISCHEN, ["student"], "8")))["faellig"] is False


async def test_doppelrolle_folgt_der_lehrkraft(test_client, konten, jwt_service, auth_headers):
    """F9: Wer `teacher` und `student` ist, bekommt die Einrichtung der Lehrkraft — samt ihrem Hinweis."""
    await test_client.put("/admin/site-texts/einrichtung_hinweis", headers=auth_headers,
                          json={"content": "An Lehrkräfte."})
    await test_client.put("/admin/site-texts/einrichtung_hinweis_schueler", headers=auth_headers,
                          json={"content": "An Schüler:innen."})
    d = await _lesen(test_client, _kopf(jwt_service, DAZWISCHEN, ["student", "teacher"], "8"))
    assert d["faellig"] is True  # Stichtag der Lehrkraft
    assert d["hinweis"] == "An Lehrkräfte."


async def test_vorschau_nicht_faellig_und_gesperrt(test_client, konten, jwt_service):
    jetzt = int(time.time())
    kopf = _kopf(jwt_service, NEU, ["student"], "9",
                 preview=Vorschau(echte_rollen=["teacher"], beginn=jetzt, sitzung_ablauf=jetzt + 3600),
                 exp=jetzt + 3600)
    assert (await _lesen(test_client, kopf))["faellig"] is False
    resp = await test_client.put("/einrichtung", headers=kopf, json={"stand": "spaeter", "seite": 2})
    assert resp.status_code == 403


async def test_vorschau_zeigt_den_hinweis_an_schuelerinnen(test_client, konten, jwt_service, auth_headers):
    """F6 a: In der Vorschau sieht die Lehrkraft, was ihre Klasse sieht — auch den Hinweis der Schule."""
    await test_client.put("/admin/site-texts/einrichtung_hinweis_schueler", headers=auth_headers,
                          json={"content": "Fragen? Sprich deine Klassenlehrkraft an."})
    jetzt = int(time.time())
    kopf = _kopf(jwt_service, NEU, ["student"], "9",
                 preview=Vorschau(echte_rollen=["teacher"], beginn=jetzt, sitzung_ablauf=jetzt + 3600),
                 exp=jetzt + 3600)
    d = await _lesen(test_client, kopf)
    assert d["faellig"] is False
    assert d["hinweis"] == "Fragen? Sprich deine Klassenlehrkraft an."


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


async def test_hinweis_je_rolle(test_client, konten, jwt_service, auth_headers):
    """F7 a: Schüler:innen lesen ihren eigenen Hinweis, nicht den an Lehrkräfte."""
    await test_client.put("/admin/site-texts/einrichtung_hinweis", headers=auth_headers,
                          json={"content": "An Lehrkräfte."})
    schueler = _kopf(jwt_service, SCHUELER, ["student"], "8")
    assert (await _lesen(test_client, schueler))["hinweis"] is None
    resp = await test_client.put("/admin/site-texts/einrichtung_hinweis_schueler", headers=auth_headers,
                                 json={"content": "An Schüler:innen."})
    assert resp.status_code == 200, resp.text
    assert (await _lesen(test_client, schueler))["hinweis"] == "An Schüler:innen."
    assert (await _lesen(test_client, _kopf(jwt_service, NEU, ["teacher"])))["hinweis"] == "An Lehrkräfte."
    # Öffentlich lesbar wie `einrichtung_hinweis` — kein Geheimnis.
    assert (await test_client.get("/site-texts/einrichtung_hinweis_schueler")).status_code == 200


async def test_reiner_admin_ohne_hinweis(test_client, konten, jwt_service, auth_headers):
    await test_client.put("/admin/site-texts/einrichtung_hinweis", headers=auth_headers,
                          json={"content": "An Lehrkräfte."})
    assert (await _lesen(test_client, _kopf(jwt_service, ADMIN, ["admin"])))["hinweis"] is None
