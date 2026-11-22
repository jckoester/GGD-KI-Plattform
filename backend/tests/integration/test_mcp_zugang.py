"""Anmeldung am MCP-Server mit Zugangstoken (0.54, Päckchen AW Schritt 2) — gegen die echte
Token-Prüfung und Datenbank. Erfordert TEST_DATABASE_URL."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import tokens
from app.auth.scopes import benoetigter_scope, pruefe_zugang
from app.db.models import PersonalAccessToken, PseudonymAudit
from app.mcp.auth import SCOPE, ZugangstokenPruefer, principal

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def fabrik(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def person(fabrik):
    """Eine Lehrkraft mit eigenem Pseudonym; räumt Token und Audit-Zeile wieder ab."""
    pseudo = f"mcp-{uuid.uuid4().hex[:10]}"
    async with fabrik() as db:
        db.add(PseudonymAudit(pseudonym=pseudo, role="teacher", roles=["teacher"], grade=None))
        await db.commit()
    yield pseudo
    async with fabrik() as db:
        await db.execute(sa.delete(PersonalAccessToken).where(PersonalAccessToken.pseudonym == pseudo))
        await db.execute(sa.delete(PseudonymAudit).where(PseudonymAudit.pseudonym == pseudo))
        await db.commit()


async def _token(fabrik, pseudo, scopes=(SCOPE,), tage=30):
    async with fabrik() as db:
        klartext, zeile = await tokens.erzeuge(
            db, pseudonym=pseudo, name="Claude", scopes=list(scopes),
            gueltig_bis=datetime.now(timezone.utc) + timedelta(days=tage), rollen=["teacher"])
    return klartext, zeile.id


async def test_gueltiges_token_wird_zur_person(fabrik, person):
    klartext, tid = await _token(fabrik, person)
    zugang = await ZugangstokenPruefer(fabrik).verify_token(klartext)
    assert zugang is not None
    assert (zugang.subject, zugang.client_id, zugang.scopes) == (person, f"pat:{tid}", [SCOPE])
    p = principal(zugang)
    assert (p.sub, p.roles, p.preview, p.token_scopes) == (person, ["teacher"], None, [SCOPE])
    async with fabrik() as db:
        assert (await db.get(PersonalAccessToken, tid)).last_used_at is not None


async def test_ohne_curriculum_scope_kein_zugang(fabrik, person):
    """F3: `context:read` genügt nicht — auch nicht zusammen mit anderen Scopes."""
    klartext, _ = await _token(fabrik, person, scopes=("context:read", "planning:read"))
    assert await ZugangstokenPruefer(fabrik).verify_token(klartext) is None


async def test_widerrufen_abgelaufen_unbekannt(fabrik, person):
    pruefer = ZugangstokenPruefer(fabrik)
    klartext, tid = await _token(fabrik, person)
    async with fabrik() as db:
        assert await tokens.widerrufe(db, tid, person)
    assert await pruefer.verify_token(klartext) is None

    klartext, tid = await _token(fabrik, person)
    async with fabrik() as db:
        await db.execute(sa.update(PersonalAccessToken).where(PersonalAccessToken.id == tid)
                         .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db.commit()
    assert await pruefer.verify_token(klartext) is None

    assert await pruefer.verify_token(tokens.PRAEFIX + "geraten") is None
    assert await pruefer.verify_token("kein-token") is None


async def test_entzogene_rolle_und_massenwiderruf_sperren(fabrik, person):
    pruefer = ZugangstokenPruefer(fabrik)
    klartext, _ = await _token(fabrik, person)
    async with fabrik() as db:
        audit = await db.get(PseudonymAudit, person)
        audit.role, audit.roles = "student", ["student"]
        await db.commit()
    assert await pruefer.verify_token(klartext) is None

    async with fabrik() as db:
        audit = await db.get(PseudonymAudit, person)
        audit.role, audit.roles = "teacher", ["teacher"]
        await db.commit()
    assert await pruefer.verify_token(klartext) is not None
    async with fabrik() as db:
        audit = await db.get(PseudonymAudit, person)
        audit.revoked_all_before = datetime.now(timezone.utc) + timedelta(seconds=1)
        await db.commit()
    assert await pruefer.verify_token(klartext) is None


def test_curriculum_scope_oeffnet_keinen_rest_weg():
    """Der Scope ist nur für den MCP-Server: Das Gatter der REST-Router kennt ihn nicht."""
    for methode, pfad in (("GET", "/context/nodes"), ("POST", "/context/search"),
                          ("GET", "/planning/x"), ("GET", "/context/curricula/x"), ("GET", "/mcp")):
        assert benoetigter_scope(methode, pfad) != SCOPE
        with pytest.raises(Exception):
            pruefe_zugang([SCOPE], methode, pfad)


def test_principal_ohne_zugang_ist_ein_fehler():
    with pytest.raises(PermissionError):
        principal(None)
