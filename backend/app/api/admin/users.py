"""Admin: Nutzer-/Sitzungsverwaltung (Sicherheits-Audit #11, „D").

Listet Nutzer (pseudonym, effektive Rollen, letzter Login) und erlaubt Admins, alle aktiven
Sitzungen eines Nutzers zu beenden — nützlich, wenn im SSO eine (additive) Rolle entzogen
wurde und die erhöhten Rechte nicht bis zum nächsten Login des Nutzers bestehen bleiben sollen.
Setzt `pseudonym_audit.revoked_all_before = now`; `JwtService.is_revoked` verwirft danach jedes
vorher ausgestellte Token → erzwingt Re-Login (dabei bewertet das SSO die Rolle neu).
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.db.models import PseudonymAudit
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["admin-users"])


class UserItem(BaseModel):
    pseudonym: str
    roles: list[str]  # effektive Rollen (roles-Spalte, sonst Primärrolle als Fallback)
    grade: Optional[int]
    last_login_at: Optional[datetime]
    revoked_all_before: Optional[datetime]  # gesetzt = Sitzungen wurden beendet


class UsersResponse(BaseModel):
    users: list[UserItem]


class RevokeResult(BaseModel):
    ok: bool
    pseudonym: str
    revoked_all_before: datetime


def _effective_roles(row: PseudonymAudit) -> list[str]:
    """Voller Rollensatz; für vor dem Rollout angelegte Zeilen (roles=NULL) die Primärrolle."""
    if row.roles:
        return list(row.roles)
    return [row.role] if row.role else []


@router.get("", response_model=UsersResponse)
async def list_users(
    role: Optional[str] = Query(default=None, description="Nur Nutzer mit dieser effektiven Rolle"),
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> UsersResponse:
    """Nutzerliste, absteigend nach letztem Login. Optionaler Rollenfilter (z. B. `admin`)."""
    result = await db.execute(
        select(PseudonymAudit).order_by(PseudonymAudit.last_login_at.desc().nulls_last())
    )
    rows = result.scalars().all()
    items = []
    for row in rows:
        eff = _effective_roles(row)
        if role is not None and role not in eff:
            continue
        items.append(UserItem(
            pseudonym=row.pseudonym,
            roles=eff,
            grade=row.grade,
            last_login_at=row.last_login_at,
            revoked_all_before=row.revoked_all_before,
        ))
    return UsersResponse(users=items)


@router.post("/{pseudonym}/revoke-sessions", response_model=RevokeResult)
async def revoke_sessions(
    pseudonym: str,
    current_user: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> RevokeResult:
    """Beendet alle aktiven Sitzungen eines Nutzers (setzt `revoked_all_before = now`)."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(PseudonymAudit)
        .where(PseudonymAudit.pseudonym == pseudonym)
        .values(revoked_all_before=now)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Nutzer nicht gefunden.")
    await db.commit()
    logger.info(
        "Admin %s hat alle Sitzungen von %s beendet (revoked_all_before=%s)",
        current_user.sub, pseudonym, now.isoformat(),
    )
    return RevokeResult(ok=True, pseudonym=pseudonym, revoked_all_before=now)
