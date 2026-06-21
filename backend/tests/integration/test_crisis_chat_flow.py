"""Integrationstests für die Krisen-Erkennung im Chat-Flow (Schritt 4).

Testet `_record_crisis` direkt (ohne LiteLLM-Mock): Flag-Anlage, message_id,
Banner-Entscheidung „einmal pro Kategorie/Konversation". Erfordert TEST_DATABASE_URL.
"""

import pytest_asyncio
from sqlalchemy import func, select

from app.chat.router import _CrisisRecord, _record_crisis
from app.db.models import Conversation, ConversationFlag, Message


@pytest_asyncio.fixture
async def _commit_as_flush(db_session, monkeypatch):
    """Ersetzt db.commit() durch flush(), damit der Fixture-Rollback greift."""
    async def _flush():
        await db_session.flush()
    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


async def _new_conversation(db_session) -> Conversation:
    conv = Conversation(pseudonym="crisis-flow-pseudo", model_used="gpt-4o")
    db_session.add(conv)
    await db_session.flush()
    return conv


async def test_record_crisis_creates_flag_and_message(_commit_as_flush):
    db = _commit_as_flush
    conv = await _new_conversation(db)

    rec = await _record_crisis(db, conv.id, "Ich will mich umbringen.", [], "crisis-flow-pseudo")

    assert isinstance(rec, _CrisisRecord)
    assert rec.hit.category == "suizidalitaet"
    assert rec.show_banner is True

    flag = await db.scalar(
        select(ConversationFlag).where(ConversationFlag.conversation_id == conv.id)
    )
    assert flag is not None
    assert flag.flag_source == "auto_crisis"
    assert flag.severity == "alert"
    assert flag.message_id is not None

    # Die früh persistierte User-Nachricht existiert und hängt am Flag
    msg = await db.scalar(select(Message).where(Message.id == flag.message_id))
    assert msg is not None
    assert msg.role == "user"


async def test_record_crisis_benign_returns_none(db_session):
    conv = await _new_conversation(db_session)

    rec = await _record_crisis(
        db_session, conv.id, "Wie löse ich diese quadratische Gleichung?", [], "crisis-flow-pseudo"
    )

    assert rec is None
    count = await db_session.scalar(
        select(func.count())
        .select_from(ConversationFlag)
        .where(ConversationFlag.conversation_id == conv.id)
    )
    assert count == 0
    # Ohne Treffer wird auch keine User-Nachricht früh geschrieben
    msg_count = await db_session.scalar(
        select(func.count()).select_from(Message).where(Message.conversation_id == conv.id)
    )
    assert msg_count == 0


async def test_banner_only_once_per_category(_commit_as_flush):
    db = _commit_as_flush
    conv = await _new_conversation(db)

    r1 = await _record_crisis(db, conv.id, "Ich will mich umbringen.", [], "p")
    r2 = await _record_crisis(db, conv.id, "Ich will mich umbringen.", [], "p")

    assert r1.show_banner is True
    assert r2.show_banner is False  # gleiche Kategorie bereits geflaggt

    # Geflaggt wird trotzdem jeder Treffer
    count = await db.scalar(
        select(func.count())
        .select_from(ConversationFlag)
        .where(ConversationFlag.conversation_id == conv.id)
    )
    assert count == 2


async def test_banner_shown_for_distinct_category(_commit_as_flush):
    db = _commit_as_flush
    conv = await _new_conversation(db)

    r1 = await _record_crisis(db, conv.id, "Ich will mich umbringen.", [], "p")  # suizidalitaet
    r2 = await _record_crisis(db, conv.id, "Niemand mag mich in der Klasse.", [], "p")  # mobbing

    assert r1.show_banner is True
    assert r2.show_banner is True  # andere Kategorie → eigenes Banner
