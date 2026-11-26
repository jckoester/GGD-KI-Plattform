"""Der Jahresverlaufsplan im Planer einer Gruppe (Päckchen BD Teil B).

`GET /planning/groups/{id}/verlaufsplan` (Schritt 1): Plan der Fachschaft für Fach, Stufe und
laufendes Schuljahr der Gruppe, für die Spur im Planer. Nur die Lehrkräfte der Gruppe — lesen
könnten sie den Plan auch in der Bibliothek, hier aber nur im Zusammenhang ihrer Gruppe.
Regeln in :mod:`app.planning.verlaufsplan_gruppe`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_any_role
from app.auth.jwt import JwtPayload
from app.context import verlaufsplan as vp
from app.db.session import get_db
from app.planning.permissions import require_group_teacher
from app.planning.verlaufsplan_gruppe import abschnitt_je_woche, plan_der_gruppe

router = APIRouter(prefix="/planning/groups", tags=["planning", "verlaufsplaene"])
lehrkraft = require_any_role(["teacher", "admin"])


@router.get("/{group_id}/verlaufsplan")
async def verlaufsplan_der_gruppe(
    group_id: int, db: AsyncSession = Depends(get_db), user: JwtPayload = Depends(lehrkraft),
):
    group = await require_group_teacher(group_id, user, db)
    pg = await plan_der_gruppe(db, group)
    plan = await vp.voll(db, pg.plan, user) if pg.plan else None
    return {
        "schuljahr": pg.schuljahr,
        "subject_id": group.subject_id,
        "stufe": pg.stufe,
        "grund": pg.grund,
        "plan": plan,
        "abschnitt_je_woche": abschnitt_je_woche(plan["lage"]) if plan else {},
    }
