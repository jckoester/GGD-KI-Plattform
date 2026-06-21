"""Integrationstest für das Stellen eines Einsicht-Antrags (Phase 12, Schritt 4).

Erfolgs-Pfad + Status-Übergang (Flag → under_review) + Konflikt-/Fehlerfälle gegen
die echte Test-DB. Endpoint-Funktion wird direkt aufgerufen (Authz im Unit-Test).
Erfordert TEST_DATABASE_URL.
"""

import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select

from app.api.admin.flags import AccessRequestCreate, create_access_request
from app.auth.jwt import JwtPayload
from app.db.models import Conversation, ConversationAccessRequest, ConversationFlag, Message

ADMIN = JwtPayload(sub="p-admin", roles=["admin"], grade=None, jti="j", iat=1, exp=9999999999)
REASON = (
    "Mehrere Nachrichten deuten auf eine akute Krise hin; Einsicht zur Einschätzung "
    "der Gefährdung und Einbindung der Schulsozialarbeit erforderlich."
)


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    """db_session mit commit()→flush(), damit der transaktionale Rollback greift."""
    async def _flush():
        await db_session.flush()
    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


@pytest_asyncio.fixture
async def open_flag(db):
    conv = Conversation(pseudonym="req-test-pseudo", model_used="gpt-4o")
    db.add(conv)
    await db.flush()
    msg = Message(conversation_id=conv.id, role="user", content="…")
    db.add(msg)
    await db.flush()
    flag = ConversationFlag(
        conversation_id=conv.id,
        message_id=msg.id,
        flag_source="auto_crisis",
        flag_category="suizidalitaet",
        severity="alert",
        status="open",
    )
    db.add(flag)
    await db.flush()
    return conv, flag


async def test_create_request_happy_path(db, open_flag):
    conv, flag = open_flag
    body = AccessRequestCreate(reason=REASON, window_hours=48)
    resp = await create_access_request(flag_id=flag.id, body=body, db=db, current_user=ADMIN)

    assert resp.status == "pending"
    assert resp.conversation_id == conv.id
    assert resp.access_window_hours == 48

    # Persistiert?
    row = await db.scalar(
        select(ConversationAccessRequest).where(ConversationAccessRequest.id == resp.id)
    )
    assert row is not None
    assert row.requested_by == "p-admin"
    assert row.reason == REASON

    # Flag-Status-Übergang
    await db.refresh(flag)
    assert flag.status == "under_review"


async def test_create_request_default_window(db, open_flag):
    conv, flag = open_flag
    resp = await create_access_request(
        flag_id=flag.id, body=AccessRequestCreate(reason=REASON), db=db, current_user=ADMIN
    )
    assert resp.access_window_hours == 24


async def test_create_request_duplicate_rejected(db, open_flag):
    conv, flag = open_flag
    await create_access_request(
        flag_id=flag.id, body=AccessRequestCreate(reason=REASON), db=db, current_user=ADMIN
    )
    with pytest.raises(HTTPException) as exc:
        await create_access_request(
            flag_id=flag.id, body=AccessRequestCreate(reason=REASON), db=db, current_user=ADMIN
        )
    assert exc.value.status_code == 409


async def test_create_request_unknown_flag_404(db):
    with pytest.raises(HTTPException) as exc:
        await create_access_request(
            flag_id=uuid.uuid4(), body=AccessRequestCreate(reason=REASON), db=db, current_user=ADMIN
        )
    assert exc.value.status_code == 404


async def test_create_request_on_resolved_flag_409(db, open_flag):
    conv, flag = open_flag
    flag.status = "resolved"
    await db.flush()
    with pytest.raises(HTTPException) as exc:
        await create_access_request(
            flag_id=flag.id, body=AccessRequestCreate(reason=REASON), db=db, current_user=ADMIN
        )
    assert exc.value.status_code == 409
