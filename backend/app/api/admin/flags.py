"""Admin-Flag-Dashboard (Krisen-Einsicht Phase 12, Schritt 3).

Listet erkannte Krisen-/Moderations-Flags **pseudonymisiert und ohne Chat-Inhalte**.
Inhalte werden erst nach vollständiger 4-Augen-Freigabe im Reader-View (Schritt 7)
sichtbar. Dieser Endpunkt zeigt nur Metadaten (Kategorie, Schweregrad, Zeitpunkt,
Status) und ob bereits ein aktiver Einsicht-Antrag läuft.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.db.models import Conversation, ConversationAccessRequest, ConversationFlag
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flags", tags=["admin-flags"])

# Ein Antrag gilt als "aktiv", solange er den Zugriff noch eröffnen kann.
_ACTIVE_REQUEST_STATUSES = ("pending", "approved")


class FlagItem(BaseModel):
    id: UUID
    conversation_id: UUID
    pseudonym: str  # pseudonym, keine reale Identität
    flag_source: str
    flag_category: str
    severity: str
    trigger_rule: str | None
    flagged_at: datetime
    status: str
    has_active_request: bool


class FlagListResponse(BaseModel):
    items: list[FlagItem]
    total: int
    limit: int
    offset: int


@router.get("", response_model=FlagListResponse)
async def list_flags(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: JwtPayload = Depends(require_role("admin")),
) -> FlagListResponse:
    where_conditions = []
    if status is not None:
        where_conditions.append(ConversationFlag.status == status)
    if severity is not None:
        where_conditions.append(ConversationFlag.severity == severity)

    total = await db.scalar(
        select(func.count()).select_from(ConversationFlag).where(*where_conditions)
    )

    # Korreliertes EXISTS: läuft für dieses Flag bereits ein offener/freigegebener Antrag?
    active_request = (
        select(ConversationAccessRequest.id)
        .where(
            ConversationAccessRequest.flag_id == ConversationFlag.id,
            ConversationAccessRequest.status.in_(_ACTIVE_REQUEST_STATUSES),
        )
        .exists()
    )

    stmt = (
        select(
            ConversationFlag,
            Conversation.pseudonym,
            active_request.label("has_active_request"),
        )
        .join(Conversation, ConversationFlag.conversation_id == Conversation.id)
        .where(*where_conditions)
        .order_by(ConversationFlag.flagged_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()

    items = [
        FlagItem(
            id=flag.id,
            conversation_id=flag.conversation_id,
            pseudonym=pseudonym,
            flag_source=flag.flag_source,
            flag_category=flag.flag_category,
            severity=flag.severity,
            trigger_rule=flag.trigger_rule,
            flagged_at=flag.flagged_at,
            status=flag.status,
            has_active_request=has_active_request,
        )
        for flag, pseudonym, has_active_request in rows
    ]
    return FlagListResponse(items=items, total=total or 0, limit=limit, offset=offset)


# ---------- Einsicht-Antrag (Schritt 4) ----------

# Flag-Status, in denen ein Einsicht-Antrag noch sinnvoll ist (nicht abgeschlossen).
_REQUESTABLE_FLAG_STATUSES = ("open", "under_review")


class AccessRequestCreate(BaseModel):
    reason: str = Field(min_length=50, max_length=2000)
    window_hours: int = Field(default=24, ge=1, le=168)

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 50:
            raise ValueError("Begründung muss mindestens 50 Zeichen enthalten.")
        return stripped


class AccessRequestResponse(BaseModel):
    id: UUID
    flag_id: UUID
    conversation_id: UUID
    status: str
    requested_at: datetime
    access_window_hours: int


@router.post(
    "/{flag_id}/access-requests",
    response_model=AccessRequestResponse,
    status_code=201,
)
async def create_access_request(
    flag_id: UUID,
    body: AccessRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: JwtPayload = Depends(require_role("admin")),
) -> AccessRequestResponse:
    flag = await db.get(ConversationFlag, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="Flag nicht gefunden.")
    if flag.status not in _REQUESTABLE_FLAG_STATUSES:
        raise HTTPException(
            status_code=409, detail="Dieses Flag ist bereits abgeschlossen."
        )

    # Doppelte Anträge verhindern: läuft schon ein offener/freigegebener Antrag?
    existing = await db.scalar(
        select(ConversationAccessRequest.id).where(
            ConversationAccessRequest.flag_id == flag_id,
            ConversationAccessRequest.status.in_(_ACTIVE_REQUEST_STATUSES),
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Für dieses Flag läuft bereits ein Einsicht-Antrag.",
        )

    req = ConversationAccessRequest(
        conversation_id=flag.conversation_id,
        flag_id=flag.id,
        requested_by=current_user.sub,
        reason=body.reason,
        access_window_hours=body.window_hours,
        status="pending",
    )
    db.add(req)
    flag.status = "under_review"
    await db.commit()
    await db.refresh(req)

    logger.info(
        "Krisen-Einsicht: Antrag angelegt (flag=%s, conv=%s, fenster=%sh)",
        flag.id,
        flag.conversation_id,
        req.access_window_hours,
    )
    return AccessRequestResponse(
        id=req.id,
        flag_id=req.flag_id,
        conversation_id=req.conversation_id,
        status=req.status,
        requested_at=req.requested_at,
        access_window_hours=req.access_window_hours,
    )
