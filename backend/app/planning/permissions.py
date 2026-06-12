"""Berechtigungs-Helper für die Unterrichtsplanung.

require_group_teacher: 404 wenn Gruppe nicht existiert/kein teaching_group,
403 wenn der Nutzer nicht Lehrkraft dieser Gruppe ist.
Kein Admin-Sonderfall (CLAUDE.md: Admin verhält sich wie Lehrkraft in Chat-UI —
ohne Mitgliedschaft kein Zugriff auf Gruppenplanung).
"""

from fastapi import HTTPException
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import JwtPayload
from app.db.models import Group, GroupMembership


async def require_group_teacher(
    group_id: int,
    user: JwtPayload,
    db: AsyncSession,
) -> Group:
    """Lädt die Gruppe und prüft Lehrkraft-Mitgliedschaft.

    Raises HTTPException 404 wenn Gruppe fehlt oder kein teaching_group.
    Raises HTTPException 403 wenn Nutzer nicht Mitglied mit role_in_group='teacher'.
    """
    group = await db.get(Group, group_id)
    if group is None or group.type != "teaching_group":
        raise HTTPException(status_code=404, detail="Unterrichtsgruppe nicht gefunden")

    result = await db.execute(
        sa.select(GroupMembership).where(
            GroupMembership.group_id == group_id,
            GroupMembership.pseudonym == user.sub,
            GroupMembership.role_in_group == "teacher",
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")

    return group
