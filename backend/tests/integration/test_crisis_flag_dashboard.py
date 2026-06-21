"""Integrationstest für das Admin-Flag-Dashboard (Phase 12, Schritt 3).

Prüft die echte Query (Pseudonym-Join, has_active_request via EXISTS, Status-/
Severity-Filter, Pagination) gegen die Test-DB. Die Endpoint-Funktion wird direkt
aufgerufen (require_role wird separat im Unit-Test geprüft). Erfordert TEST_DATABASE_URL.
"""

import pytest_asyncio

from app.api.admin.flags import list_flags
from app.auth.jwt import JwtPayload
from app.db.models import (
    Conversation,
    ConversationAccessRequest,
    ConversationFlag,
    Message,
)

ADMIN = JwtPayload(sub="p-admin", roles=["admin"], grade=None, jti="j", iat=1, exp=9999999999)
REASON = "Begründung mit ausreichender Länge für den Einsicht-Antrag (>= 50 Zeichen)."


async def _flag(db, *, pseudonym, category, severity, status="open"):
    conv = Conversation(pseudonym=pseudonym, model_used="gpt-4o")
    db.add(conv)
    await db.flush()
    msg = Message(conversation_id=conv.id, role="user", content="…")
    db.add(msg)
    await db.flush()
    flag = ConversationFlag(
        conversation_id=conv.id,
        message_id=msg.id,
        flag_source="auto_crisis",
        flag_category=category,
        severity=severity,
        status=status,
    )
    db.add(flag)
    await db.flush()
    return conv, flag


@pytest_asyncio.fixture
async def seeded(db_session):
    a_conv, a_flag = await _flag(
        db_session, pseudonym="dash-alpha", category="suizidalitaet", severity="alert"
    )
    b_conv, b_flag = await _flag(
        db_session, pseudonym="dash-beta", category="mobbing", severity="warning"
    )
    return {"a": (a_conv, a_flag), "b": (b_conv, b_flag)}


async def test_lists_flags_pseudonymous(db_session, seeded):
    resp = await list_flags(
        status=None, severity=None, limit=25, offset=0, db=db_session, _=ADMIN
    )
    pseudonyms = {i.pseudonym for i in resp.items}
    assert {"dash-alpha", "dash-beta"} <= pseudonyms
    assert resp.total >= 2
    # Standardmäßig kein aktiver Antrag
    for item in resp.items:
        assert item.has_active_request is False


async def test_has_active_request_reflects_pending(db_session, seeded):
    a_conv, a_flag = seeded["a"]
    req = ConversationAccessRequest(
        conversation_id=a_conv.id,
        flag_id=a_flag.id,
        requested_by="p-admin",
        reason=REASON,
        status="pending",
    )
    db_session.add(req)
    await db_session.flush()

    resp = await list_flags(
        status=None, severity=None, limit=25, offset=0, db=db_session, _=ADMIN
    )
    by_id = {i.id: i for i in resp.items}
    assert by_id[a_flag.id].has_active_request is True
    assert by_id[seeded["b"][1].id].has_active_request is False


async def test_denied_request_does_not_count_as_active(db_session, seeded):
    a_conv, a_flag = seeded["a"]
    req = ConversationAccessRequest(
        conversation_id=a_conv.id,
        flag_id=a_flag.id,
        requested_by="p-admin",
        reason=REASON,
        status="denied",
    )
    db_session.add(req)
    await db_session.flush()

    resp = await list_flags(
        status=None, severity=None, limit=25, offset=0, db=db_session, _=ADMIN
    )
    by_id = {i.id: i for i in resp.items}
    assert by_id[a_flag.id].has_active_request is False


async def test_severity_filter(db_session, seeded):
    resp = await list_flags(
        status=None, severity="alert", limit=25, offset=0, db=db_session, _=ADMIN
    )
    assert all(i.severity == "alert" for i in resp.items)
    assert any(i.pseudonym == "dash-alpha" for i in resp.items)
    assert all(i.pseudonym != "dash-beta" for i in resp.items)


async def test_status_filter(db_session, seeded):
    resp = await list_flags(
        status="resolved", severity=None, limit=25, offset=0, db=db_session, _=ADMIN
    )
    assert all(i.status == "resolved" for i in resp.items)


async def test_pagination_limits_items(db_session, seeded):
    resp = await list_flags(
        status=None, severity=None, limit=1, offset=0, db=db_session, _=ADMIN
    )
    assert len(resp.items) == 1
    assert resp.limit == 1
    assert resp.total >= 2
