"""Die Selbstverwaltung der Zugangstoken im Profil — samt Re-Authentifizierung.

Zwei Zusagen stehen hier im Mittelpunkt:

* **Anlegen verlangt frisches Step-up.** Ein übernommenes Browser-Fenster soll sich
  keinen Dauerzugang ausstellen können, der das Ausloggen überlebt.
* **Ein Token kann kein Token anlegen.** `/tokens` steht nicht in der Scope-Tabelle;
  sonst wäre ein Widerruf wirkungslos — man widerruft eines, das nächste steht bereit.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from app.auth import tokens as token_dienst
from app.auth.stepup import (
    STEPUP_AKTIONEN_OHNE_RESSOURCE,
    issue_stepup_token,
    ressource_erwartet,
)
from app.config import settings
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


def _stepup(action: str = "create_token") -> str:
    """Ein frisches, ressourcenloses Step-up-Token."""
    return issue_stepup_token(settings.jwt_secret, TEACHER1_PSEUDO, action, "")


def _mit_stepup(auth_headers: dict, stepup: str | None) -> dict:
    """Sitzungs- und Step-up-Cookie in **einer** Kopfzeile.

    Getrennt geht es nicht: `auth_headers` setzt `Cookie:` roh, und httpx' eigener
    Cookie-Jar aus `cookies=` schreibt dieselbe Kopfzeile — eine der beiden gewinnt, und
    zwar stumm. Die erste Fassung dieses Tests verlor so das Step-up-Cookie und sah aus
    wie ein Fehler im Guard.
    """
    if stepup is None:
        return dict(auth_headers)
    return {**auth_headers, "Cookie": f"{auth_headers['Cookie']}; stepup={stepup}"}


def _anlegen(test_client, auth_headers, *, name="MacBook", scopes=None, tage=30, stepup=...):
    return test_client.post(
        "/tokens",
        json={
            "name": name,
            "scopes": scopes if scopes is not None else ["planning:read"],
            "gueltig_bis": (date.today() + timedelta(days=tage)).isoformat(),
        },
        headers=_mit_stepup(auth_headers, _stepup() if stepup is ... else stepup),
    )


class TestAnlegen:
    async def test_mit_frischem_stepup(self, test_client, auth_headers, audit):
        resp = await _anlegen(test_client, auth_headers)
        assert resp.status_code == 201, resp.text
        daten = resp.json()
        assert daten["token"].startswith(token_dienst.PRAEFIX)
        assert daten["eintrag"]["scopes"] == ["planning:read"]
        assert daten["eintrag"]["last_used_at"] is None

    async def test_ohne_stepup_kommt_die_aufforderung(self, test_client, auth_headers, audit):
        resp = await _anlegen(test_client, auth_headers, stepup=None)
        assert resp.status_code == 401
        assert resp.headers.get("X-Stepup-Required") == "1"

    async def test_stepup_einer_anderen_aktion_zaehlt_nicht(
        self, test_client, auth_headers, audit
    ):
        """Cross-Action-Reuse: Wer eine Krisen-Freigabe re-authentifiziert hat, hat damit
        noch lange kein Token angelegt (Sicherheits-Audit #3 Teil B)."""
        resp = await _anlegen(test_client, auth_headers, stepup=_stepup("approve"))
        assert resp.status_code == 401

    async def test_stepup_gilt_nur_einmal(self, test_client, auth_headers, audit):
        """Die Nonce: Dasselbe Cookie zweimal einzulösen ist ein Replay."""
        gleiches = _stepup()
        assert (await _anlegen(test_client, auth_headers, stepup=gleiches)).status_code == 201
        zweiter = await _anlegen(test_client, auth_headers, name="Zweites", stepup=gleiches)
        assert zweiter.status_code == 401

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
            headers={**auth_headers_student,
                     "Cookie": f"{auth_headers_student['Cookie']}; stepup={_stepup()}"},
        )
        assert resp.status_code in (401, 403), resp.text

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


class TestRessourcenloses_Stepup:
    """Die Verallgemeinerung selbst — unabhängig vom Token-Endpunkt."""

    def test_create_token_ist_als_ressourcenlos_erklaert(self):
        assert "create_token" in STEPUP_AKTIONEN_OHNE_RESSOURCE
        assert not ressource_erwartet("create_token")

    def test_die_krisen_aktionen_bleiben_gebunden(self):
        for aktion in ("approve", "deny", "read", "export"):
            assert ressource_erwartet(aktion), f"{aktion} verlor seine Ressourcenbindung"

    def test_gebundene_aktion_kann_nicht_ressourcenlos_gefordert_werden(self):
        """Der Riegel gegen den stillen Verlust der Bindung."""
        from app.auth.dependencies import require_fresh_stepup_ohne_ressource

        with pytest.raises(ValueError, match="ressourcengebunden"):
            require_fresh_stepup_ohne_ressource("approve")

    async def test_challenge_verlangt_keine_ressource(self, test_client, auth_headers):
        resp = await test_client.get(
            "/auth/step-up?action=create_token&resource_id=", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text

    async def test_challenge_lehnt_ueberzaehlige_ressource_ab(self, test_client, auth_headers):
        """Symmetrie: Eine ressourcenlose Aktion darf auch keine ID mitbekommen."""
        resp = await test_client.get(
            "/auth/step-up?action=create_token&resource_id=irgendwas", headers=auth_headers
        )
        assert resp.status_code == 400

    async def test_gebundene_aktion_braucht_weiterhin_eine_ressource(
        self, test_client, auth_headers
    ):
        resp = await test_client.get(
            "/auth/step-up?action=approve&resource_id=", headers=auth_headers
        )
        assert resp.status_code == 400
