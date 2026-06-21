"""Integrationstests für das Krisen-Einsicht-Datenmodell (Phase 12, Schritt 2).

conversation_access_requests + conversation_access_audit: Insert/Query,
Server-Defaults, CHECK-Constraints (Status, Action, 4-Augen-Ausschluss) und
FK-Cascade. Erfordert TEST_DATABASE_URL.
"""

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    Conversation,
    ConversationAccessAudit,
    ConversationAccessRequest,
    ConversationFlag,
    Message,
)

REQUESTER = "admin-pseudo"
REVIEWER = "review-pseudo"
REASON = "Begründung mit ausreichender Länge für den Einsicht-Antrag (>= 50 Zeichen)."


@pytest_asyncio.fixture
async def conv_flag(db_session):
    """Eine Konversation mit auslösender Nachricht und einem Krisen-Flag."""
    conv = Conversation(pseudonym="access-test-pseudo", model_used="gpt-4o")
    db_session.add(conv)
    await db_session.flush()
    msg = Message(conversation_id=conv.id, role="user", content="…")
    db_session.add(msg)
    await db_session.flush()
    flag = ConversationFlag(
        conversation_id=conv.id,
        message_id=msg.id,
        flag_source="auto_crisis",
        flag_category="suizidalitaet",
        severity="alert",
        coreviewer_role="review",
    )
    db_session.add(flag)
    await db_session.flush()
    return conv, flag


async def test_insert_and_query_access_request(db_session, conv_flag):
    conv, flag = conv_flag
    req = ConversationAccessRequest(
        conversation_id=conv.id,
        flag_id=flag.id,
        requested_by=REQUESTER,
        reason=REASON,
    )
    db_session.add(req)
    await db_session.flush()
    await db_session.refresh(req)

    # Server-Defaults
    assert req.status == "pending"
    assert req.required_coreviewer_role == "review"
    assert req.requested_at is not None
    assert req.coreviewer is None
    assert req.access_granted_until is None

    row = await db_session.scalar(
        select(ConversationAccessRequest).where(
            ConversationAccessRequest.conversation_id == conv.id
        )
    )
    assert row is not None
    assert row.requested_by == REQUESTER
    assert row.flag_id == flag.id


async def test_insert_and_query_audit(db_session, conv_flag):
    conv, flag = conv_flag
    req = ConversationAccessRequest(
        conversation_id=conv.id, flag_id=flag.id, requested_by=REQUESTER, reason=REASON
    )
    db_session.add(req)
    await db_session.flush()

    audit = ConversationAccessAudit(
        access_request_id=req.id, viewer=REQUESTER, action="view", ip_address="127.0.0.1"
    )
    db_session.add(audit)
    await db_session.flush()
    await db_session.refresh(audit)

    assert audit.viewed_at is not None  # server_default now()

    count = await db_session.scalar(
        select(func.count())
        .select_from(ConversationAccessAudit)
        .where(ConversationAccessAudit.access_request_id == req.id)
    )
    assert count == 1


async def test_invalid_status_rejected(db_session, conv_flag):
    conv, flag = conv_flag
    with pytest.raises(IntegrityError):
        req = ConversationAccessRequest(
            conversation_id=conv.id,
            flag_id=flag.id,
            requested_by=REQUESTER,
            reason=REASON,
            status="bogus",
        )
        db_session.add(req)
        await db_session.flush()


async def test_invalid_audit_action_rejected(db_session, conv_flag):
    conv, flag = conv_flag
    req = ConversationAccessRequest(
        conversation_id=conv.id, flag_id=flag.id, requested_by=REQUESTER, reason=REASON
    )
    db_session.add(req)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        audit = ConversationAccessAudit(
            access_request_id=req.id, viewer=REQUESTER, action="screenshot"
        )
        db_session.add(audit)
        await db_session.flush()


async def test_coreviewer_equal_requester_rejected(db_session, conv_flag):
    """4-Augen-Prinzip auf DB-Ebene: Zweitperson darf nicht der Antragsteller sein."""
    conv, flag = conv_flag
    with pytest.raises(IntegrityError):
        req = ConversationAccessRequest(
            conversation_id=conv.id,
            flag_id=flag.id,
            requested_by=REQUESTER,
            reason=REASON,
            coreviewer=REQUESTER,
        )
        db_session.add(req)
        await db_session.flush()


async def test_coreviewer_distinct_allowed(db_session, conv_flag):
    conv, flag = conv_flag
    req = ConversationAccessRequest(
        conversation_id=conv.id,
        flag_id=flag.id,
        requested_by=REQUESTER,
        reason=REASON,
        coreviewer=REVIEWER,
    )
    db_session.add(req)
    await db_session.flush()
    await db_session.refresh(req)
    assert req.coreviewer == REVIEWER


async def test_deleting_conversation_cascades(db_session, conv_flag):
    """Konversation löschen entfernt Antrag und (mehrstufig) das Audit-Protokoll."""
    conv, flag = conv_flag
    req = ConversationAccessRequest(
        conversation_id=conv.id, flag_id=flag.id, requested_by=REQUESTER, reason=REASON
    )
    db_session.add(req)
    await db_session.flush()
    audit = ConversationAccessAudit(
        access_request_id=req.id, viewer=REQUESTER, action="view"
    )
    db_session.add(audit)
    await db_session.flush()

    await db_session.delete(conv)
    await db_session.flush()

    req_count = await db_session.scalar(
        select(func.count())
        .select_from(ConversationAccessRequest)
        .where(ConversationAccessRequest.id == req.id)
    )
    audit_count = await db_session.scalar(
        select(func.count())
        .select_from(ConversationAccessAudit)
        .where(ConversationAccessAudit.id == audit.id)
    )
    assert req_count == 0
    assert audit_count == 0


async def test_deleting_flag_cascades_to_request(db_session, conv_flag):
    conv, flag = conv_flag
    req = ConversationAccessRequest(
        conversation_id=conv.id, flag_id=flag.id, requested_by=REQUESTER, reason=REASON
    )
    db_session.add(req)
    await db_session.flush()

    await db_session.delete(flag)
    await db_session.flush()

    count = await db_session.scalar(
        select(func.count())
        .select_from(ConversationAccessRequest)
        .where(ConversationAccessRequest.id == req.id)
    )
    assert count == 0
