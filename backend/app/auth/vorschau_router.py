"""Vorschau betreten und verlassen (0.29, Päckchen S, Schritt 2, ADR-016 Ansatz C).

* ``POST /auth/vorschau`` — eine Lehrkraft sieht die App als Schüler:in eines Jahrgangs,
  wahlweise einer ihrer Unterrichtsgruppen (F3) und mit einem eigenen Assistenten aus dem
  Editor (F6). Das Sitzungs-Cookie trägt danach das Vorschau-Token: Rolle ``student``, die
  echten Rollen im Merkmal (`app.auth.vorschau`).
* ``DELETE /auth/vorschau`` — zurück in die Lehrkraft-Sicht, **mit dem Ablauf der
  Ausgangssitzung** (F1): Die Vorschau verlängert die Sitzung nicht.

**60 Minuten**, höchstens bis zum Ablauf der Ausgangssitzung (F1). Danach trägt das Cookie ein
abgelaufenes Vorschau-Token und sonst nichts. Der Rückweg nimmt es deshalb auch abgelaufen an
(:meth:`JwtService.verify_ohne_ablauf`) — einmal: Das Vorschau-Token wird beim Tausch
widerrufen. Ist auch die Ausgangssitzung abgelaufen, gibt es keinen Rückweg, nur die
Anmeldung.

**Keine Verschachtelung:** Aus einer Vorschau heraus gibt es keine zweite — das Token sagt
ohnehin ``student``, und nur Lehrkräfte dürfen eintreten.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from jose import JWTError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_jwt_service
from app.auth.jwt import JwtPayload, JwtService
from app.auth.vorschau import Vorschau, ist_vorschau, mitglied
from app.config import settings
from app.core.audit import audit
from app.db.models import Assistant, Group, GroupMembership
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

#: Wie lange eine Vorschau höchstens dauert (F1, Jan 02.11.2026).
DAUER_SEKUNDEN = 60 * 60


class VorschauAnfrage(BaseModel):
    jahrgang: int
    gruppe_id: Optional[int] = None
    assistent_id: Optional[int] = None


class VorschauAntwort(BaseModel):
    ok: bool = True
    jahrgang: str | None = None
    gruppe_id: int | None = None
    assistent_id: int | None = None
    #: Ablauf des jetzt gültigen Tokens (Unix-Zeit).
    ablauf: int


def _cookie(response: Response, token: str, ablauf: int) -> None:
    """Dieselben Attribute wie beim Login — sonst ersetzt der Browser das Cookie nicht."""
    response.set_cookie(
        "session", token,
        httponly=True, secure=settings.environment != "development", samesite="lax",
        max_age=max(1, ablauf - int(time.time())), path="/",
    )


async def _pruefe_gruppe(db: AsyncSession, user: JwtPayload, gruppe_id: int) -> None:
    """Eine eigene Unterrichtsgruppe des laufenden Schuljahres (F3) — sonst 404."""
    from app.groups.aktualitaet import gruppen_mit_beleg, gruppen_mit_quellklasse, ist_aktuell
    from app.planning.calendar import load_school_year

    gruppe = await db.scalar(
        select(Group)
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        .where(Group.id == gruppe_id, Group.type == "teaching_group",
               mitglied(user.sub, "teacher"))
    )
    if gruppe is None:
        raise HTTPException(status_code=404, detail="Unterrichtsgruppe nicht gefunden.")
    cfg = load_school_year()
    beleg = await gruppen_mit_beleg(db, [gruppe.id], cfg)
    quellklassen = await gruppen_mit_quellklasse(db, [gruppe.id])
    if not ist_aktuell(gruppe, beleg, cfg, quellklassen):
        raise HTTPException(status_code=404, detail="Unterrichtsgruppe nicht gefunden.")


@router.post("/vorschau", response_model=VorschauAntwort)
async def vorschau_betreten(
    anfrage: VorschauAnfrage,
    request: Request,
    response: Response,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    jwt_service: JwtService = Depends(get_jwt_service),
) -> VorschauAntwort:
    if ist_vorschau(current_user):
        raise HTTPException(status_code=409, detail="Du bist schon in der Vorschau.")
    # Nur aus einer Browser-Sitzung: Ein Zugangstoken hat kein Cookie, das die Vorschau
    # tragen könnte, und soll keine Rollen wechseln.
    if current_user.token_scopes is not None or not request.cookies.get("session"):
        raise HTTPException(status_code=403, detail="Die Vorschau gibt es nur im Browser.")
    if not {"teacher", "admin"} & set(current_user.roles or ()):
        raise HTTPException(status_code=403, detail="Die Vorschau ist für Lehrkräfte.")
    if anfrage.jahrgang not in settings.student_grades:
        raise HTTPException(status_code=422, detail="Diesen Jahrgang gibt es hier nicht.")
    if anfrage.gruppe_id is not None:
        await _pruefe_gruppe(db, current_user, anfrage.gruppe_id)
    if anfrage.assistent_id is not None:
        assistent = await db.get(Assistant, anfrage.assistent_id)
        if assistent is None or assistent.created_by != current_user.sub:
            raise HTTPException(status_code=404, detail="Assistent nicht gefunden.")

    jetzt = int(time.time())
    ablauf = min(jetzt + DAUER_SEKUNDEN, current_user.exp)
    merkmal = Vorschau(
        echte_rollen=list(current_user.roles),
        echter_jahrgang=current_user.grade,
        gruppe_id=anfrage.gruppe_id,
        assistent_id=anfrage.assistent_id,
        beginn=jetzt,
        sitzung_ablauf=current_user.exp,
    )
    token, _ = jwt_service.issue(
        current_user.sub, ["student"], str(anfrage.jahrgang), current_user.display_name,
        sso_groups=current_user.sso_groups, sso_roles=current_user.sso_roles,
        preview=merkmal, exp=ablauf,
    )
    await audit(db, "auth", "preview_entered", akteur=current_user, daten={
        "jahrgang": anfrage.jahrgang,
        "gruppe_id": anfrage.gruppe_id,
        "assistent_id": anfrage.assistent_id,
    })
    await db.commit()
    _cookie(response, token, ablauf)
    return VorschauAntwort(jahrgang=str(anfrage.jahrgang), gruppe_id=anfrage.gruppe_id,
                           assistent_id=anfrage.assistent_id, ablauf=ablauf)


@router.delete("/vorschau", response_model=VorschauAntwort)
async def vorschau_verlassen(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    jwt_service: JwtService = Depends(get_jwt_service),
) -> VorschauAntwort:
    """Zurück in die eigene Sitzung — auch mit abgelaufenem Vorschau-Token (siehe oben)."""
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Nicht authentifiziert")
    try:
        payload = jwt_service.verify_ohne_ablauf(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Ungültiger Token")
    merkmal = payload.preview
    if merkmal is None:
        raise HTTPException(status_code=409, detail="Du bist nicht in der Vorschau.")
    if await jwt_service.is_revoked(db, payload):
        raise HTTPException(status_code=401, detail="Token revoziert")
    jetzt = int(time.time())
    if merkmal.sitzung_ablauf <= jetzt:
        raise HTTPException(status_code=401, detail="Die Sitzung ist abgelaufen. Bitte melde dich neu an.")

    neu, _ = jwt_service.issue(
        payload.sub, merkmal.echte_rollen, merkmal.echter_jahrgang, payload.display_name,
        sso_groups=payload.sso_groups, sso_roles=payload.sso_roles,
        exp=merkmal.sitzung_ablauf,
    )
    abgelaufen = payload.exp <= jetzt
    await audit(db, "auth", "preview_exited", akteur=payload.sub,
                rolle=_fuehrende(merkmal.echte_rollen), daten={
                    "grund": "abgelaufen" if abgelaufen else "beendet",
                    "dauer_sekunden": max(0, min(jetzt, payload.exp) - merkmal.beginn),
                })
    # `revoke` schreibt und committet — der Audit-Eintrag geht im selben Commit mit.
    await jwt_service.revoke(
        db, jti=payload.jti, pseudonym=payload.sub,
        expires_at=datetime.fromtimestamp(payload.exp, timezone.utc),
        reason="vorschau_verlassen",
    )
    _cookie(response, neu, merkmal.sitzung_ablauf)
    return VorschauAntwort(jahrgang=merkmal.echter_jahrgang, ablauf=merkmal.sitzung_ablauf)


def _fuehrende(rollen: list[str]) -> str | None:
    from app.core.audit import _rolle

    return _rolle(rollen)
