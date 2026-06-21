"""Integrationstests für den Soft-Delete geflaggter Konversationen (Schritt 7, ADR-008 Teil 7).

Ruft die Endpoint-Funktionen direkt auf (commit→flush-Patch für den Fixture-Rollback).
Erfordert TEST_DATABASE_URL.
"""

import pytest_asyncio
from sqlalchemy import func, select

from app.auth.jwt import JwtPayload
from app.chat.router import delete_conversation, list_conversations
from app.db.models import Conversation, ConversationFlag


def _payload(pseudonym: str) -> JwtPayload:
    return JwtPayload(sub=pseudonym, roles=["student"], grade="8", jti="t", iat=0, exp=9_999_999_999)


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    """db_session mit commit()→flush(), damit der transaktionale Rollback greift."""
    async def _flush():
        await db_session.flush()
    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


async def _make_conv(db, pseudonym, *, flagged=False, flag_status="open") -> Conversation:
    conv = Conversation(pseudonym=pseudonym, model_used="gpt-4o")
    db.add(conv)
    await db.flush()
    if flagged:
        db.add(ConversationFlag(
            conversation_id=conv.id,
            flag_source="auto_crisis",
            flag_category="suizidalitaet",
            severity="alert",
            status=flag_status,
        ))
        await db.flush()
    return conv


async def _count_conv(db, conv_id) -> int:
    return await db.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.id == conv_id)
    )


async def test_unflagged_conversation_is_hard_deleted(db):
    conv = await _make_conv(db, "p", flagged=False)
    await delete_conversation(conversation_id=conv.id, current_user=_payload("p"), db=db)
    assert await _count_conv(db, conv.id) == 0


async def test_flagged_conversation_is_soft_deleted(db):
    conv = await _make_conv(db, "p", flagged=True, flag_status="open")
    await delete_conversation(conversation_id=conv.id, current_user=_payload("p"), db=db)

    row = await db.scalar(select(Conversation).where(Conversation.id == conv.id))
    assert row is not None  # nicht hart gelöscht
    assert row.hidden_by_user is True
    # Das Flag überlebt (wäre sonst per Cascade weg)
    flag_count = await db.scalar(
        select(func.count()).select_from(ConversationFlag).where(
            ConversationFlag.conversation_id == conv.id
        )
    )
    assert flag_count == 1


async def test_dismissed_flag_allows_hard_delete(db):
    conv = await _make_conv(db, "p", flagged=True, flag_status="dismissed")
    await delete_conversation(conversation_id=conv.id, current_user=_payload("p"), db=db)
    assert await _count_conv(db, conv.id) == 0


async def test_hidden_conversation_excluded_from_list(db):
    visible = await _make_conv(db, "lister", flagged=False)
    hidden = await _make_conv(db, "lister", flagged=True, flag_status="open")
    await delete_conversation(conversation_id=hidden.id, current_user=_payload("lister"), db=db)

    resp = await list_conversations(
        limit=10,
        offset=0,
        include_test=False,
        subject_id=None,
        group_id=None,
        exclude_groups=False,
        current_user=_payload("lister"),
        db=db,
    )
    ids = {item.id for item in resp.items}
    assert visible.id in ids
    assert hidden.id not in ids
    assert resp.total == 1
