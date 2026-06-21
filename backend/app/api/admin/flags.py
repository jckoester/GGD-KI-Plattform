"""Admin-Flag-Dashboard (Krisen-Einsicht Phase 12, Schritt 3).

Listet erkannte Krisen-/Moderations-Flags **pseudonymisiert und ohne Chat-Inhalte**.
Inhalte werden erst nach vollständiger 4-Augen-Freigabe im Reader-View (Schritt 7)
sichtbar. Dieser Endpunkt zeigt nur Metadaten (Kategorie, Schweregrad, Zeitpunkt,
Status) und ob bereits ein aktiver Einsicht-Antrag läuft.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.db.models import Conversation, ConversationAccessRequest, ConversationFlag
from app.db.session import get_db

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
