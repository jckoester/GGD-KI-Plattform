"""Zustimmung zu einem KI-Programm (0.55, Päckchen AX Schritt 4) — die Routen hinter
`/oauth/consent`. Erfordert TEST_DATABASE_URL."""
import base64
import hashlib
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.oauth import router
from app.auth import tokens
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.auth.vorschau import Vorschau
from app.db.models import OAuthClient, PersonalAccessToken, PseudonymAudit
from app.mcp.server import einhaengen, lebenszyklus

pytestmark = pytest.mark.asyncio

HOST = "ki.schule.test"
RUECK = "https://claude.ai/api/mcp/auth_callback"


@pytest_asyncio.fixture
async def fabrik(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def person(fabrik):
    pseudo = f"oz-{uuid.uuid4().hex[:10]}"
    async with fabrik() as db:
        db.add(PseudonymAudit(pseudonym=pseudo, role="teacher", roles=["teacher"], grade=None))
        await db.commit()
    yield pseudo
    async with fabrik() as db:
        await db.execute(sa.delete(PersonalAccessToken).where(PersonalAccessToken.pseudonym == pseudo))
        await db.execute(sa.delete(OAuthClient).where(OAuthClient.metadaten["client_name"].astext == f"Test {pseudo}"))
        await db.execute(sa.delete(PseudonymAudit).where(PseudonymAudit.pseudonym == pseudo))
        await db.commit()


def _user(pseudo, *rollen, preview=None):
    return JwtPayload(sub=pseudo, roles=list(rollen), grade=None, jti="j", iat=0, exp=9999999999, preview=preview)


@asynccontextmanager
async def _app(fabrik, user=None, *, aktiv=True):
    app = FastAPI()
    app.include_router(router)
    app.state.mcp_server = einhaengen(app, aktiv=aktiv, oeffentliche_url=f"https://{HOST}/api/mcp",
                                      sitzung=fabrik, geheimnis="test-geheim", frontend=f"https://{HOST}")
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    async with lebenszyklus(app.state.mcp_server):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=f"https://{HOST}") as c:
            yield c


async def _anfrage(c, pseudo):
    client = (await c.post("/register", json={"client_name": f"Test {pseudo}", "redirect_uris": [RUECK]})).json()
    verifier = uuid.uuid4().hex * 2
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    r = await c.get("/authorize", params={"response_type": "code", "client_id": client["client_id"],
                                          "redirect_uri": RUECK, "state": "st", "code_challenge": challenge,
                                          "code_challenge_method": "S256"})
    return parse_qs(urlsplit(r.headers["location"]).query)["anfrage"][0]


async def test_lehrkraft_sieht_die_anfrage_und_stimmt_zu(fabrik, person):
    async with _app(fabrik, _user(person, "teacher")) as c:
        anfrage = await _anfrage(c, person)
        info = (await c.get("/oauth/anfrage", params={"anfrage": anfrage})).json()
        assert (info["programm"], info["ruecksprung"], info["tage"]) == (f"Test {person}", "claude.ai", 90)
        assert info["berechtigung"] == tokens.SCOPE_BESCHRIFTUNG["curriculum:read"]
        r = await c.post("/oauth/entscheidung", json={"anfrage": anfrage, "zulassen": True})
        assert r.status_code == 200, r.text
        weiter = r.json()["weiter"]
        assert weiter.startswith(RUECK + "?")
        q = parse_qs(urlsplit(weiter).query)
        assert q["state"] == ["st"] and q["code"]


async def test_ablehnen_schickt_access_denied(fabrik, person):
    async with _app(fabrik, _user(person, "admin", "teacher")) as c:
        anfrage = await _anfrage(c, person)
        weiter = (await c.post("/oauth/entscheidung", json={"anfrage": anfrage, "zulassen": False})).json()["weiter"]
        assert parse_qs(urlsplit(weiter).query) == {"error": ["access_denied"], "state": ["st"]}


async def test_schuelerin_und_vorschau_gesperrt(fabrik, person):
    vorschau = Vorschau(echte_rollen=["teacher"], gruppe_id=1, beginn=0, sitzung_ablauf=2**31)
    for user in (_user(person, "student"), _user(person, "student", preview=vorschau)):
        async with _app(fabrik, user) as c:
            anfrage = await _anfrage(c, person)
            assert (await c.get("/oauth/anfrage", params={"anfrage": anfrage})).status_code == 403
            r = await c.post("/oauth/entscheidung", json={"anfrage": anfrage, "zulassen": True})
            assert r.status_code == 403


async def test_ohne_sitzung_401_und_zugangstoken_gesperrt(fabrik, person, monkeypatch):
    """Ohne Sitzung 401 — die Seite führt dann zur Anmeldung. Ein Zugangstoken (auch mit
    `curriculum:read`) kommt nicht herein: `/oauth` steht nicht im Gatter der Scopes."""
    from app.db import session as db_session_modul

    monkeypatch.setattr(db_session_modul, "AsyncSessionLocal", fabrik)
    async with fabrik() as db:
        klartext, _ = await tokens.erzeuge(db, pseudonym=person, name="t", scopes=["curriculum:read"],
                                           gueltig_bis=datetime.now(timezone.utc) + timedelta(days=1),
                                           rollen=["teacher"])
    app = FastAPI()
    app.include_router(router)
    from app.db.session import get_db

    async def _db():
        async with fabrik() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=f"https://{HOST}") as c:
        assert (await c.get("/oauth/anfrage", params={"anfrage": "x"})).status_code == 401
        r = await c.get("/oauth/anfrage", params={"anfrage": "x"}, headers={"authorization": f"Bearer {klartext}"})
        assert r.status_code == 403
        assert r.json()["detail"] == "Dieser Bereich ist für Zugangstoken gesperrt."


async def test_aus_404_und_kaputte_anfrage_400(fabrik, person):
    async with _app(fabrik, _user(person, "teacher"), aktiv=False) as c:
        assert (await c.get("/oauth/anfrage", params={"anfrage": "x"})).status_code == 404
    async with _app(fabrik, _user(person, "teacher")) as c:
        r = await c.get("/oauth/anfrage", params={"anfrage": "kein.jwt"})
        assert r.status_code == 400 and "neu verbinden" in r.json()["detail"]
