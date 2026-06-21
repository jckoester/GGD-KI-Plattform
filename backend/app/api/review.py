"""Zweitfreigabe-Endpunkte für die Rolle `review` (Krisen-Einsicht Phase 12, Schritt 6).

Personen mit Rolle `review` (Schulsozialarbeit/Beratung) sehen offene Einsicht-Anträge
(pseudonymisiert, **ohne Chat-Inhalte**) und geben sie im Vier-Augen-Prinzip frei oder
lehnen ab. Freigabe/Ablehnung verlangen eine frische Authentifizierung (Step-up) und
schließen Selbst-Freigabe aus (Antragsteller ≠ Zweitperson).
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_any_role, require_fresh_stepup
from app.auth.jwt import JwtPayload
from app.db.models import Conversation, ConversationAccessRequest, ConversationFlag
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
