"""OAuth über HTTP (0.55, Päckchen AX Schritt 3) — die Endpunkte des SDK in der App, der Ablauf wie
bei Claude: Metadaten → Registrierung → Authorize → (Zustimmung, Schritt 4) → Token → MCP-Aufruf →
Refresh → Widerruf. Erfordert TEST_DATABASE_URL."""
import base64
import hashlib
import uuid
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import JwtPayload
from app.db.models import OAuthClient, PersonalAccessToken, PseudonymAudit
from app.mcp.server import einhaengen, lebenszyklus

pytestmark = pytest.mark.asyncio

HOST = "ki.schule.test"
URL = f"https://{HOST}/api/mcp"
ISSUER = f"https://{HOST}/api"
RUECK = "https://claude.ai/api/mcp/auth_callback"
KOPF = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}


@pytest_asyncio.fixture
async def fabrik(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def person(fabrik):
    pseudo = f"oh-{uuid.uuid4().hex[:10]}"
    async with fabrik() as db:
        db.add(PseudonymAudit(pseudonym=pseudo, role="teacher", roles=["teacher"], grade=None))
        await db.commit()
    yield pseudo
    async with fabrik() as db:
        await db.execute(sa.delete(PersonalAccessToken).where(PersonalAccessToken.pseudonym == pseudo))
        await db.execute(sa.delete(OAuthClient).where(OAuthClient.metadaten["client_name"].astext == f"Test {pseudo}"))
        await db.execute(sa.delete(PseudonymAudit).where(PseudonymAudit.pseudonym == pseudo))
        await db.commit()


@asynccontextmanager
async def _verbunden(fabrik):
    app = FastAPI()
    server = einhaengen(app, aktiv=True, oeffentliche_url=URL, sitzung=fabrik, geheimnis="test-geheim",
                        frontend=f"https://{HOST}")
    async with lebenszyklus(server):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=f"https://{HOST}") as c:
            yield c, server._auth_server_provider


def _pkce():
    verifier = uuid.uuid4().hex * 2
    return verifier, base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


async def _registrieren(c, pseudo, redirect=RUECK):
    return await c.post("/register", json={"client_name": f"Test {pseudo}", "redirect_uris": [redirect],
                                           "token_endpoint_auth_method": "client_secret_post",
                                           "grant_types": ["authorization_code", "refresh_token"]})


async def _bis_token(c, provider, pseudo):
    client = (await _registrieren(c, pseudo)).json()
    verifier, challenge = _pkce()
    r = await c.get("/authorize", params={
        "response_type": "code", "client_id": client["client_id"], "redirect_uri": RUECK, "state": "s1",
        "code_challenge": challenge, "code_challenge_method": "S256", "resource": URL})
    assert r.status_code == 302, r.text
    ziel = r.headers["location"]
    assert ziel.startswith(f"https://{HOST}/oauth/consent?anfrage=")
    # Zustimmung (Schritt 4: Seite im Frontend) — hier direkt am Provider
    rueck = await provider.code_ausstellen(parse_qs(urlsplit(ziel).query)["anfrage"][0],
                                           JwtPayload(sub=pseudo, roles=["teacher"], grade=None, jti="j", iat=0,
                                                      exp=9999999999))
    q = parse_qs(urlsplit(rueck).query)
    assert q["state"] == ["s1"]
    r = await c.post("/token", data={
        "grant_type": "authorization_code", "code": q["code"][0], "redirect_uri": RUECK,
        "code_verifier": verifier, "client_id": client["client_id"], "client_secret": client["client_secret"],
        "resource": URL})
    assert r.status_code == 200, r.text
    return client, r.json()


async def test_metadaten_unter_den_erwarteten_adressen(fabrik):
    async with _verbunden(fabrik) as (c, _):
        r = await c.get("/.well-known/oauth-protected-resource/api/mcp")
        assert r.status_code == 200
        assert (r.json()["resource"], r.json()["authorization_servers"]) == (URL, [ISSUER])
        # RFC 8414 mit Pfad (nginx reicht /.well-known ungekürzt durch) und über /api (gekürzt)
        for pfad in ("/.well-known/oauth-authorization-server/api", "/.well-known/oauth-authorization-server"):
            m = (await c.get(pfad)).json()
            assert m["issuer"] == ISSUER, pfad
            assert (m["authorization_endpoint"], m["token_endpoint"], m["registration_endpoint"]) == (
                f"{ISSUER}/authorize", f"{ISSUER}/token", f"{ISSUER}/register")
            assert "S256" in m["code_challenge_methods_supported"]
        r = await c.post("/mcp", json=INIT, headers=KOPF)
        assert r.status_code == 401
        assert f'resource_metadata="https://{HOST}/.well-known/oauth-protected-resource/api/mcp"' in r.headers[
            "www-authenticate"]


async def test_ganzer_ablauf_bis_zum_werkzeug(fabrik, person):
    async with _verbunden(fabrik) as (c, provider):
        client, t = await _bis_token(c, provider, person)
        assert t["token_type"].lower() == "bearer" and t["expires_in"] == 3600
        kopf = {**KOPF, "authorization": f"Bearer {t['access_token']}"}
        r = await c.post("/mcp", json=INIT, headers=kopf)
        assert r.status_code == 200, r.text
        kopf["mcp-protocol-version"] = r.json()["result"]["protocolVersion"]
        r = await c.post("/mcp", headers=kopf, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        from tests.integration.test_mcp_werkzeuge import WERKZEUGE
        assert {w["name"] for w in r.json()["result"]["tools"]} == WERKZEUGE

        # Refresh: neue Token, der alte Zugriff gilt bis zu seinem Ablauf weiter
        r = await c.post("/token", data={"grant_type": "refresh_token", "refresh_token": t["refresh_token"],
                                         "client_id": client["client_id"], "client_secret": client["client_secret"]})
        assert r.status_code == 200, r.text
        neu = r.json()
        assert neu["refresh_token"] != t["refresh_token"]
        # Der eingelöste Refresh-Token noch einmal: abgewiesen, und die Verbindung endet
        r = await c.post("/token", data={"grant_type": "refresh_token", "refresh_token": t["refresh_token"],
                                         "client_id": client["client_id"], "client_secret": client["client_secret"]})
        assert r.status_code == 400
        r = await c.post("/mcp", json=INIT, headers={**KOPF, "authorization": f"Bearer {neu['access_token']}"})
        assert r.status_code == 401


async def test_widerruf_ueber_revoke(fabrik, person):
    async with _verbunden(fabrik) as (c, provider):
        client, t = await _bis_token(c, provider, person)
        r = await c.post("/revoke", data={"token": t["refresh_token"], "client_id": client["client_id"],
                                          "client_secret": client["client_secret"]})
        assert r.status_code == 200, r.text
        r = await c.post("/mcp", json=INIT, headers={**KOPF, "authorization": f"Bearer {t['access_token']}"})
        assert r.status_code == 401


async def test_falscher_verifier_und_fremder_redirect(fabrik, person):
    async with _verbunden(fabrik) as (c, _):
        assert (await _registrieren(c, person, "http://boese.test/cb")).status_code == 400
        assert (await _registrieren(c, person, "http://localhost:33418/callback")).status_code == 201
        client = (await _registrieren(c, person)).json()
        _, challenge = _pkce()
        r = await c.get("/authorize", params={
            "response_type": "code", "client_id": client["client_id"], "redirect_uri": "https://boese.test/cb",
            "code_challenge": challenge, "code_challenge_method": "S256"})
        assert r.status_code == 400  # fremder Redirect: keine Weiterleitung dorthin
        r = await c.post("/token", data={"grant_type": "authorization_code", "code": "geraten", "redirect_uri": RUECK,
                                         "code_verifier": "x" * 43, "client_id": client["client_id"],
                                         "client_secret": client["client_secret"]})
        assert r.status_code == 400


async def test_registrierung_gedrosselt_je_ip(fabrik, person, monkeypatch):
    from app.ratelimit import config as drossel_config, store

    store.reset()  # die übrigen Tests registrieren von derselben Test-IP
    monkeypatch.setattr(drossel_config, "resolve", lambda b, r: (2, 60.0) if b == "oauth" else (999, 60.0))
    async with _verbunden(fabrik) as (c, _):
        codes = [(await _registrieren(c, person)).status_code for _ in range(3)]
    store.reset()
    assert codes == [201, 201, 429]


async def _code(c, provider, pseudo):
    """Bis zum Code, ohne einzulösen: (Client, Code, Verifier)."""
    client = (await _registrieren(c, pseudo)).json()
    verifier, challenge = _pkce()
    r = await c.get("/authorize", params={"response_type": "code", "client_id": client["client_id"],
                                          "redirect_uri": RUECK, "code_challenge": challenge,
                                          "code_challenge_method": "S256"})
    rueck = await provider.code_ausstellen(parse_qs(urlsplit(r.headers["location"]).query)["anfrage"][0],
                                           JwtPayload(sub=pseudo, roles=["teacher"], grade=None, jti="j", iat=0,
                                                      exp=9999999999))
    return client, parse_qs(urlsplit(rueck).query)["code"][0], verifier


async def test_falscher_verifier_zu_gueltigem_code(fabrik, person):
    """PKCE: Wer den Code abfängt, aber den Verifier nicht kennt, bekommt keine Token."""
    async with _verbunden(fabrik) as (c, provider):
        client, code, verifier = await _code(c, provider, person)
        daten = {"grant_type": "authorization_code", "code": code, "redirect_uri": RUECK,
                 "client_id": client["client_id"], "client_secret": client["client_secret"]}
        r = await c.post("/token", data={**daten, "code_verifier": "falsch" * 8})
        assert r.status_code == 400 and r.json()["error"] == "invalid_grant"
        # Der richtige Verifier geht danach noch — ein Fehlversuch verbraucht den Code nicht
        assert (await c.post("/token", data={**daten, "code_verifier": verifier})).status_code == 200


async def test_abgelaufener_code(fabrik, person):
    from datetime import datetime, timedelta, timezone

    from app.db.models import OAuthCode

    async with _verbunden(fabrik) as (c, provider):
        client, code, verifier = await _code(c, provider, person)
        async with fabrik() as db:
            await db.execute(sa.update(OAuthCode).where(
                OAuthCode.code_hash == hashlib.sha256(code.encode()).hexdigest())
                .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
            await db.commit()
        r = await c.post("/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": RUECK,
                                         "code_verifier": verifier, "client_id": client["client_id"],
                                         "client_secret": client["client_secret"]})
        assert r.status_code == 400 and r.json()["error"] == "invalid_grant"
