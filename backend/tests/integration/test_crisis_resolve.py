"""Integrationstests für die Resolution (Phase 12, Schritt 8).

Resolution setzt Flag-Status + resolved_at + Resolutions-Notiz und schließt den Antrag.
Endpoint-Funktion direkt aufgerufen (Rolle im Unit-Test). Erfordert TEST_DATABASE_URL.
"""

import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.api.review import ResolveRequest, resolve_access_request
from app.auth.jwt import JwtPayload
from app.db.models import (
    Conversation,
    ConversationAccessRequest,
    ConversationFlag,
    Message,
)

ADMIN = JwtPayload(sub="admin-pseudo", roles=["teacher", "admin"], grade=None, jti="j", iat=1, exp=9999999999)
NOTE = "Mit Schulsozialarbeit besprochen; Schüler:in ist in Betreuung."


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()
    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


async def _request(db, *, req_status="approved"):
    conv = Conversation(pseudonym="subject-pseudo", model_used="gpt-4o")
    db.add(conv)
    await db.flush()
    db.add(Message(conversation_id=conv.id, role="user", content="…"))
    flag = ConversationFlag(
        conversation_id=conv.id,
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
        requested_by="admin-pseudo",
        access_window_hours=48,
        status=req_status,
    )
    db.add(req)
    await db.flush()
    return conv, flag, req


async def test_resolve_marks_flag_resolved(db):
    conv, flag, req = await _request(db)
    resp = await resolve_access_request(
        request_id=req.id,
        body=ResolveRequest(outcome="resolved", note=NOTE),
        db=db,
        _=ADMIN,
    )
    assert resp.request_status == "expired"
    assert resp.flag_status == "resolved"

    await db.refresh(req)
    await db.refresh(flag)
    assert req.resolution_note == NOTE
    assert req.status == "expired"
    assert flag.status == "resolved"
    assert flag.resolved_at is not None


async def test_resolve_dismissed(db):
    conv, flag, req = await _request(db)
    resp = await resolve_access_request(
        request_id=req.id,
        body=ResolveRequest(outcome="dismissed", note="Fehlalarm."),
        db=db,
        _=ADMIN,
    )
    assert resp.flag_status == "dismissed"
    await db.refresh(flag)
    assert flag.status == "dismissed"
    assert flag.resolved_at is not None


async def test_resolve_pending_request_allowed(db):
    # Admin schließt direkt (Fehlalarm) ohne Einsicht
    conv, flag, req = await _request(db, req_status="pending")
    resp = await resolve_access_request(
        request_id=req.id,
        body=ResolveRequest(outcome="dismissed", note="Kein Anlass."),
        db=db,
        _=ADMIN,
    )
    assert resp.request_status == "expired"
    assert resp.flag_status == "dismissed"


async def test_resolve_already_closed_409(db):
    conv, flag, req = await _request(db, req_status="expired")
    with pytest.raises(HTTPException) as exc:
        await resolve_access_request(
            request_id=req.id,
            body=ResolveRequest(outcome="resolved", note=NOTE),
            db=db,
            _=ADMIN,
        )
    assert exc.value.status_code == 409


async def test_resolve_unknown_404(db):
    with pytest.raises(HTTPException) as exc:
        await resolve_access_request(
            request_id=uuid.uuid4(),
            body=ResolveRequest(outcome="resolved", note=NOTE),
            db=db,
            _=ADMIN,
        )
    assert exc.value.status_code == 404


def test_resolve_blank_note_rejected():
    with pytest.raises(ValueError):
        ResolveRequest(outcome="resolved", note="   ")
