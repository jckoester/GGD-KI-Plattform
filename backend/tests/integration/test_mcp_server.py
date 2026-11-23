"""Der MCP-Server in der App (0.54, Päckchen AW Schritt 3) — über die ASGI-App mit echter
Token-Prüfung. Erfordert TEST_DATABASE_URL."""
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import tokens
from app.db.models import PersonalAccessToken, PseudonymAudit
from app.mcp.auth import SCOPE, ZugangstokenPruefer
from app.mcp.server import einhaengen, lebenszyklus

pytestmark = pytest.mark.asyncio

URL = "https://ki.schule.test/api/mcp"
HOST = "ki.schule.test"
KOPF = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18", "capabilities": {},
    "clientInfo": {"name": "test", "version": "0"}}}


@pytest_asyncio.fixture
async def fabrik(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def person(fabrik):
    pseudo = f"mcp-{uuid.uuid4().hex[:10]}"
    async with fabrik() as db:
        db.add(PseudonymAudit(pseudonym=pseudo, role="teacher", roles=["teacher"], grade=None))
        await db.commit()
    yield pseudo
    async with fabrik() as db:
        await db.execute(sa.delete(PersonalAccessToken).where(PersonalAccessToken.pseudonym == pseudo))
        await db.execute(sa.delete(PseudonymAudit).where(PseudonymAudit.pseudonym == pseudo))
        await db.commit()


async def _token(fabrik, pseudo, scopes=(SCOPE,)):
    async with fabrik() as db:
        klartext, _ = await tokens.erzeuge(
            db, pseudonym=pseudo, name="Claude", scopes=list(scopes),
            gueltig_bis=datetime.now(timezone.utc) + timedelta(days=30), rollen=["teacher"])
    return klartext


@asynccontextmanager
async def _verbunden(fabrik):
    """Kein Fixture: Die Task-Gruppe des Session-Managers muss im selben Task enden, in dem
    sie begann — pytest-asyncio räumt Fixtures in einem anderen auf."""
    app = FastAPI()
    server = einhaengen(app, aktiv=True, oeffentliche_url=URL, sitzung=fabrik)
    async with lebenszyklus(server):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url=f"https://{HOST}") as c:
            yield c


def _mit(token):
    return {**KOPF, "authorization": f"Bearer {token}"}


async def test_ohne_token_401(fabrik):
    async with _verbunden(fabrik) as client:
        r = await client.post("/mcp", json=INIT, headers=KOPF)
        assert r.status_code == 401
        assert r.headers["www-authenticate"].lower().startswith("bearer")


async def test_mit_token_initialisieren_und_werkzeuge_auflisten(fabrik, person):
    async with _verbunden(fabrik) as client:
        kopf = _mit(await _token(fabrik, person))
        r = await client.post("/mcp", json=INIT, headers=kopf)
        assert r.status_code == 200, r.text
        ergebnis = r.json()["result"]
        assert ergebnis["serverInfo"]["name"] == "ggd-ki-plattform"
        assert "Schreiben ist über diese Schnittstelle nicht möglich" in ergebnis["instructions"]
        r = await client.post("/mcp", headers={**kopf, "mcp-protocol-version": ergebnis["protocolVersion"]},
                              json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert r.status_code == 200, r.text
        assert "tools" in r.json()["result"]


async def test_token_ohne_scope_und_geratenes_token_401(fabrik, person):
    async with _verbunden(fabrik) as client:
        for token in (await _token(fabrik, person, scopes=("context:read",)), tokens.PRAEFIX + "x"):
            r = await client.post("/mcp", json=INIT, headers=_mit(token))
            assert r.status_code == 401


async def test_fremder_host_abgewiesen(fabrik, person):
    async with _verbunden(fabrik) as client:
        r = await client.post("/mcp", json=INIT, headers={**_mit(await _token(fabrik, person)), "host": "boese.test"})
        assert r.status_code in (400, 421), r.status_code


async def test_drossel_je_token(fabrik, person, monkeypatch):
    async with _verbunden(fabrik) as client:
        from app.ratelimit import config as drossel_config

        monkeypatch.setattr(drossel_config, "resolve", lambda bucket, rollen: (2, 60.0) if bucket == "mcp" else (999, 60.0))
        kopf, anderes = _mit(await _token(fabrik, person)), _mit(await _token(fabrik, person))
        assert [(await client.post("/mcp", json=INIT, headers=kopf)).status_code for _ in range(2)] == [200, 200]
        r = await client.post("/mcp", json=INIT, headers=kopf)
        assert r.status_code == 429
        assert int(r.headers["retry-after"]) >= 1
        # ein anderes Token hat seinen eigenen Zähler
        assert (await client.post("/mcp", json=INIT, headers=anderes)).status_code == 200


def test_aus_ist_aus():
    app = FastAPI()
    assert einhaengen(app, aktiv=False, oeffentliche_url=URL) is None
    assert einhaengen(app, aktiv=True, oeffentliche_url="") is None  # ohne Adresse kein Server
    assert not [r for r in app.router.routes if getattr(r, "path", None) == "/mcp"]


async def test_aus_antwortet_404():
    """F4 als HTTP-Antwort: Ohne MCP_AKTIV gibt es /mcp nicht."""
    app = FastAPI()
    assert einhaengen(app, aktiv=False, oeffentliche_url=URL) is None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=f"https://{HOST}") as c:
        assert (await c.post("/mcp", json=INIT, headers=KOPF)).status_code == 404


async def test_widerruf_wirkt_beim_naechsten_aufruf(fabrik, person):
    """Zustandslos: Jede Nachricht prüft das Token neu — ein Widerruf im Profil beendet auch eine
    laufende Verbindung sofort."""
    klartext = await _token(fabrik, person)
    async with _verbunden(fabrik) as client:
        assert (await client.post("/mcp", json=INIT, headers=_mit(klartext))).status_code == 200
        async with fabrik() as db:
            zeile = (await db.execute(sa.select(PersonalAccessToken).where(
                PersonalAccessToken.pseudonym == person))).scalar_one()
            assert await tokens.widerrufe(db, zeile.id, person)
        r = await client.post("/mcp", headers=_mit(klartext),
                              json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert r.status_code == 401
