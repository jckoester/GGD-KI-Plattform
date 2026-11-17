"""`budget_accrual.aktualisiert_am` folgt der letzten Buchung (0.46).

Bis 0.46 nur `server_default` — `merke()` schrieb Schuljahr und Woche fort, der Zeitpunkt blieb
beim ersten Eintrag stehen und taugte nicht als Beleg, wann der Wochenlauf zuletzt gebucht hat.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.budget.accrual import merke
from app.db.models import BudgetAccrual

pytestmark = pytest.mark.asyncio


async def test_merke_setzt_den_zeitpunkt(db_session):
    alt = datetime(2026, 1, 5, tzinfo=timezone.utc)
    p = f"accrual-{uuid.uuid4().hex[:8]}"
    db_session.add(BudgetAccrual(pseudonym=p, schuljahr="2026/27", letzte_woche=3, aktualisiert_am=alt))
    await db_session.flush()

    await merke(db_session, p, bis_woche=4, schuljahr="2026/27")
    await db_session.flush()
    zeile = await db_session.get(BudgetAccrual, p)
    await db_session.refresh(zeile)
    assert zeile.letzte_woche == 4 and zeile.aktualisiert_am > alt
