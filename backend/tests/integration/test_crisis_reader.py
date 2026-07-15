"""Integrationstests für den Reader-View + Audit (Phase 12, Schritt 7).

Zugriffskontrolle (Beteiligte/Status/Zeitfenster) und Audit-Protokollierung gegen die
Test-DB. Endpoint-Funktionen direkt aufgerufen (Step-up im Unit-Test). require_fresh_stepup
wird beim Direktaufruf umgangen. Erfordert TEST_DATABASE_URL.
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select

from app.api.review import (
    export_conversation,
    read_conversation,
)
from app.auth.jwt import JwtPayload
from app.db.models import (
    Conversation,
    ConversationAccessAudit,
    ConversationAccessRequest,
    ConversationFlag,
    Message,
)

REQUESTER = "admin-pseudo"
REVIEWER = "review-pseudo"


def _user(sub):
    return JwtPayload(sub=sub, roles=["review"], grade=None, jti="j", iat=1, exp=9999999999)


def _req(ip="10.0.0.5", fwd=None):
    headers = {"x-forwarded-for": fwd} if fwd else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=ip))


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()
    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


async def _make_request(db, *, status="approved", granted_delta=timedelta(hours=1)):
    conv = Conversation(pseudonym="subject-pseudo", model_used="gpt-4o")
    db.add(conv)
    await db.flush()
    db.add(Message(conversation_id=conv.id, role="user", content="Mir geht es schlecht."))
    db.add(Message(conversation_id=conv.id, role="assistant", content="Das tut mir leid."))
    flag = ConversationFlag(
        conversation_id=conv.id,
        flag_source="auto_crisis",
        flag_category="suizidalitaet",
        severity="alert",
        status="under_review",
    )
    db.add(flag)
    await db.flush()
    now = datetime.now(timezone.utc)
    req = ConversationAccessRequest(
        conversation_id=conv.id,
        flag_id=flag.id,
        requested_by=REQUESTER,
        coreviewer=REVIEWER if status == "approved" else None,
        access_window_hours=48,
        status=status,
        access_granted_until=(now + granted_delta) if status == "approved" else None,
    )
    db.add(req)
    await db.flush()
    return conv, flag, req


async def _audit_count(db, req_id, action=None):
    stmt = select(func.count()).select_from(ConversationAccessAudit).where(
        ConversationAccessAudit.access_request_id == req_id
    )
    if action:
        stmt = stmt.where(ConversationAccessAudit.action == action)
    return await db.scalar(stmt)


async def test_requester_can_read(db):
    conv, flag, req = await _make_request(db)
    resp = await read_conversation(
        request_id=req.id, request=_req(), db=db, current_user=_user(REQUESTER)
    )
    assert resp.conversation_id == conv.id
    assert resp.subject_pseudonym == "subject-pseudo"
    assert [m.role for m in resp.messages] == ["user", "assistant"]
    assert resp.messages[0].content == "Mir geht es schlecht."


async def test_coreviewer_can_read(db):
    conv, flag, req = await _make_request(db)
    resp = await read_conversation(
        request_id=req.id, request=_req(), db=db, current_user=_user(REVIEWER)
    )
    assert len(resp.messages) == 2


async def _audit_ip(db, req_id):
    row = await db.scalar(
        select(ConversationAccessAudit).where(
            ConversationAccessAudit.access_request_id == req_id
        )
    )
    return row


async def test_read_writes_view_audit_with_ip_trusted_proxy(db):
    # Peer ist ein vertrauenswürdiger Proxy (127.0.0.1) → X-Forwarded-For wird ausgewertet;
    # genommen wird der rechteste NICHT-Proxy-Eintrag (echter Client, den nginx anhängt),
    # nicht der spoofbare linke Eintrag (Sicherheits-Audit #13).
    conv, flag, req = await _make_request(db)
    await read_conversation(
        request_id=req.id,
        request=_req(ip="127.0.0.1", fwd="203.0.113.7, 10.0.0.1"),
        db=db,
        current_user=_user(REVIEWER),
    )
    assert await _audit_count(db, req.id, "view") == 1
    row = await _audit_ip(db, req.id)
    assert row.viewer == REVIEWER
    assert row.ip_address == "10.0.0.1"  # rechtester Nicht-Proxy-Eintrag


async def test_read_audit_ignores_xff_from_untrusted_peer(db):
    # Peer ist KEIN vertrauenswürdiger Proxy → X-Forwarded-For ist spoofbar und wird ignoriert;
    # geloggt wird der tatsächliche TCP-Peer (Anti-Spoofing, Sicherheits-Audit #13).
    conv, flag, req = await _make_request(db)
    await read_conversation(
        request_id=req.id,
        request=_req(ip="10.0.0.5", fwd="203.0.113.7"),
        db=db,
        current_user=_user(REVIEWER),
    )
    row = await _audit_ip(db, req.id)
    assert row.ip_address == "10.0.0.5"


async def test_non_participant_forbidden(db):
    conv, flag, req = await _make_request(db)
    with pytest.raises(HTTPException) as exc:
        await read_conversation(
            request_id=req.id, request=_req(), db=db, current_user=_user("fremd-pseudo")
        )
    assert exc.value.status_code == 403
    assert await _audit_count(db, req.id) == 0  # kein Audit bei verweigertem Zugriff


async def test_not_approved_forbidden(db):
    conv, flag, req = await _make_request(db, status="pending")
    with pytest.raises(HTTPException) as exc:
        await read_conversation(
            request_id=req.id, request=_req(), db=db, current_user=_user(REQUESTER)
        )
    assert exc.value.status_code == 403


async def test_expired_window_gone(db):
    conv, flag, req = await _make_request(db, granted_delta=timedelta(hours=-1))
    with pytest.raises(HTTPException) as exc:
        await read_conversation(
            request_id=req.id, request=_req(), db=db, current_user=_user(REVIEWER)
        )
    assert exc.value.status_code == 410


async def test_unknown_request_404(db):
    with pytest.raises(HTTPException) as exc:
        await read_conversation(
            request_id=uuid.uuid4(), request=_req(), db=db, current_user=_user(REVIEWER)
        )
    assert exc.value.status_code == 404


async def test_export_writes_export_audit(db):
    conv, flag, req = await _make_request(db)
    resp = await export_conversation(
        request_id=req.id, request=_req(), db=db, current_user=_user(REQUESTER)
    )
    assert len(resp.messages) == 2
    assert await _audit_count(db, req.id, "export") == 1
