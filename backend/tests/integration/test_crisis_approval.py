"""Integrationstests für die Zweitfreigabe (Phase 12, Schritt 6).

Freigabe/Ablehnung-Logik, 4-Augen-Ausschluss, Zeitfenster und Flag-Status-Übergänge
gegen die Test-DB. Endpoint-Funktionen direkt aufgerufen (Rolle/Step-up im Unit-Test).
Erfordert TEST_DATABASE_URL.
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.api.review import (
    approve_access_request,
    deny_access_request,
    list_access_requests,
)
from app.auth.jwt import JwtPayload
from app.db.models import (
    Conversation,
    ConversationAccessRequest,
    ConversationFlag,
    Message,
)

REQUESTER = "admin-pseudo"
REVIEWER = JwtPayload(sub="review-pseudo", roles=["review"], grade=None, jti="j", iat=1, exp=9999999999)


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()
    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


@pytest_asyncio.fixture
async def pending_request(db):
    conv = Conversation(pseudonym="subject-pseudo", model_used="gpt-4o")
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
        status="under_review",
    )
    db.add(flag)
    await db.flush()
    req = ConversationAccessRequest(
        conversation_id=conv.id,
        flag_id=flag.id,
        requested_by=REQUESTER,
        reason="Zusatzkontext einer Lehrkraft.",
        access_window_hours=48,
        status="pending",
    )
    db.add(req)
    await db.flush()
    return conv, flag, req


async def test_approve_sets_coreviewer_and_window(db, pending_request):
    conv, flag, req = pending_request
    resp = await approve_access_request(
        request_id=req.id, db=db, current_user=REVIEWER, _fresh=REVIEWER
    )
    assert resp.status == "approved"
    assert resp.coreviewer == "review-pseudo"
    assert resp.access_granted_until is not None

    await db.refresh(req)
    assert req.coreviewer_approved_at is not None
    # Fenster ≈ now + 48h
    delta = req.access_granted_until - datetime.now(timezone.utc)
    assert 47 * 3600 < delta.total_seconds() < 49 * 3600


async def test_self_approval_forbidden(db, pending_request):
    conv, flag, req = pending_request
    requester_user = JwtPayload(
        sub=REQUESTER, roles=["admin", "review"], grade=None, jti="j", iat=1, exp=9999999999
    )
    with pytest.raises(HTTPException) as exc:
        await approve_access_request(
            request_id=req.id, db=db, current_user=requester_user, _fresh=requester_user
        )
    assert exc.value.status_code == 403


async def test_approve_non_pending_409(db, pending_request):
    conv, flag, req = pending_request
    req.status = "approved"
    await db.flush()
    with pytest.raises(HTTPException) as exc:
        await approve_access_request(
            request_id=req.id, db=db, current_user=REVIEWER, _fresh=REVIEWER
        )
    assert exc.value.status_code == 409


async def test_approve_unknown_404(db):
    with pytest.raises(HTTPException) as exc:
        await approve_access_request(
            request_id=uuid.uuid4(), db=db, current_user=REVIEWER, _fresh=REVIEWER
        )
    assert exc.value.status_code == 404


async def test_deny_marks_denied_and_resets_flag(db, pending_request):
    conv, flag, req = pending_request
    resp = await deny_access_request(
        request_id=req.id, db=db, current_user=REVIEWER, _fresh=REVIEWER
    )
    assert resp.status == "denied"
    await db.refresh(flag)
    assert flag.status == "open"  # zurück aus under_review


async def test_deny_non_pending_409(db, pending_request):
    conv, flag, req = pending_request
    req.status = "denied"
    await db.flush()
    with pytest.raises(HTTPException) as exc:
        await deny_access_request(
            request_id=req.id, db=db, current_user=REVIEWER, _fresh=REVIEWER
        )
    assert exc.value.status_code == 409


async def test_list_shows_pending_pseudonymous(db, pending_request):
    conv, flag, req = pending_request
    resp = await list_access_requests(status="pending", db=db, _=REVIEWER)
    found = [i for i in resp.items if i.id == req.id]
    assert found
    item = found[0]
    assert item.subject_pseudonym == "subject-pseudo"
    assert item.requested_by == REQUESTER
    assert item.flag_category == "suizidalitaet"
    assert item.access_window_hours == 48
    assert item.reason == "Zusatzkontext einer Lehrkraft."
