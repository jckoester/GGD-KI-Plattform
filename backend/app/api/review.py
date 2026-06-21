"""Zweitfreigabe-Endpunkte für die Rolle `review` (Krisen-Einsicht Phase 12, Schritt 6).

Personen mit Rolle `review` (Schulsozialarbeit/Beratung) sehen offene Einsicht-Anträge
(pseudonymisiert, **ohne Chat-Inhalte**) und geben sie im Vier-Augen-Prinzip frei oder
lehnen ab. Freigabe/Ablehnung verlangen eine frische Authentifizierung (Step-up) und
schließen Selbst-Freigabe aus (Antragsteller ≠ Zweitperson).
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_any_role, require_fresh_stepup
from app.auth.jwt import JwtPayload
from app.db.models import (
    Conversation,
    ConversationAccessAudit,
    ConversationAccessRequest,
    ConversationFlag,
    Message,
)
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/access-requests", tags=["access-requests"])


class AccessRequestItem(BaseModel):
    id: UUID
    conversation_id: UUID
    flag_id: UUID
    subject_pseudonym: str  # Pseudonym der betroffenen Konversation (Schüler:in)
    flag_category: str
    severity: str
    flagged_at: datetime
    requested_by: str  # Pseudonym der antragstellenden Person (i. d. R. Admin)
    requested_at: datetime
    reason: str | None  # optionaler Zusatzkontext
    access_window_hours: int
    status: str


class AccessRequestListResponse(BaseModel):
    items: list[AccessRequestItem]


class ApprovalResponse(BaseModel):
    id: UUID
    status: str
    coreviewer: str | None
    access_granted_until: datetime | None


@router.get("", response_model=AccessRequestListResponse)
async def list_access_requests(
    status: str = Query(default="pending"),
    db: AsyncSession = Depends(get_db),
    _: JwtPayload = Depends(require_any_role(["review"])),
) -> AccessRequestListResponse:
    stmt = (
        select(
            ConversationAccessRequest,
            ConversationFlag.flag_category,
            ConversationFlag.severity,
            ConversationFlag.flagged_at,
            Conversation.pseudonym,
        )
        .join(ConversationFlag, ConversationAccessRequest.flag_id == ConversationFlag.id)
        .join(Conversation, ConversationAccessRequest.conversation_id == Conversation.id)
        .where(ConversationAccessRequest.status == status)
        .order_by(ConversationAccessRequest.requested_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    items = [
        AccessRequestItem(
            id=req.id,
            conversation_id=req.conversation_id,
            flag_id=req.flag_id,
            subject_pseudonym=pseudonym,
            flag_category=category,
            severity=severity,
            flagged_at=flagged_at,
            requested_by=req.requested_by,
            requested_at=req.requested_at,
            reason=req.reason,
            access_window_hours=req.access_window_hours,
            status=req.status,
        )
        for req, category, severity, flagged_at, pseudonym in rows
    ]
    return AccessRequestListResponse(items=items)


@router.post("/{request_id}/approve", response_model=ApprovalResponse)
async def approve_access_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: JwtPayload = Depends(require_any_role(["review"])),
    _fresh: JwtPayload = Depends(require_fresh_stepup),
) -> ApprovalResponse:
    req = await db.get(ConversationAccessRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden.")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail="Antrag ist nicht offen.")
    # Vier-Augen-Prinzip: Zweitperson darf nicht der Antragsteller sein.
    if req.requested_by == current_user.sub:
        raise HTTPException(
            status_code=403, detail="Selbst-Freigabe ist nicht zulässig."
        )

    now = datetime.now(timezone.utc)
    req.coreviewer = current_user.sub
    req.coreviewer_approved_at = now
    req.status = "approved"
    req.access_granted_until = now + timedelta(hours=req.access_window_hours)
    await db.commit()
    await db.refresh(req)

    logger.info(
        "Krisen-Einsicht: Antrag freigegeben (request=%s, conv=%s, bis=%s)",
        req.id,
        req.conversation_id,
        req.access_granted_until,
    )
    return ApprovalResponse(
        id=req.id,
        status=req.status,
        coreviewer=req.coreviewer,
        access_granted_until=req.access_granted_until,
    )


@router.post("/{request_id}/deny", response_model=ApprovalResponse)
async def deny_access_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: JwtPayload = Depends(require_any_role(["review"])),
    _fresh: JwtPayload = Depends(require_fresh_stepup),
) -> ApprovalResponse:
    req = await db.get(ConversationAccessRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden.")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail="Antrag ist nicht offen.")

    req.status = "denied"
    # Flag aus dem Review zurück auf 'open' (wieder bearbeitbar/abschließbar).
    flag = await db.get(ConversationFlag, req.flag_id)
    if flag is not None and flag.status == "under_review":
        flag.status = "open"
    await db.commit()
    await db.refresh(req)

    logger.info("Krisen-Einsicht: Antrag abgelehnt (request=%s)", req.id)
    return ApprovalResponse(
        id=req.id,
        status=req.status,
        coreviewer=req.coreviewer,
        access_granted_until=req.access_granted_until,
    )


# ---------- Reader-View (read-only) + Audit (Schritt 7) ----------


class ReaderMessage(BaseModel):
    role: str  # 'user' | 'assistant'
    content: str
    created_at: datetime


class ReaderConversationResponse(BaseModel):
    request_id: UUID
    conversation_id: UUID
    subject_pseudonym: str
    flag_category: str
    severity: str
    access_granted_until: datetime
    messages: list[ReaderMessage]


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


async def _authorize_reader(
    request_id: UUID, current_user: JwtPayload, db: AsyncSession
) -> ConversationAccessRequest:
    """Prüft Beteiligung, Freigabe und Zeitfenster. Wirft 403/404/410."""
    req = await db.get(ConversationAccessRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden.")
    # Nur die beiden Beteiligten (Antragsteller UND Zweitperson) dürfen einsehen.
    if current_user.sub not in (req.requested_by, req.coreviewer):
        raise HTTPException(status_code=403, detail="Kein Zugriff auf diesen Antrag.")
    if req.status != "approved":
        raise HTTPException(status_code=403, detail="Einsicht ist nicht freigegeben.")
    now = datetime.now(timezone.utc)
    if req.access_granted_until is None or now >= req.access_granted_until:
        raise HTTPException(status_code=410, detail="Das Einsicht-Zeitfenster ist abgelaufen.")
    return req


async def _build_reader_payload(
    req: ConversationAccessRequest,
    current_user: JwtPayload,
    db: AsyncSession,
    request: Request,
    action: str,
) -> ReaderConversationResponse:
    from app.chat.router import _parse_stored_content  # lazy: vermeidet Import-Zyklus

    flag = await db.get(ConversationFlag, req.flag_id)
    conv = await db.get(Conversation, req.conversation_id)
    if conv is None or flag is None:
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden.")

    rows = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == req.conversation_id)
            .order_by(Message.created_at.asc())
        )
    ).scalars().all()

    messages: list[ReaderMessage] = []
    for m in rows:
        content = m.content
        if m.role == "user":
            content, _ = _parse_stored_content(m.content)  # Anhänge-Marker entfernen
        messages.append(
            ReaderMessage(role=m.role, content=content, created_at=m.created_at)
        )

    # Append-only-Audit: JEDER Zugriff wird protokolliert.
    db.add(
        ConversationAccessAudit(
            access_request_id=req.id,
            viewer=current_user.sub,
            action=action,
            ip_address=_client_ip(request),
        )
    )
    await db.commit()
    logger.info(
        "Krisen-Einsicht: %s (request=%s, conv=%s, viewer=%s)",
        action,
        req.id,
        req.conversation_id,
        current_user.sub,
    )

    return ReaderConversationResponse(
        request_id=req.id,
        conversation_id=conv.id,
        subject_pseudonym=conv.pseudonym,
        flag_category=flag.flag_category,
        severity=flag.severity,
        access_granted_until=req.access_granted_until,
        messages=messages,
    )


@router.get("/{request_id}/conversation", response_model=ReaderConversationResponse)
async def read_conversation(
    request_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: JwtPayload = Depends(require_fresh_stepup),
) -> ReaderConversationResponse:
    req = await _authorize_reader(request_id, current_user, db)
    return await _build_reader_payload(req, current_user, db, request, action="view")


@router.post("/{request_id}/export", response_model=ReaderConversationResponse)
async def export_conversation(
    request_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: JwtPayload = Depends(require_fresh_stepup),
) -> ReaderConversationResponse:
    # Gleiche Zugriffskontrolle; protokolliert action='export'. Den eigentlichen
    # Download baut das Frontend aus der Antwort.
    req = await _authorize_reader(request_id, current_user, db)
    return await _build_reader_payload(req, current_user, db, request, action="export")
