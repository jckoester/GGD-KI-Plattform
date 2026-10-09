"""Der Stundenbezug einer Konversation (0.15, Päckchen A Schritt 2).

Eine Konversation kann sich auf eine Unterrichtsstunde beziehen
(`conversations.stunde_node_id`). Gesetzt wird er beim Anlegen, aus der Entwurfsansicht. Der
Assistent bekommt ihn als Systemzeile (`bezugszeile`), die Stundenwerkzeuge nehmen ihn als
Vorgabe, wenn das Modell keine Kennung nennt.

**Zwei Regeln, zwei Funktionen:**

* *Setzen* (`stunde_fuer_bezug`) nur als Lehrkraft der Gruppe der Stunde (Jan, 09.10.2026).
  Mit dem Bezug bekommt die Konversation die Gruppe der Stunde — und eine Gruppe trägt eine
  Konversation nur bei Mitgliedschaft (`_eigene_unterrichtsgruppe` im Chat-Router). Die
  Eigentümerin ohne Mitgliedschaft (Archiv-Fall) liest die Stunde, setzt sie aber nicht.
* *Lesen* (`bezugszeile`) wird bei jedem Aufbau des Prompts neu geprüft, mit der Leseregel aus
  `zugang_zur_stunde`. Dasselbe Muster wie die Bausteine unter der Antwort (0.14): Was einmal
  sichtbar war, ist es nicht für immer.
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode, Group, LessonSlot
from app.planning.permissions import zugang_zur_stunde
from app.planning.student_context import _fmt_datum


async def _stunde(db: AsyncSession, stunde_id: UUID) -> ContextNode | None:
    stunde = await db.get(ContextNode, stunde_id)
    if stunde is None or stunde.status != "active" or stunde.content_type != "unterrichtsstunde":
        return None
    return stunde


async def stunde_fuer_bezug(db: AsyncSession, stunde_id: UUID, user) -> ContextNode:
    """Die Stunde, wenn diese Person sie als Bezug setzen darf.

    :raises HTTPException: 404, wenn es die Stunde nicht gibt; 403 ohne Mitgliedschaft als
        Lehrkraft ihrer Gruppe — auch für die Eigentümerin, die sie nur noch lesen darf.
    """
    stunde = await _stunde(db, stunde_id)
    if stunde is None:
        raise HTTPException(status_code=404, detail="Stunde nicht gefunden")
    if not await zugang_zur_stunde(stunde, user, db):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    return stunde


async def bezugszeile(db: AsyncSession, stunde_id: UUID | None, user) -> str | None:
    """Die Systemzeile zur Bezugsstunde — None ohne Bezug oder ohne Lesezugang."""
    if stunde_id is None:
        return None
    stunde = await _stunde(db, stunde_id)
    if stunde is None:
        return None
    try:
        await zugang_zur_stunde(stunde, user, db)
    except HTTPException:
        return None

    angaben: list[str] = []
    if stunde.write_scope_group_id is not None:
        gruppe = await db.get(Group, stunde.write_scope_group_id)
        if gruppe is not None:
            angaben.append(gruppe.anzeigename)
    slot = (
        await db.execute(sa.select(LessonSlot).where(LessonSlot.stunde_node_id == stunde.id))
    ).scalars().first()
    if slot is not None:
        angaben.append(_fmt_datum(slot.date))
        if slot.start_period:
            ende = slot.start_period + slot.periods - 1
            angaben.append(
                f"{slot.start_period}. Stunde" if ende == slot.start_period
                else f"{slot.start_period}.–{ende}. Stunde"
            )
    klammer = f" ({', '.join(angaben)})" if angaben else ""
    return (
        f"Bezugsstunde dieser Unterhaltung: „{stunde.title}“{klammer}, Kennung {stunde.id}. "
        "Ist von „der Stunde“ die Rede, ist diese gemeint; die Stundenwerkzeuge nehmen sie, "
        "wenn keine Kennung angegeben ist."
    )
