"""Endpunkte der Jahresverlaufspläne (Päckchen BD, Schritt 4).

Lesen: Lehrkräfte und Admins. Schreiben: die Fachschaft des Fachs und Admins, nur im laufenden
oder einem kommenden Schuljahr. Regeln und Darstellung in :mod:`app.context.verlaufsplan`.

Rückgängig macht der Editor (BD Schritt 5): Er hält die vorigen Stände und speichert einen davon
zurück — jeder Stand ist ein vollständiger Plan, es gibt kein Teil-Update.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_any_role
from app.auth.jwt import JwtPayload
from app.context import verlaufsplan as vp
from app.context.curriculum_entwurf import ENTWURF, NUR_FACHSCHAFT
from app.db.models import ContextNode, Subject
from app.db.session import get_db
from app.planning.calendar import ist_schuljahr

router = APIRouter(prefix="/context/verlaufsplaene", tags=["verlaufsplaene"])
lehrkraft = require_any_role(["teacher", "admin"])

NICHT_GEFUNDEN = HTTPException(status_code=404, detail="Jahresverlaufsplan nicht gefunden")
ARCHIVIERT = HTTPException(status_code=409, detail="Pläne vergangener Schuljahre sind nur lesbar.")


class Abschnitt(BaseModel):
    id: Optional[str] = Field(default=None, max_length=40)
    titel: str = Field(default="", max_length=200)
    # Richtgröße 1–6 (F2); länger geht, bis zu einem ganzen Schuljahr
    wochen: int = Field(ge=1, le=45)
    kapitel_ids: list[UUID] = Field(default_factory=list, max_length=20)
    # Bei sequenzgenauer Planung (Schritt 7) — es gilt das Feld der Planungsart
    sequenz_ids: list[UUID] = Field(default_factory=list, max_length=40)
    notiz: str = Field(default="", max_length=2000)


class PlanSpeichern(BaseModel):
    abschnitte: list[Abschnitt] = Field(default_factory=list, max_length=60)
    # Wechsel der Planungsart: Die Abschnitte kommen in der alten Art und werden umgerechnet.
    # Ein Raster gibt es seit Schritt 7 nicht mehr — die Dauer jedes Abschnitts regelt das.
    planungsart: Optional[Literal["sequenz", "kapitel"]] = None


class PlanAnlegen(PlanSpeichern):
    planungsart: Literal["sequenz", "kapitel"] = "sequenz"
    subject_id: int
    stufe: int = Field(ge=1, le=13)
    schuljahr: str

    @field_validator("schuljahr")
    @classmethod
    def _schuljahr(cls, v: str) -> str:
        if not ist_schuljahr(v):
            raise ValueError("Schuljahr in der Form „2027/28“.")
        return v


def _metadata(alt: dict, daten: PlanSpeichern, abschnitte_roh: Optional[list[dict]] = None) -> dict:
    """Metadaten des Plans aus der Eingabe. `abschnitte_roh` sind schon umgerechnete Abschnitte
    (Wechsel der Planungsart); sonst die aus `daten`."""
    abschnitte = []
    for a in abschnitte_roh if abschnitte_roh is not None else [x.model_dump(mode="json") for x in daten.abschnitte]:
        d = dict(a)
        d["id"] = d["id"] or uuid4().hex[:12]
        d["titel"] = d["titel"].strip()
        d["notiz"] = d["notiz"].strip()
        d["kapitel_ids"] = list(dict.fromkeys(d.get("kapitel_ids") or []))
        d["sequenz_ids"] = list(dict.fromkeys(d.get("sequenz_ids") or []))
        abschnitte.append(d)
    meta = {k: v for k, v in alt.items() if k != "raster"}
    return {**meta, "abschnitte": abschnitte, "planungsart": daten.planungsart or vp.planungsart(alt)}


@router.get("")
async def verlaufsplaene_liste(
    subject_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(lehrkraft),
):
    """Alle Pläne (eines Fachs), neueste Schuljahre zuerst. Die Oberfläche teilt nach
    `archiviert` in laufende/kommende und das Archiv (F10)."""
    stmt = sa.select(ContextNode, Subject).outerjoin(Subject, Subject.id == ContextNode.subject_id).where(
        ContextNode.content_type == vp.TYP, ContextNode.status.in_((ENTWURF, vp.BESCHLOSSEN)))
    if subject_id is not None:
        stmt = stmt.where(ContextNode.subject_id == subject_id)
    zeilen = (await db.execute(stmt)).all()
    plaene = [vp.kurz(p, f) for p, f in zeilen]
    plaene.sort(key=lambda p: (p["schuljahr"] or "", -(p["stufe"] or 0)), reverse=True)
    darf = await vp.darf_bearbeiten(db, subject_id, user) if subject_id is not None else False
    return {"aktuelles_schuljahr": vp.aktuelles_schuljahr(), "plaene": plaene, "darf_anlegen": darf}


@router.post("", status_code=201)
async def verlaufsplan_anlegen(
    daten: PlanAnlegen, db: AsyncSession = Depends(get_db), user: JwtPayload = Depends(lehrkraft),
):
    """Neuer Plan als Entwurf (F8). Nur für das laufende oder ein kommendes Schuljahr."""
    fach = await db.get(Subject, daten.subject_id)
    if fach is None:
        raise HTTPException(status_code=404, detail="Fach nicht gefunden")
    if not await vp.darf_bearbeiten(db, daten.subject_id, user):
        raise HTTPException(status_code=403, detail=NUR_FACHSCHAFT)
    if daten.schuljahr < vp.aktuelles_schuljahr():
        raise HTTPException(status_code=422, detail="Für vergangene Schuljahre legst du keinen Plan mehr an.")
    gruppe = await vp.fachschaftsgruppe(db, daten.subject_id)
    if gruppe is None:
        raise HTTPException(status_code=422, detail=f"{fach.name} hat keine Fachschaft in der Plattform.")
    plan = ContextNode(
        category="knowledge", content_type=vp.TYP, status=ENTWURF,
        title=f"Jahresverlaufsplan {fach.name} Kl. {daten.stufe} {daten.schuljahr}",
        subject_id=daten.subject_id, min_grade=daten.stufe, max_grade=daten.stufe,
        read_scope="school", write_scope="subject", write_scope_group_id=gruppe,
        owner_pseudonym=user.sub,
        metadata_=_metadata({"schuljahr": daten.schuljahr}, daten),
    )
    try:
        async with db.begin_nested():
            db.add(plan)
            await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail=(
            f"Für {fach.name} Kl. {daten.stufe} gibt es {daten.schuljahr} schon einen Plan."))
    await vp.bezugskanten_abgleichen(db, plan)
    await db.commit()
    await db.refresh(plan)
    return await vp.voll(db, plan, user)


@router.get("/{plan_id}")
async def verlaufsplan_lesen(
    plan_id: UUID, db: AsyncSession = Depends(get_db), user: JwtPayload = Depends(lehrkraft),
):
    plan = await vp.lade(db, plan_id)
    if plan is None:
        raise NICHT_GEFUNDEN
    return await vp.voll(db, plan, user)


async def _zum_schreiben(db: AsyncSession, plan_id: UUID, user) -> ContextNode:
    plan = await vp.lade(db, plan_id)
    if plan is None:
        raise NICHT_GEFUNDEN
    if not await vp.darf_bearbeiten(db, plan, user):
        raise HTTPException(status_code=403, detail=NUR_FACHSCHAFT)
    if vp.ist_archiviert(plan):
        raise ARCHIVIERT
    return plan


@router.put("/{plan_id}")
async def verlaufsplan_speichern(
    plan_id: UUID, daten: PlanSpeichern,
    db: AsyncSession = Depends(get_db), user: JwtPayload = Depends(lehrkraft),
):
    """Der ganze Plan auf einmal — Abschnitte in Planreihenfolge und Raster. Ein beschlossener
    Plan bleibt beschlossen (F8: Änderungen danach gehen direkt)."""
    plan = await _zum_schreiben(db, plan_id, user)
    alt = plan.metadata_ or {}
    roh = None
    if daten.planungsart and daten.planungsart != vp.planungsart(alt):
        roh = [a.model_dump(mode="json") for a in daten.abschnitte]
        bezug = {str(k) for a in roh for k in (a.get("sequenz_ids") or []) + (a.get("kapitel_ids") or [])}
        roh = vp.umrechnen(roh, daten.planungsart,
                           kapitel_von=await vp.kapitel_der_sequenzen(db, bezug),
                           sequenzen_von=await vp.sequenzen_der_kapitel(db, bezug))
    plan.metadata_ = _metadata(alt, daten, roh)
    await vp.bezugskanten_abgleichen(db, plan)
    await db.commit()
    await db.refresh(plan)
    return await vp.voll(db, plan, user)


@router.post("/{plan_id}/beschliessen")
async def verlaufsplan_beschliessen(
    plan_id: UUID, db: AsyncSession = Depends(get_db), user: JwtPayload = Depends(lehrkraft),
):
    """Entwurf → beschlossen. Der Beschluss fällt in der Fachkonferenz; hier wird er vermerkt."""
    plan = await _zum_schreiben(db, plan_id, user)
    if plan.status != ENTWURF:
        raise HTTPException(status_code=409, detail="Der Plan ist schon beschlossen.")
    plan.status = vp.BESCHLOSSEN
    plan.metadata_ = {**(plan.metadata_ or {}), "beschlossen_am": vp.heute().isoformat()}
    await db.commit()
    await db.refresh(plan)
    return await vp.voll(db, plan, user)


class Uebernehmen(BaseModel):
    schuljahr: str

    @field_validator("schuljahr")
    @classmethod
    def _schuljahr(cls, v: str) -> str:
        if not ist_schuljahr(v):
            raise ValueError("Schuljahr in der Form „2027/28“.")
        return v


@router.post("/{plan_id}/uebernehmen", status_code=201)
async def verlaufsplan_uebernehmen(
    plan_id: UUID, daten: Uebernehmen,
    db: AsyncSession = Depends(get_db), user: JwtPayload = Depends(lehrkraft),
):
    """Einen Plan — meist den des Vorjahrs aus dem Archiv — als **Entwurf** in ein späteres
    Schuljahr übernehmen (BD Schritt 6). Reihenfolge und Dauern legen sich auf den neuen Kalender;
    Kapitel werden auf die Curricula von heute abgebildet. Neu schreiben bleibt die Regel, das hier
    ist nur der Ausgangspunkt."""
    quelle = await vp.lade(db, plan_id)
    if quelle is None:
        raise NICHT_GEFUNDEN
    if not await vp.darf_bearbeiten(db, quelle, user):
        raise HTTPException(status_code=403, detail=NUR_FACHSCHAFT)
    if daten.schuljahr < vp.aktuelles_schuljahr():
        raise HTTPException(status_code=422, detail="Für vergangene Schuljahre legst du keinen Plan mehr an.")
    if daten.schuljahr == (quelle.metadata_ or {}).get("schuljahr"):
        raise HTTPException(status_code=422, detail="Wähle ein anderes Schuljahr als das des Plans.")
    fach = await db.get(Subject, quelle.subject_id)
    gruppe = await vp.fachschaftsgruppe(db, quelle.subject_id)
    if gruppe is None:
        raise HTTPException(status_code=422, detail=f"{fach.name} hat keine Fachschaft in der Plattform.")

    alt = (quelle.metadata_ or {}).get("abschnitte", [])
    curricula = await vp.curricula_der_stufe(db, quelle.subject_id, quelle.min_grade)
    art = vp.planungsart(quelle)
    alte_ids = {str(k) for a in alt for k in a.get(vp.BEZUGSFELD[art]) or []}
    titel = await vp.knotentitel(db, alte_ids, vp.BEZUGSTYP[art])
    kapitel_alt = await vp.kapiteltitel_der_sequenzen(db, alte_ids) if art == vp.SEQUENZ else {}
    abschnitte, entfallen = vp.bezuege_abbilden(alt, curricula, art, titel, kapitel_alt)
    abschnitte = [{**a, "id": uuid4().hex[:12]} for a in abschnitte]

    plan = ContextNode(
        category="knowledge", content_type=vp.TYP, status=ENTWURF,
        title=f"Jahresverlaufsplan {fach.name} Kl. {quelle.min_grade} {daten.schuljahr}",
        subject_id=quelle.subject_id, min_grade=quelle.min_grade, max_grade=quelle.max_grade,
        read_scope="school", write_scope="subject", write_scope_group_id=gruppe,
        owner_pseudonym=user.sub,
        metadata_={"schuljahr": daten.schuljahr, "abschnitte": abschnitte,
                   "planungsart": vp.planungsart(quelle),
                   "uebernommen_aus": str(quelle.id)},
    )
    try:
        async with db.begin_nested():
            db.add(plan)
            await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail=(
            f"Für {fach.name} Kl. {quelle.min_grade} gibt es {daten.schuljahr} schon einen Plan."))
    await vp.bezugskanten_abgleichen(db, plan)
    await db.commit()
    await db.refresh(plan)
    return {**await vp.voll(db, plan, user), "kapitel_entfallen": entfallen}


@router.delete("/{plan_id}", status_code=204)
async def verlaufsplan_loeschen(
    plan_id: UUID, db: AsyncSession = Depends(get_db), user: JwtPayload = Depends(lehrkraft),
):
    plan = await _zum_schreiben(db, plan_id, user)
    await db.delete(plan)
    await db.commit()
    return Response(status_code=204)
