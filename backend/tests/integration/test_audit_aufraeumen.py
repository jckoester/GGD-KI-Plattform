"""Aufbewahrung des Audit-Logs (0.28, ADR-010 §2.3): Je Klasse verschwindet, was älter ist als
die Frist; `secret` bleibt; der Lauf protokolliert sich selbst. Erfordert TEST_DATABASE_URL."""
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.crons.audit_cleanup_service import AUFBEWAHRUNG_TAGE, cleanup_audit_log

pytestmark = pytest.mark.asyncio

JETZT = datetime(2030, 6, 1, tzinfo=timezone.utc)
MARKE = "aufraeumen-test"


@pytest.fixture
async def bestand(async_engine):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        for klasse, tage in {**AUFBEWAHRUNG_TAGE, "secret": 5000}.items():
            for alter, art in (((tage or 5000) + 1, "alt"), (max((tage or 5000) - 1, 0), "jung")):
                await db.execute(sa.text(
                    "INSERT INTO audit_log (occurred_at, category, event_type, actor_pseudonym, retention_class)"
                    " VALUES (:t, :k, :e, :m, :k)"),
                    {"t": JETZT - timedelta(days=alter), "k": klasse, "e": f"{klasse}_{art}", "m": MARKE})
        await db.commit()
    yield fabrik
    async with fabrik() as db:
        await db.execute(sa.text("SET LOCAL audit.aufraeumen = 'on'"))
        await db.execute(sa.text("DELETE FROM audit_log WHERE actor_pseudonym = :m OR event_type = 'audit_log_cleaned'"), {"m": MARKE})
        await db.commit()


async def _ereignisse(fabrik):
    async with fabrik() as db:
        return set((await db.execute(sa.text(
            "SELECT event_type FROM audit_log WHERE actor_pseudonym = :m"), {"m": MARKE})).scalars())


async def test_frist_je_klasse_und_eigenes_protokoll(bestand):
    async with bestand() as db:
        trocken = await cleanup_audit_log(db, dry_run=True, now=JETZT)
    assert all(trocken.geloescht[k] >= 1 for k in ("auth", "admin", "moderation", "system"))
    assert "auth_alt" in await _ereignisse(bestand)          # Trockenlauf löscht nichts

    async with bestand() as db:
        await cleanup_audit_log(db, now=JETZT)
    uebrig = await _ereignisse(bestand)
    assert uebrig == {"auth_jung", "admin_jung", "moderation_jung", "system_jung", "secret_alt", "secret_jung"}
    async with bestand() as db:
        assert (await db.execute(sa.text(
            "SELECT count(*) FROM audit_log WHERE event_type = 'audit_log_cleaned'"))).scalar_one() >= 1
        # Danach gilt der Trigger wieder: Die Sitzungsvariable war nur für den Lauf gesetzt.
        with pytest.raises(Exception, match="nur zum Anhängen"):
            await db.execute(sa.text("DELETE FROM audit_log WHERE actor_pseudonym = :m"), {"m": MARKE})
        await db.rollback()
