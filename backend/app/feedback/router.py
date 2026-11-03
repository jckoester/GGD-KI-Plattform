"""Endpunkte des Feedback-Kanals für alle Rollen (ADR-020).

Der Gegenpart für die Sichtung liegt in `app/api/admin/feedback.py` (AP3). Getrennte
Router, weil die Antworten verschieden sind: Hier fehlen `issue_ref` und der Snapshot,
dort stehen sie.
"""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.audit import get_primary_role
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.core.hintergrund import im_hintergrund
from app.db.session import AsyncSessionLocal, get_db
from app.feedback import service
from app.feedback.benachrichtigung import benachrichtige
from app.feedback.schemas import BekanntesProblemOut, FeedbackCreate, FeedbackOut
from app.ratelimit.dependency import rate_limit

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", status_code=201)
async def create_feedback(
    daten: FeedbackCreate,
    current_user: JwtPayload = Depends(rate_limit("feedback")),
    db: AsyncSession = Depends(get_db),
) -> FeedbackOut:
    """Eine Meldung anlegen. 403 bei Spam-Sperre, 429 über dem Tageslimit.

    Die Rolle wird hier festgehalten, nicht später nachgeschlagen: Wer heute als
    Schüler:in meldet, hat es als Schüler:in getan — auch wenn das Konto später
    wechselt.
    """
    # Aus der Vorschau (0.29): die **echte** Rolle — es meldet eine Lehrkraft, keine
    # Schüler:in —, und das Merkmal `preview` (ADR-020).
    merkmal = current_user.preview
    eintrag = await service.erstelle(
        db,
        daten,
        pseudonym=current_user.sub,
        rolle=get_primary_role(merkmal.echte_rollen if merkmal else current_user.roles),
        aus_vorschau=merkmal is not None,
    )

    # Im Hintergrund: Ein Mailserver darf eine Rückmeldung nicht aufhalten. Ob
    # überhaupt versendet wird, entscheidet die Dämpfung in `benachrichtigung` (AP3).
    im_hintergrund(
        lambda: benachrichtige(AsyncSessionLocal),
        was="Feedback-Benachrichtigung",
    )
    return service.nach_aussen(eintrag)


# ⚠️ **Nur `POST` trägt die Drossel.** Der Eimer zählt je `(Bucket, Pseudonym)`, nicht
# je Endpunkt: An `GET /mine` gehängt, wäre man nach fünf Aufrufen aus der eigenen
# Meldungsliste ausgesperrt — und zwar mit derselben Meldung, die das Melden begrenzen
# soll. Lesen und Zurückziehen laufen deshalb wie überall über `get_current_user`.
@router.get("/mine")
async def my_feedback(
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FeedbackOut]:
    """Die eigenen Meldungen mit Status und Antwort — der Rückweg über das Pseudonym."""
    eintraege = await service.eigene(db, current_user.sub)
    return [service.nach_aussen(e) for e in eintraege]


@router.get("/public")
async def known_problems(
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BekanntesProblemOut]:
    """Bekannte Probleme (0.31): was die Sichtung öffentlich gemacht hat, für die eigene Rolle.

    Maßgeblich sind die Rollen **im Token** — in der Vorschau also die simulierte Schülersicht.
    """
    eintraege = await service.bekannte(db, lehrkraft="teacher" in current_user.roles)
    return [service.als_bekanntes_problem(e) for e in eintraege]


@router.delete("/{feedback_id}")
async def withdraw_feedback(
    feedback_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Eine eigene Meldung zurückziehen — nur solange sie offen ist."""
    await service.ziehe_zurueck(db, current_user.sub, feedback_id)
    return {"ok": True}
