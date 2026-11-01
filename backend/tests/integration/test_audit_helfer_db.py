"""Audit-Helfer gegen die Datenbank (0.28): `audit` schreibt mit dem Commit des Aufrufers und
rollt mit ihm zurück; `audit_getrennt` schreibt sofort. Erfordert TEST_DATABASE_URL."""
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import audit as audit_modul

pytestmark = pytest.mark.asyncio

PSEUDO = "audit-helfer-test"


async def _anzahl(fabrik, ereignis):
    async with fabrik() as db:
        return (await db.execute(sa.text(
            "SELECT count(*) FROM audit_log WHERE actor_pseudonym = :p AND event_type = :e"),
            {"p": PSEUDO, "e": ereignis})).scalar_one()


@pytest.fixture
def fabrik(async_engine, monkeypatch):
    f = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.db.session as session_modul
    monkeypatch.setattr(session_modul, "AsyncSessionLocal", f)
    yield f


async def test_audit_folgt_der_transaktion(fabrik):
    async with fabrik() as db:
        await audit_modul.audit(db, "admin", "assistant_approved", akteur=PSEUDO, ziel=("assistant", 1))
        await db.rollback()
    assert await _anzahl(fabrik, "assistant_approved") == 0
    async with fabrik() as db:
        await audit_modul.audit(db, "admin", "assistant_approved", akteur=PSEUDO, ziel=("assistant", 1))
        await db.commit()
    assert await _anzahl(fabrik, "assistant_approved") == 1


async def test_audit_getrennt_schreibt_sofort(fabrik):
    await audit_modul.audit_getrennt("auth", "login_failed", akteur=PSEUDO, daten={"grund": "abgelehnt"})
    assert await _anzahl(fabrik, "login_failed") == 1


@pytest.fixture(autouse=True)
async def aufraeumen(async_engine):
    yield
    f = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with f() as db:
        await db.execute(sa.text("SET LOCAL audit.aufraeumen = 'on'"))
        await db.execute(sa.text("DELETE FROM audit_log WHERE actor_pseudonym = :p"), {"p": PSEUDO})
        await db.commit()
