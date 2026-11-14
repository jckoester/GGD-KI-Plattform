"""Einrichtung beim ersten Login (0.43, Plan `Onboarding-Lehrkraefte-Plan.md`).

Ein Dialog führt neue Lehrkräfte durch Erscheinungsbild, Darstellungsstufe, Stundenplan-Kürzel
und Unterrichtsgruppen. Dieser Router liefert nur, was der Dialog **zusätzlich** braucht —
ob er fällig ist, wo die Person stehen geblieben ist, die Fristen der Löschläufe und den Hinweis
der Schule. Die Inhalte der Seiten kommen von den bestehenden Endpunkten.

Der Stand liegt in `user_preferences` (Schlüssel `einrichtung`) und geht mit dem Konto.
"""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.auth.vorschau import ist_vorschau
from app.calendar.service import is_configured
from app.crons.cleanup_service import _ACCOUNT_RETENTION_DAYS, _CONVERSATION_RETENTION_DAYS
from app.db.models import PseudonymAudit, SiteConfig
from app.db.session import get_db
from app.preferences.service import einrichtung_lesen, einrichtung_speichern

router = APIRouter(prefix="/einrichtung", tags=["einrichtung"])

#: Konten, die vor diesem Tag entstanden sind, bekommen den Dialog nicht von selbst (F2 a) —
#: sie haben die Plattform längst eingerichtet und finden ihn unter „Unterricht“ und im Profil.
EINRICHTUNG_AB = date(2026, 11, 14)

#: Rollen mit einer Einrichtung. Rollen sind additiv: Admin mit `teacher` bekommt sie, ein
#: reiner Admin nicht (F10). Schüler:innen folgen mit 0.47.
ROLLEN = ("teacher",)

#: Version des Durchgangs. Ein späterer, verkürzter Durchgang (etwa zum Schuljahreswechsel)
#: zählt hoch.
VERSION = 1
SEITEN_HOECHSTENS = 6

HINWEIS_SCHLUESSEL = "einrichtung_hinweis"

Stand = Literal["spaeter", "erledigt", "abgewaehlt"]


class Stundenplan(BaseModel):
    configured: bool
    kuerzel_gesetzt: bool


class Fristen(BaseModel):
    chat_tage: int
    konto_tage: int


class EinrichtungRead(BaseModel):
    faellig: bool
    stand: Stand | None = None
    seite: int | None = None
    stundenplan: Stundenplan
    fristen: Fristen
    hinweis: str | None = None


class EinrichtungWrite(BaseModel):
    stand: Stand
    seite: int = Field(ge=1, le=SEITEN_HOECHSTENS)


def _hat_einrichtung(user: JwtPayload) -> bool:
    return not ist_vorschau(user) and any(r in user.roles for r in ROLLEN)


async def _konto_neu(db: AsyncSession, pseudonym: str) -> bool:
    seit = (await db.execute(
        select(PseudonymAudit.created_at).where(PseudonymAudit.pseudonym == pseudonym)
    )).scalar_one_or_none()
    return seit is not None and seit.astimezone().date() >= EINRICHTUNG_AB


@router.get("", response_model=EinrichtungRead)
async def einrichtung_lesen_route(
    user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EinrichtungRead:
    stand, kuerzel_gesetzt = await einrichtung_lesen(db, user.sub)
    hinweis = (await db.execute(
        select(SiteConfig.value).where(SiteConfig.key == HINWEIS_SCHLUESSEL)
    )).scalar_one_or_none()
    faellig = (_hat_einrichtung(user) and stand is None
               and await _konto_neu(db, user.sub))
    return EinrichtungRead(
        faellig=faellig,
        stand=(stand or {}).get("stand"),
        seite=(stand or {}).get("seite"),
        stundenplan=Stundenplan(configured=is_configured(), kuerzel_gesetzt=kuerzel_gesetzt),
        fristen=Fristen(chat_tage=_CONVERSATION_RETENTION_DAYS,
                        konto_tage=_ACCOUNT_RETENTION_DAYS),
        hinweis=(hinweis or "").strip() or None,
    )


@router.put("", response_model=EinrichtungRead)
async def einrichtung_setzen(
    body: EinrichtungWrite,
    user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EinrichtungRead:
    if not _hat_einrichtung(user):
        raise HTTPException(status_code=403, detail="Für deine Rolle gibt es keine Einrichtung.")
    await einrichtung_speichern(db, user.sub, {
        "version": VERSION,
        "stand": body.stand,
        "seite": body.seite,
        "am": date.today().isoformat(),
    })
    return await einrichtung_lesen_route(user=user, db=db)
