"""Audit-Log: nur anhängen (0.28, ADR-010 §2.5).

Der Trigger weist UPDATE, DELETE und TRUNCATE ab — auch für den Benutzer `postgres`, mit dem
die Anwendung läuft. Nur eine Transaktion mit `SET LOCAL audit.aufraeumen = 'on'` darf löschen
(Aufräum-Lauf) oder ändern (Platzhalter bei Kontolöschung). Erfordert TEST_DATABASE_URL.
"""
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio

EINFUEGEN = sa.text(
    "INSERT INTO audit_log (category, event_type, actor_pseudonym, retention_class) "
    "VALUES ('system', 'test_tabelle', 'audit-test', 'system') RETURNING id"
)


async def _sitzung(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)()


async def test_einfuegen_geht_aendern_loeschen_leeren_nicht(async_engine):
    async with await _sitzung(async_engine) as db:
        zeile = (await db.execute(EINFUEGEN)).scalar_one()
        await db.commit()

    for befehl in (
        sa.text("UPDATE audit_log SET event_type = 'x' WHERE id = :id"),
        sa.text("DELETE FROM audit_log WHERE id = :id"),
        sa.text("TRUNCATE audit_log"),
    ):
        async with await _sitzung(async_engine) as db:
            with pytest.raises(DBAPIError, match="nur zum Anhängen"):
                await db.execute(befehl, {"id": zeile})
            await db.rollback()

    # Mit der Sitzungsvariablen des Aufräum-Laufs geht es — nur für diese Transaktion.
    async with await _sitzung(async_engine) as db:
        await db.execute(sa.text("SET LOCAL audit.aufraeumen = 'on'"))
        await db.execute(sa.text("DELETE FROM audit_log WHERE id = :id"), {"id": zeile})
        await db.commit()
    async with await _sitzung(async_engine) as db:
        assert (await db.execute(sa.text("SELECT count(*) FROM audit_log WHERE id = :id"),
                                 {"id": zeile})).scalar_one() == 0
        # Die Variable gilt nicht über die Transaktion hinaus.
        zweite = (await db.execute(EINFUEGEN)).scalar_one()
        await db.commit()
    async with await _sitzung(async_engine) as db:
        with pytest.raises(DBAPIError, match="nur zum Anhängen"):
            await db.execute(sa.text("DELETE FROM audit_log WHERE id = :id"), {"id": zweite})
        await db.rollback()
    async with await _sitzung(async_engine) as db:
        await db.execute(sa.text("SET LOCAL audit.aufraeumen = 'on'"))
        await db.execute(sa.text("DELETE FROM audit_log WHERE event_type = 'test_tabelle'"))
        await db.commit()


async def test_kategorie_wird_geprueft(async_engine):
    async with await _sitzung(async_engine) as db:
        with pytest.raises(DBAPIError):
            await db.execute(sa.text(
                "INSERT INTO audit_log (category, event_type, retention_class) "
                "VALUES ('quatsch', 'x', 'system')"))
        await db.rollback()
