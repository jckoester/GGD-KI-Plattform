"""Die Selbstverwaltung der Zugangstoken im Profil — samt Re-Authentifizierung.

Zwei Zusagen stehen hier im Mittelpunkt:

* **Anlegen verlangt eine frische Sitzung** (höchstens 15 Minuten, seit 0.19; vorher
  Step-up). Ein gestohlenes Sitzungs-Cookie soll sich keinen Dauerzugang ausstellen
  können, der das Ausloggen überlebt.
* **Ein Token kann kein Token anlegen.** `/tokens` steht nicht in der Scope-Tabelle;
  sonst wäre ein Widerruf wirkungslos — man widerruft eines, das nächste steht bereit.
"""

import time
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from app.auth import tokens as token_dienst
from app.auth.dependencies import FRISCHE_SITZUNG_S
from app.db.models import PersonalAccessToken, PseudonymAudit
from tests.integration.test_planning_api import TEACHER1_PSEUDO


@pytest.fixture
async def db(async_engine):
    """Session ohne umschließende Transaktion — der Dienst committet selbst."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sitzung:
        yield sitzung
    async with factory() as aufraeumen:
        await aufraeumen.execute(
            sa.delete(PersonalAccessToken).where(
                PersonalAccessToken.pseudonym == TEACHER1_PSEUDO
            )
        )
        await aufraeumen.commit()


@pytest.fixture
async def audit(db):
    """`pseudonym_audit` ist geteilter Zustand — nach dem Test zurücksetzen."""
    vorher = await db.get(PseudonymAudit, TEACHER1_PSEUDO)
    gab_es = vorher is not None
    alt = (
        {"role": vorher.role, "roles": vorher.roles, "revoked_all_before": vorher.revoked_all_before}
        if gab_es else None
    )
    if not gab_es:
        vorher = PseudonymAudit(pseudonym=TEACHER1_PSEUDO, role="teacher",
                                roles=["teacher", "admin"], grade=None)
        db.add(vorher)
    else:
        vorher.role, vorher.roles, vorher.revoked_all_before = "teacher", ["teacher", "admin"], None
    await db.commit()
    yield vorher
    zeile = await db.get(PseudonymAudit, TEACHER1_PSEUDO)
    if zeile is not None and gab_es:
        for feld, wert in alt.items():
            setattr(zeile, feld, wert)
    elif zeile is not None:
        await db.delete(zeile)
    await db.commit()


def _anlegen(test_client, auth_headers, *, name="MacBook", scopes=None, tage=30):
    return test_client.post(
        "/tokens",
        json={
            "name": name,
            "scopes": scopes if scopes is not None else ["planning:read"],
            "gueltig_bis": (date.today() + timedelta(days=tage)).isoformat(),
        },
        headers=auth_headers,
    )


class TestAnlegen:
    async def test_mit_frischer_sitzung(self, test_client, auth_headers, audit):
        resp = await _anlegen(test_client, auth_headers)
        assert resp.status_code == 201, resp.text
        daten = resp.json()
        assert daten["token"].startswith(token_dienst.PRAEFIX)
        assert daten["eintrag"]["scopes"] == ["planning:read"]
        assert daten["eintrag"]["last_used_at"] is None

    async def test_alte_sitzung_bekommt_die_aufforderung(self, test_client, auth_headers, audit):
        """Die Sitzung ist 15 Minuten und eine Sekunde alt — die Uhr rückt vor, nicht das Token."""
        spaeter = time.time() + FRISCHE_SITZUNG_S + 1
        with patch("app.auth.dependencies.time.time", return_value=spaeter):
            resp = await _anlegen(test_client, auth_headers)
        assert resp.status_code == 401
        assert resp.headers.get("X-Frische-Anmeldung") == "1"
        assert "neu anmelden" in resp.json()["detail"]

    async def test_kurz_vor_der_grenze_geht_es_noch(self, test_client, auth_headers, audit):
        spaeter = time.time() + FRISCHE_SITZUNG_S - 30
        with patch("app.auth.dependencies.time.time", return_value=spaeter):
            assert (await _anlegen(test_client, auth_headers)).status_code == 201

    async def test_kein_stepup_mehr_noetig_und_keins_moeglich(self, test_client, auth_headers):
        """Seit 0.19 gibt es für das Token-Anlegen keine Step-up-Aktion mehr."""
        resp = await test_client.get(
            "/auth/step-up?action=create_token&resource_id=", headers=auth_headers
        )
        assert resp.status_code == 400

    async def test_vorschlag_des_formulars_wird_angenommen(self, test_client, auth_headers, audit):
        """Das vorgeschlagene Datum (heute + 365 Tage) liegt auf der Grenze — es muss gehen.
        Bis 19.10.2026 lehnte der sekundengenaue Vergleich genau den Vorschlag ab."""
        auskunft = (await test_client.get("/tokens/scopes", headers=auth_headers)).json()
        resp = await test_client.post("/tokens", headers=auth_headers, json={
            "name": "Vorschlag", "scopes": ["planning:read"],
            "gueltig_bis": auskunft["vorschlag_gueltig_bis"],
        })
        assert resp.status_code == 201, resp.text

    async def test_ein_tag_ueber_dem_jahr_wird_abgelehnt(self, test_client, auth_headers, audit):
        resp = await _anlegen(test_client, auth_headers, tage=366)
        assert resp.status_code == 422

    async def test_laenger_als_ein_jahr_wird_abgelehnt(self, test_client, auth_headers, audit):
        resp = await _anlegen(test_client, auth_headers, tage=400)
        assert resp.status_code == 422
        assert "Jahr" in resp.text

    async def test_ohne_scope_wird_abgelehnt(self, test_client, auth_headers, audit):
        resp = await _anlegen(test_client, auth_headers, scopes=[])
        assert resp.status_code == 422

    async def test_schueler_kommen_nicht_an_den_endpunkt(
        self, test_client, auth_headers_student
    ):
        resp = await test_client.post(
            "/tokens",
            json={"name": "Tablet", "scopes": ["context:read"],
                  "gueltig_bis": (date.today() + timedelta(days=1)).isoformat()},
            headers=auth_headers_student,
        )
        assert resp.status_code == 403, resp.text

    async def test_heutiges_datum_ergibt_kein_totes_token(
        self, test_client, auth_headers, audit
    ):
        """`gueltig_bis` ist ein Tag, kein Zeitpunkt — gemeint ist dessen Ende.

        Mit Mitternacht zu Tagesbeginn wäre ein heute angelegtes Token sofort abgelaufen.
        """
        resp = await _anlegen(test_client, auth_headers, tage=0)
        assert resp.status_code == 201, resp.text
        ablauf = datetime.fromisoformat(resp.json()["eintrag"]["expires_at"].replace("Z", "+00:00"))
        assert ablauf > datetime.now(timezone.utc)


class TestListeUndWiderruf:
    async def test_liste_zeigt_kein_klartext_token(self, test_client, auth_headers, audit):
        klartext = (await _anlegen(test_client, auth_headers)).json()["token"]
        resp = await test_client.get("/tokens", headers=auth_headers)
        assert resp.status_code == 200
        assert klartext not in resp.text

    async def test_widerruf_ohne_stepup(self, test_client, auth_headers, audit):
        """Einen Zugang zu **beenden** ist die sichere Richtung — keine Hürde davor."""
        eintrag = (await _anlegen(test_client, auth_headers)).json()["eintrag"]
        resp = await test_client.delete(f"/tokens/{eintrag['id']}", headers=auth_headers)
        assert resp.status_code == 204, resp.text
        liste = (await test_client.get("/tokens", headers=auth_headers)).json()
        assert next(t for t in liste if t["id"] == eintrag["id"])["revoked_at"] is not None

    async def test_fremdes_token_ist_404(self, test_client, auth_headers_teacher2, auth_headers, audit):
        eintrag = (await _anlegen(test_client, auth_headers)).json()["eintrag"]
        resp = await test_client.delete(
            f"/tokens/{eintrag['id']}", headers=auth_headers_teacher2
        )
        assert resp.status_code == 404

    async def test_widerrufene_bleiben_in_der_liste(self, test_client, auth_headers, audit):
        eintrag = (await _anlegen(test_client, auth_headers)).json()["eintrag"]
        await test_client.delete(f"/tokens/{eintrag['id']}", headers=auth_headers)
        liste = (await test_client.get("/tokens", headers=auth_headers)).json()
        assert any(t["id"] == eintrag["id"] for t in liste)


class TestEinTokenLegtKeinTokenAn:
    """Sonst wäre der Widerruf wirkungslos."""

    async def test_token_erreicht_die_verwaltung_nicht(
        self, test_client, auth_headers, db, audit
    ):
        klartext, _ = await token_dienst.erzeuge(
            db, pseudonym=TEACHER1_PSEUDO, name="Spiegel",
            scopes=sorted(token_dienst.SCOPES),
            gueltig_bis=datetime.now(timezone.utc) + timedelta(days=1),
            rollen=["teacher"],
        )
        kopf = {"Authorization": f"Bearer {klartext}"}
        for methode, pfad in (("get", "/tokens"), ("get", "/tokens/scopes")):
            resp = await getattr(test_client, methode)(pfad, headers=kopf)
            assert resp.status_code == 403, f"{pfad}: {resp.status_code}"


class TestScopeAuskunft:
    async def test_beschriftungen_decken_alle_scopes_ab(self, test_client, auth_headers):
        resp = await test_client.get("/tokens/scopes", headers=auth_headers)
        assert resp.status_code == 200
        daten = resp.json()
        assert {s["key"] for s in daten["scopes"]} == set(token_dienst.SCOPES)
        assert all(s["label"] for s in daten["scopes"])
        assert daten["max_tage"] == token_dienst.MAX_GUELTIGKEIT.days


class TestStepupBleibtGebunden:
    """Nach dem Wegfall des ressourcenlosen Step-ups: Jede Aktion braucht ihren Antrag."""

    async def test_aktion_ohne_ressource_wird_abgelehnt(self, test_client, auth_headers):
        resp = await test_client.get(
            "/auth/step-up?action=approve&resource_id=", headers=auth_headers
        )
        assert resp.status_code == 400

    async def test_aktion_mit_ressource_geht(self, test_client, auth_headers):
        resp = await test_client.get(
            "/auth/step-up?action=approve&resource_id=00000000-0000-0000-0000-000000000001",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
