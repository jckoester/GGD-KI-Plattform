"""Integrationstests für die Krisen-Aufbewahrung im Cleanup-Cron (Phase 12, Schritt 8).

Verifiziert, dass der Cleanup geflaggte Konversationen schützt: offene/in-Prüfung-Flags
nie, resolved/dismissed bis 180 Tage nach resolved_at. Gegen die echte Test-DB mit
commit→flush-Patch. Erfordert TEST_DATABASE_URL.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from sqlalchemy import func, select

from app.crons.cleanup_service import (
    cleanup_inactive_accounts,
    cleanup_stale_conversations,
)
from app.db.models import (
    Conversation,
    ConversationFlag,
    Message,
    PseudonymAudit,
)

NOW = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
OLD = NOW - timedelta(days=200)  # älter als 93/90 Tage → Löschkandidat


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()
    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


async def _conv(db, pseudonym, *, flag_status=None, resolved_at=None):
    conv = Conversation(
        pseudonym=pseudonym, model_used="gpt-4o", last_message_at=OLD
    )
    db.add(conv)
    await db.flush()
    db.add(Message(conversation_id=conv.id, role="user", content="…"))
    if flag_status is not None:
        db.add(
            ConversationFlag(
                conversation_id=conv.id,
                flag_source="auto_crisis",
                flag_category="suizidalitaet",
                severity="alert",
                status=flag_status,
                resolved_at=resolved_at,
            )
        )
    await db.flush()
    return conv


async def test_stale_cleanup_protects_flagged(db):
    a = await _conv(db, "pa")  # kein Flag → löschbar
    b = await _conv(db, "pb", flag_status="open")  # offen → geschützt
    c = await _conv(db, "pc", flag_status="resolved", resolved_at=NOW - timedelta(days=10))  # frisch resolved → geschützt
    d = await _conv(db, "pd", flag_status="resolved", resolved_at=NOW - timedelta(days=200))  # Aufbewahrung abgelaufen → löschbar

    await cleanup_stale_conversations(db, now=NOW)

    remaining = set(
        (await db.execute(select(Conversation.id).where(
            Conversation.id.in_([a.id, b.id, c.id, d.id])
        ))).scalars().all()
    )
    assert a.id not in remaining  # gelöscht
    assert b.id in remaining      # geschützt (offen)
    assert c.id in remaining      # geschützt (innerhalb 180 Tage)
    assert d.id not in remaining  # gelöscht (Aufbewahrung vorbei)


async def test_stale_cleanup_dry_run_excludes_protected(db):
    await _conv(db, "pa")  # löschbar
    await _conv(db, "pb", flag_status="under_review")  # geschützt
    stats = await cleanup_stale_conversations(db, now=NOW, dry_run=True)
    # Nur die ungeschützte zählt (keine anderen Konversationen im rollback-Scope)
    assert stats.found == 1


async def test_account_cleanup_skips_protected(db):
    db.add(PseudonymAudit(pseudonym="prot", role="student", last_login_at=OLD))
    db.add(PseudonymAudit(pseudonym="norm", role="student", last_login_at=OLD))
    await db.flush()
    await _conv(db, "prot", flag_status="open")  # schützt den Account
    await _conv(db, "norm")  # ungeschützt

    with patch("app.crons.cleanup_service.LiteLLMClient") as cls:
        inst = cls.return_value
        inst.delete_user = AsyncMock()
        inst.delete_key = AsyncMock()
        inst.close = AsyncMock()
        stats = await cleanup_inactive_accounts(db, now=NOW)

    prot = await db.scalar(
        select(func.count()).select_from(PseudonymAudit).where(PseudonymAudit.pseudonym == "prot")
    )
    norm = await db.scalar(
        select(func.count()).select_from(PseudonymAudit).where(PseudonymAudit.pseudonym == "norm")
    )
    assert prot == 1  # geschützt, nicht gelöscht
    assert norm == 0  # gelöscht
    assert stats.skipped_protected >= 1
