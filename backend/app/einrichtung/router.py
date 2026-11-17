"""Einrichtung beim ersten Login (0.43 Lehrkräfte, 0.47 Schüler:innen).

Pläne `Onboarding-Lehrkraefte-Plan.md` und `Onboarding-Schueler-Plan.md`. Ein Dialog führt neue
Lehrkräfte durch Erscheinungsbild, Darstellungsstufe, Stundenplan-Kürzel und Unterrichtsgruppen,
neue Schüler:innen durch Erscheinungsbild, das Wichtigste zu Daten und Budget und ihre Fächer. Dieser Router liefert nur, was der Dialog **zusätzlich** braucht —
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

#: Stichtag je Rolle: Konten, die vor diesem Tag entstanden sind, bekommen den Dialog nicht von
#: selbst (F2 a bzw. F1 a) — sie kennen die Plattform schon und finden ihn im Profil (Lehrkräfte
#: auch unter „Unterricht“). Ein eigener Tag je Rolle, sonst bekäme mit einer neuen Rolle ihr
#: ganzer Bestand seit dem älteren Stichtag den Dialog.
#: ⚠️ Schüler:innen: bei der Release-Vorbereitung von 0.47 auf den Tag des Ausrollens setzen.
EINRICHTUNG_AB: dict[str, date] = {
    "teacher": date(2026, 11, 14),
    "student": date(2026, 11, 18),
}

#: Rollen mit einer Einrichtung, in der Reihenfolge des Vorrangs. Rollen sind additiv: Admin mit
#: `teacher` bekommt die der Lehrkraft, ein reiner Admin keine (F10); wer `teacher` und
#: `student` ist, die der Lehrkraft (0.47, F9).
ROLLEN = ("teacher", "student")

#: Version des Durchgangs. Ein späterer, verkürzter Durchgang (etwa zum Schuljahreswechsel)
#: zählt hoch.
VERSION = 1
SEITEN_HOECHSTENS = 6

#: Site-Text „Hinweis der Schule“ je Rolle (0.47, F7 a: an Schüler:innen schreibt eine Schule
#: anderes als an Lehrkräfte).
HINWEIS_SCHLUESSEL: dict[str, str] = {
    "teacher": "einrichtung_hinweis",
    "student": "einrichtung_hinweis_schueler",
}

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


def einrichtungs_rolle(user: JwtPayload) -> str | None:
    """Nach welcher Rolle sich die Einrichtung richtet — `None`: keine.

    In der Vorschau die **simulierte** Rolle: Die Lehrkraft soll dort sehen, was ihre Klasse
    sieht, auch den Hinweis der Schule an Schüler:innen (F6 a). Fällig ist sie dort nie, und
    speichern lässt sie sich nicht (`_hat_einrichtung`).
    """
    return next((r for r in ROLLEN if r in user.roles), None)


def _hat_einrichtung(user: JwtPayload) -> bool:
    return not ist_vorschau(user) and einrichtungs_rolle(user) is not None


async def _konto_neu(db: AsyncSession, pseudonym: str, rolle: str) -> bool:
    seit = (await db.execute(
        select(PseudonymAudit.created_at).where(PseudonymAudit.pseudonym == pseudonym)
    )).scalar_one_or_none()
    return seit is not None and seit.astimezone().date() >= EINRICHTUNG_AB[rolle]


@router.get("", response_model=EinrichtungRead)
async def einrichtung_lesen_route(
    user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EinrichtungRead:
    stand, kuerzel_gesetzt = await einrichtung_lesen(db, user.sub)
    rolle = einrichtungs_rolle(user)
    hinweis = None
    if rolle is not None:
        hinweis = (await db.execute(
            select(SiteConfig.value).where(SiteConfig.key == HINWEIS_SCHLUESSEL[rolle])
        )).scalar_one_or_none()
    faellig = (_hat_einrichtung(user) and stand is None
               and await _konto_neu(db, user.sub, rolle))
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
