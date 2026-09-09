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


async def ist_gruppenlehrkraft(
    group_id: int,
    user: JwtPayload,
    db: AsyncSession,
) -> bool:
    """Wie :func:`require_group_teacher`, aber als Frage statt als Schranke."""
    result = await db.execute(
        sa.select(GroupMembership).where(
            GroupMembership.group_id == group_id,
            GroupMembership.pseudonym == user.sub,
            GroupMembership.role_in_group == "teacher",
        )
    )
    return result.scalar_one_or_none() is not None


async def zugang_zur_stunde(
    lesson,
    user: JwtPayload,
    db: AsyncSession,
) -> bool:
    """Darf diese Person die Stunde sehen — und darf sie sie ändern?

    Zwei Wege hinein, einer heraus:

    * **Mitgliedschaft** in der Gruppe → lesen *und* ändern. Der Regelfall.
    * **Eigentum** an der Stunde → nur lesen. Der Archiv-Fall: Mit dem
      Schuljahreswechsel fällt die Mitgliedschaft (Immediate Mirror in
      ``sync_groups``), der eigene Stundenentwurf bleibt.

    **Warum das keine aufgeweichte Regel ist.** „Eigenes darf man lesen" ist die
    erste Zeile der Sichtbarkeitsregel für Knoten (`app/context/visibility.py`) —
    ein Stundenentwurf *ist* ein Knoten, und über `GET /context/nodes/{id}` war er
    für seine Eigentümerin ohnehin lesbar, nur ohne Verlaufsplan. Der Planer war
    die einzige Stelle, die dieser Regel nicht folgte; damit war die Auskunft über
    denselben Gegenstand von der Tür abhängig, durch die man kam.

    Geändert wird weiterhin **nur** mit Mitgliedschaft: `PATCH /lessons/{id}` und
    die Nachbereitung bleiben unangetastet.

    :returns: ``True``, wenn geändert werden darf.
    :raises HTTPException: 403, wenn keiner der beiden Wege trägt.
    """
    group_id = lesson.write_scope_group_id
    if group_id is not None and await ist_gruppenlehrkraft(group_id, user, db):
        return True
    if lesson.owner_pseudonym is not None and lesson.owner_pseudonym == user.sub:
        return False
    raise HTTPException(status_code=403, detail="Keine Berechtigung")
