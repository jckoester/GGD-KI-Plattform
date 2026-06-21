"""Integrationstests für das conversation_flags-Datenmodell (Schritt 3).

Insert/Query, Server-Defaults und FK-Cascade. Erfordert TEST_DATABASE_URL.
"""

import pytest_asyncio
from sqlalchemy import func, select

from app.db.models import Conversation, ConversationFlag, Message


@pytest_asyncio.fixture
async def conv_with_message(db_session):
    """Eine Konversation mit einer (auslösenden) User-Nachricht."""
    conv = Conversation(pseudonym="crisis-test-pseudo", model_used="gpt-4o")
    db_session.add(conv)
    await db_session.flush()
    msg = Message(conversation_id=conv.id, role="user", content="…")
    db_session.add(msg)
    await db_session.flush()
    return conv, msg


async def test_insert_and_query_flag(db_session, conv_with_message):
    conv, msg = conv_with_message
    flag = ConversationFlag(
        conversation_id=conv.id,
        message_id=msg.id,
        flag_source="auto_crisis",
        flag_category="suizidalitaet",
        severity="alert",
        trigger_rule="crisis_triggers:suizidalitaet",
        coreviewer_role="review",
    )
    db_session.add(flag)
    await db_session.flush()
    await db_session.refresh(flag)

    assert flag.status == "open"  # server_default
    assert flag.flagged_at is not None  # server_default now()

    row = await db_session.scalar(
        select(ConversationFlag).where(ConversationFlag.conversation_id == conv.id)
    )
    assert row is not None
    assert row.message_id == msg.id
    assert row.flag_category == "suizidalitaet"


async def test_hidden_by_user_defaults_false(db_session):
    conv = Conversation(pseudonym="crisis-test-pseudo", model_used="gpt-4o")
    db_session.add(conv)
    await db_session.flush()
    await db_session.refresh(conv)
    assert conv.hidden_by_user is False


async def test_deleting_conversation_cascades_to_flag(db_session, conv_with_message):
    conv, msg = conv_with_message
    flag = ConversationFlag(
        conversation_id=conv.id,
        message_id=msg.id,
        flag_source="auto_crisis",
        flag_category="mobbing",
        severity="warning",
    )
    db_session.add(flag)
    await db_session.flush()

    await db_session.delete(conv)
    await db_session.flush()

    count = await db_session.scalar(
        select(func.count())
        .select_from(ConversationFlag)
        .where(ConversationFlag.conversation_id == conv.id)
    )
    assert count == 0


async def test_deleting_message_cascades_to_flag(db_session, conv_with_message):
    conv, msg = conv_with_message
    flag = ConversationFlag(
        conversation_id=conv.id,
        message_id=msg.id,
        flag_source="auto_crisis",
        flag_category="selbstverletzung",
        severity="alert",
    )
    db_session.add(flag)
    await db_session.flush()

    await db_session.delete(msg)
    await db_session.flush()

    count = await db_session.scalar(
        select(func.count())
        .select_from(ConversationFlag)
        .where(ConversationFlag.id == flag.id)
    )
    assert count == 0
