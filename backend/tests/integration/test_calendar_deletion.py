"""UP-8, Schritt 11 — Löschpfad der Stundenplan-Integration.

Verlässt eine Lehrkraft die Schule, verschwinden mit ihrem Pseudonym auch die beiden
Spuren, die die Kalenderanbindung hinterlässt:

* das **Kürzel** in `user_preferences.preferences` — das einzige Personenmerkmal, das die
  Integration überhaupt speichert (Zugangsdaten liegen schulweit in der Umgebung);
* der **Abrufstatus** in `calendar_sync_status` — Zeitstempel und Fehlertexte je Lehrkraft.

Warum ausgerechnet als Integrationstest: Beide Tabellen hängen **ohne
Fremdschlüssel** am Pseudonym. Ein Mock-Test würde nur beweisen, dass ein DELETE
abgesetzt wurde — nicht, dass danach nichts mehr da ist. Genau das ist hier aber die
Zusage. Erfordert TEST_DATABASE_URL.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from sqlalchemy import func, select

from app.calendar.service import KUERZEL_PREFERENCE_KEY
from app.crons.cleanup_service import cleanup_inactive_accounts
from app.db.models import CalendarSyncStatus, PseudonymAudit, UserPreference

NOW = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
LANGE_WEG = NOW - timedelta(days=200)  # älter als die 90-Tage-Frist → Löschkandidat
GESTERN = NOW - timedelta(days=1)      # aktiv → muss bleiben


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    """Commit auf flush umbiegen, damit der Test-Rollback greift."""
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


async def _lehrkraft(db, pseudonym: str, *, letzter_login: datetime, kuerzel: str = "AK"):
    """Eine Lehrkraft mit Kürzel und Abrufstatus anlegen."""
    db.add(PseudonymAudit(pseudonym=pseudonym, role="teacher", last_login_at=letzter_login))
    db.add(
        UserPreference(
            pseudonym=pseudonym,
            preferences={"theme": "dark", KUERZEL_PREFERENCE_KEY: kuerzel},
        )
    )
    db.add(
        CalendarSyncStatus(
            pseudonym=pseudonym,
            last_sync_at=letzter_login,
            status="ok",
            changed=3,
            conflicts=1,
            shifts=0,
        )
    )
    await db.flush()


async def _zaehle(db, modell, pseudonym: str) -> int:
    return await db.scalar(
        select(func.count()).select_from(modell).where(modell.pseudonym == pseudonym)
    )


async def _cleanup(db):
    with patch("app.crons.cleanup_service.LiteLLMClient") as cls:
        inst = cls.return_value
        inst.delete_user = AsyncMock()
        inst.delete_key = AsyncMock()
        inst.close = AsyncMock()
        return await cleanup_inactive_accounts(db, now=NOW)


async def test_kuerzel_und_abrufstatus_gehen_mit_dem_konto(db):
    """Die Abnahme aus dem Plan: nach der Löschung ist keine Spur mehr da."""
    await _lehrkraft(db, "weg", letzter_login=LANGE_WEG)

    stats = await _cleanup(db)

    assert stats.deleted_local >= 1
    assert await _zaehle(db, PseudonymAudit, "weg") == 0
    assert await _zaehle(db, UserPreference, "weg") == 0
    assert await _zaehle(db, CalendarSyncStatus, "weg") == 0


async def test_aktive_lehrkraft_behaelt_kuerzel_und_status(db):
    """Gegenprobe — sonst würde ein zu weit gefasstes DELETE unbemerkt durchgehen."""
    await _lehrkraft(db, "aktiv", letzter_login=GESTERN)
    await _lehrkraft(db, "weg2", letzter_login=LANGE_WEG)

    await _cleanup(db)

    assert await _zaehle(db, UserPreference, "aktiv") == 1
    assert await _zaehle(db, CalendarSyncStatus, "aktiv") == 1
    assert await _zaehle(db, CalendarSyncStatus, "weg2") == 0


async def test_status_ohne_praeferenz_bleibt_nicht_zurueck(db):
    """Der Abrufstatus entsteht im Cron, die Präferenz beim Eintragen des Kürzels —
    beide unabhängig voneinander. Wer das Kürzel vor dem Weggang löscht, hinterlässt
    sonst eine verwaiste Statuszeile, die kein Aufräumlauf mehr findet."""
    db.add(PseudonymAudit(pseudonym="nur-status", role="teacher", last_login_at=LANGE_WEG))
    db.add(
        CalendarSyncStatus(
            pseudonym="nur-status",
            last_sync_at=LANGE_WEG,
            status="nicht_erreichbar",
            error="WebUntis nicht erreichbar (ConnectError)",
        )
    )
    await db.flush()

    await _cleanup(db)

    assert await _zaehle(db, CalendarSyncStatus, "nur-status") == 0
