"""Verbrauch des Systemkontos — gegen die echte Datenbank (0.12, Paket 2, AP3).

Was hier an der Datenbank hängt: dass zwei Aufrufe desselben Tages **eine** Zeile
ergeben (Upsert statt zweier Zeilen oder eines Konflikts), dass die Zeitraumgrenzen
einschließlich gelten, und dass `/budget` und `/statistics/costs` die Zeile zeigen —
`/statistics/costs` aber nur ohne Team- und Modellfilter.
"""
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.admin.budgets import _systemverbrauch
from app.api.admin.stats import get_spend
from app.db.models import SystemSpend
from app.litellm import systemkonto
from app.planning.calendar import load_school_year

pytestmark = pytest.mark.asyncio


def _antwort(kosten: str):
    r = MagicMock()
    r.headers = {systemkonto.KOSTENKOPF: kosten}
    return r


@pytest_asyncio.fixture
async def sitzungen(async_engine):
    """Eigene Sitzungen wie im Betrieb — `verbuche` committet selbst, also aufräumen."""
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        await db.execute(delete(SystemSpend))
        await db.commit()
    yield fabrik
    async with fabrik() as db:
        await db.execute(delete(SystemSpend))
        await db.commit()


async def test_zwei_aufrufe_eines_tages_sind_eine_zeile(sitzungen):
    await systemkonto.verbuche(_antwort("1e-07"), sitzungen=sitzungen)
    await systemkonto.verbuche(_antwort("3e-07"), sitzungen=sitzungen)

    async with sitzungen() as db:
        zeilen = (await db.execute(select(SystemSpend))).scalars().all()
    assert len(zeilen) == 1
    assert zeilen[0].tag == datetime.now(systemkonto.BERLIN).date()
    assert zeilen[0].kosten_usd == pytest.approx(4e-07)
    assert zeilen[0].anfragen == 2


async def test_zeitraum_gilt_einschliesslich(db_session):
    for tag, kosten in ((date(2026, 3, 1), 1.0), (date(2026, 3, 15), 2.0),
                        (date(2026, 3, 16), 4.0)):
        db_session.add(SystemSpend(tag=tag, kosten_usd=kosten, anfragen=10))
    await db_session.flush()

    assert await systemkonto.summe(db_session, date(2026, 3, 1), date(2026, 3, 15)) \
        == (pytest.approx(3.0), 20)
    assert await systemkonto.summe(db_session, date(2026, 3, 2)) == (pytest.approx(6.0), 20)


async def test_budget_zaehlt_ab_schuljahresbeginn(db_session):
    beginn = load_school_year().beginn
    db_session.add(SystemSpend(tag=beginn - timedelta(days=1), kosten_usd=5.0, anfragen=1))
    db_session.add(SystemSpend(tag=beginn, kosten_usd=0.002, anfragen=3))
    await db_session.flush()

    info = await _systemverbrauch(db_session, eur_usd=2.0)
    assert info.verbraucht_eur == pytest.approx(0.001)
    assert info.anfragen == 3


async def _spend(db, **filter):
    return await get_spend(
        from_date=date(2026, 3, 1), to_date=date(2026, 3, 31), granularity="month",
        _=None, db=db, **{"team_id": None, "model": None, **filter},
    )


async def test_kostenseite_zeigt_den_posten_ohne_filter(db_session):
    db_session.add(SystemSpend(tag=date(2026, 3, 10), kosten_usd=0.0003, anfragen=7))
    db_session.add(SystemSpend(tag=date(2026, 4, 1), kosten_usd=9.0, anfragen=1))
    await db_session.flush()

    antwort = await _spend(db_session)
    assert antwort.system is not None
    assert antwort.system.usd == pytest.approx(0.0003)
    assert antwort.system.anfragen == 7
    assert antwort.system.eur == pytest.approx(0.0003 / antwort.eur_usd_rate)
    # In keinem Balken: Die Einträge kommen allein aus den Nachrichten.
    assert sum(e.usd for e in antwort.entries) == antwort.total_usd


@pytest.mark.parametrize("filter", [{"team_id": "lehrkraefte"}, {"model": "chat-standard"}])
async def test_kostenseite_laesst_den_posten_bei_filtern_weg(db_session, filter):
    db_session.add(SystemSpend(tag=date(2026, 3, 10), kosten_usd=0.0003, anfragen=7))
    await db_session.flush()

    assert (await _spend(db_session, **filter)).system is None
