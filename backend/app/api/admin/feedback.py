"""Sichtung der Rückmeldungen (ADR-020, AP3).

**Was die Sichtung sieht.** Pseudonym und Rolle — mehr Identität gibt es nicht, außer
die meldende Person hat freiwillig etwas ins Kontaktfeld geschrieben. Dieser Kontakt
ist **zweckgebunden**: Rückfragen zu dieser einen Meldung, nie Grundlage für Einsicht
in Chats. Ein angehängter Chat ist eine vom Opt-in gedeckte Kopie, **keine**
Einsichtnahme im Sinne von ADR-008 — und berechtigt auch zu keiner.

**Warum der Snapshot nicht in der Liste steht.** Er kann Hunderte Nachrichten tragen.
In einer Übersicht über fünfzig Meldungen wäre das ein Vielfaches an Chatinhalt, das
niemand angefordert hat — geladen wird er erst beim Aufklappen (`GET …/{id}`).
"""
import logging
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.db.models import Feedback
from app.db.session import get_db
from app.feedback import service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["admin-feedback"])

ALLE_STATI = (service.OFFEN, service.IN_ARBEIT, service.ERLEDIGT,
              service.ABGELEHNT, service.SPAM)

# Ohne Auswahl zeigt die Liste, was Arbeit macht — nicht das Archiv.
VORGABE_STATI = [service.OFFEN, service.IN_ARBEIT]


class FeedbackAdminOut(BaseModel):
    """Eine Meldung, wie die Sichtung sie sieht — ohne den Snapshot-Inhalt."""

    id: UUID
    pseudonym: Optional[str] = None  # Pseudonym, keine reale Identität
    role: str
    category: str
    content: str
    contact: Optional[str] = None
    app_version: str
    route: Optional[str] = None
    assistant_id: Optional[int] = None
    user_agent: Optional[str] = None
    viewport: Optional[str] = None
    status: str
    admin_reply: Optional[str] = None
    resolved_in_version: Optional[str] = None
    issue_ref: Optional[str] = None
    has_snapshot: bool
    created_at: datetime
    status_changed_at: Optional[datetime] = None


class FeedbackAdminDetail(FeedbackAdminOut):
    conversation_snapshot: Optional[dict] = None


class FeedbackListe(BaseModel):
    items: list[FeedbackAdminOut]
    total: int
    # Je Status, für die Zähler an den Filterknöpfen. Die übrigen Filter wirken mit,
    # der Status-Filter nicht — sonst zeigte der Knopf „Erledigt" immer die Zahl, die
    # gerade ausgewählt ist, und nie die, auf die man wechseln würde.
    counts: dict[str, int]


class FeedbackPatch(BaseModel):
    status: Optional[Literal["open", "in_progress", "done", "declined", "spam"]] = None
    admin_reply: Optional[str] = Field(None, max_length=2_000)
    resolved_in_version: Optional[str] = Field(None, max_length=50)
    issue_ref: Optional[str] = Field(None, max_length=200)
    keep_snapshot: bool = False


def _nach_aussen(eintrag: Feedback, *, mit_anhang: bool = False):
    felder = {
        "id": eintrag.id,
        "pseudonym": eintrag.pseudonym,
        "role": eintrag.role,
        "category": eintrag.category,
        "content": eintrag.content,
        "contact": eintrag.contact,
        "app_version": eintrag.app_version,
        "route": eintrag.route,
        "assistant_id": eintrag.assistant_id,
        "user_agent": eintrag.user_agent,
        "viewport": eintrag.viewport,
        "status": eintrag.status,
        "admin_reply": eintrag.admin_reply,
        "resolved_in_version": eintrag.resolved_in_version,
        "issue_ref": eintrag.issue_ref,
        "has_snapshot": eintrag.conversation_snapshot is not None,
        "created_at": eintrag.created_at,
        "status_changed_at": eintrag.status_changed_at,
    }
    if mit_anhang:
        return FeedbackAdminDetail(conversation_snapshot=eintrag.conversation_snapshot, **felder)
    return FeedbackAdminOut(**felder)


@router.get("")
async def list_feedback(
    status: Optional[list[str]] = Query(None),
    category: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    app_version: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> FeedbackListe:
    """Der Eingang, neueste zuerst. Ohne `status` nur Offenes und in Arbeit."""
    gewaehlt = status or VORGABE_STATI
    unbekannt = sorted(set(gewaehlt) - set(ALLE_STATI))
    if unbekannt:
        raise HTTPException(status_code=422, detail=f"Unbekannter Status: {unbekannt}")

    # Die Filter ohne den Status — sie gelten auch für die Zähler.
    rest = []
    if category:
        rest.append(Feedback.category == category)
    if role:
        rest.append(Feedback.role == role)
    if app_version:
        rest.append(Feedback.app_version == app_version)

    bedingungen = [Feedback.status.in_(gewaehlt), *rest]

    total = await db.scalar(
        select(func.count()).select_from(Feedback).where(*bedingungen)
    )
    ergebnis = await db.execute(
        select(Feedback)
        .where(*bedingungen)
        .order_by(Feedback.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    zaehler = await db.execute(
        select(Feedback.status, func.count()).where(*rest).group_by(Feedback.status)
    )
    counts = {s: 0 for s in ALLE_STATI}
    counts.update({s: int(n) for s, n in zaehler.all()})

    return FeedbackListe(
        items=[_nach_aussen(e) for e in ergebnis.scalars().all()],
        total=int(total or 0),
        counts=counts,
    )


@router.get("/{feedback_id}")
async def get_feedback(
    feedback_id: UUID,
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> FeedbackAdminDetail:
    """Eine Meldung mit allem, auch dem angehängten Chat."""
    eintrag = await db.scalar(select(Feedback).where(Feedback.id == feedback_id))
    if eintrag is None:
        raise HTTPException(status_code=404, detail="Meldung nicht gefunden")
    return _nach_aussen(eintrag, mit_anhang=True)


@router.patch("/{feedback_id}")
async def patch_feedback(
    feedback_id: UUID,
    aenderung: FeedbackPatch,
    current_user: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> FeedbackAdminDetail:
    """Status, Antwort, Version, Issue-Referenz.

    Die Regeln stehen in `app/feedback/service.py`, nicht hier: Sie gelten für die
    Meldung, nicht für diesen Endpunkt.
    """
    eintrag = await service.aendere(
        db,
        feedback_id,
        admin_pseudonym=current_user.sub,
        status=aenderung.status,
        admin_reply=aenderung.admin_reply,
        resolved_in_version=aenderung.resolved_in_version,
        issue_ref=aenderung.issue_ref,
        keep_snapshot=aenderung.keep_snapshot,
    )
    return _nach_aussen(eintrag, mit_anhang=True)
