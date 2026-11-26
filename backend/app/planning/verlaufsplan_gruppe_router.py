"""Der Jahresverlaufsplan im Planer einer Gruppe (Päckchen BD Teil B).

`GET /planning/groups/{id}/verlaufsplan` (Schritt 1): Plan der Fachschaft für Fach, Stufe und
laufendes Schuljahr der Gruppe, für die Spur im Planer. Nur die Lehrkräfte der Gruppe — lesen
könnten sie den Plan auch in der Bibliothek, hier aber nur im Zusammenhang ihrer Gruppe.
`GET …/verlaufsplan/vorschau` (Schritt 3): was „Einheiten aus dem Jahresverlaufsplan anlegen“
täte, je Abschnitt — ohne etwas zu schreiben. Ein GET, weil die Vorschau nur liest (Plan: POST).

`POST …/verlaufsplan/anlegen` und `…/verlaufsplan/rueckgaengig` (Schritt 4): die Vorschläge
anlegen; einen Lauf zurücknehmen, solange seine Einheiten noch keine Stunden haben.

Regeln in :mod:`app.planning.verlaufsplan_gruppe` und :mod:`app.planning.verlaufsplan_vorlage`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_any_role
from app.auth.jwt import JwtPayload
from app.context import verlaufsplan as vp
from app.db.session import get_db
from app.planning.permissions import require_group_teacher
from app.planning import verlaufsplan_gruppe as vg
from app.planning.verlaufsplan_gruppe import abschnitt_je_woche, plan_der_gruppe, vorschlaege

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


KEIN_PLAN = "Für diese Gruppe gibt es im laufenden Schuljahr keinen Jahresverlaufsplan der Fachschaft."
KEIN_KALENDER = "Für dieses Schuljahr liegt der Kalender der Schule noch nicht vor."


def _vorschlag_dict(v, curricula: list[dict]) -> dict:
    return {
        "index": v.index, "nr": v.nr, "abschnitt_id": v.abschnitt_id, "titel": v.titel, "wochen": v.wochen,
        "anlegen": v.anlegen, "grund": v.grund, "kapitel_id": v.kapitel_id, "kapitel_titel": v.kapitel_titel,
        "kapitel_fehlt": v.kapitel_fehlt, "beschreibung": v.beschreibung, "stunden": v.stunden, "belegt": v.belegt,
        "ohne_termine": v.ohne_termine, "farbe": vg.farbe_des_kapitels(v.kapitel_id, curricula),
    }


async def _plan_mit_lage(group_id: int, db: AsyncSession, user):
    group = await require_group_teacher(group_id, user, db)
    pg = await plan_der_gruppe(db, group)
    if pg.plan is None:
        raise HTTPException(status_code=404, detail=KEIN_PLAN)
    voll = await vp.voll(db, pg.plan, user)
    if voll["lage"] is None:
        raise HTTPException(status_code=409, detail=KEIN_KALENDER)
    return group, pg, voll


@router.get("/{group_id}/verlaufsplan/vorschau")
async def verlaufsplan_vorschau(
    group_id: int, db: AsyncSession = Depends(get_db), user: JwtPayload = Depends(lehrkraft),
):
    group, pg, voll = await _plan_mit_lage(group_id, db, user)
    liste = await vorschlaege(db, group, pg.plan, voll["lage"])
    return {
        "plan_id": voll["id"], "titel": voll["titel"], "status": voll["status"], "schuljahr": pg.schuljahr,
        "vorschlaege": [_vorschlag_dict(v, voll["curricula"]) for v in liste],
        "neu": sum(1 for v in liste if v.anlegen),
        "stunden": sum(v.stunden for v in liste),
    }


NICHT_MEHR = ("Rückgängig geht nicht mehr: In mindestens einer der angelegten Einheiten gibt es schon "
              "Stunden. Einzelne Einheiten löschst du in der Jahresübersicht.")


@router.post("/{group_id}/verlaufsplan/anlegen")
async def verlaufsplan_anlegen(
    group_id: int, db: AsyncSession = Depends(get_db), user: JwtPayload = Depends(lehrkraft),
):
    """Legt an, was die Vorschau in diesem Moment vorschlägt — neu gerechnet, nicht aus dem Browser."""
    group, pg, voll = await _plan_mit_lage(group_id, db, user)
    return await vg.anlegen(db, group, pg.plan, voll, user)


class Lauf(BaseModel):
    lauf_id: str = Field(min_length=1, max_length=64)


@router.post("/{group_id}/verlaufsplan/rueckgaengig")
async def verlaufsplan_rueckgaengig(
    group_id: int, daten: Lauf, db: AsyncSession = Depends(get_db), user: JwtPayload = Depends(lehrkraft),
):
    group = await require_group_teacher(group_id, user, db)
    try:
        geloescht = await vg.rueckgaengig(db, group, daten.lauf_id)
    except vg.NichtMehrRueckgaengig:
        raise HTTPException(status_code=409, detail=NICHT_MEHR) from None
    if not geloescht:
        raise HTTPException(status_code=404, detail="Die angelegten Einheiten gibt es nicht mehr.")
    return {"einheiten": geloescht}
