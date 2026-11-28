"""Endpunkt der Vernetzung der Fächer (Päckchen BE, Teil A, Schritt 3).

`GET /context/vernetzung?fach=&schuljahr=&weg=&entwuerfe=` — nur für Lehrkräfte (F7). Liest nur;
die Arbeit macht `app.context.vernetzung`. `fach` ist das Fachkürzel („PH“) oder die Kennung des
Fachs. Ohne `schuljahr` und `weg` gilt das laufende Schuljahr; `schuljahr` legt alle Stufen in
ein Jahr (etwa das kommende), `weg` zeigt den Weg der Klasse, die im laufenden Jahr in dieser
Stufe ist (F13). Beides zugleich ist ein Widerspruch (422).
"""
from __future__ import annotations

from typing import Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_any_role
from app.auth.jwt import JwtPayload
from app.context import vernetzung_zeit as vz
from app.db.models import Subject
from app.db.session import get_db
from app.planning.calendar import ist_schuljahr

router = APIRouter(prefix="/context/vernetzung", tags=["vernetzung"])
lehrkraft = require_any_role(["teacher", "admin"])


async def _fach_id(db: AsyncSession, angabe: str) -> int:
    angabe = (angabe or "").strip()
    if angabe.isdigit() and (s := await db.get(Subject, int(angabe))) is not None:
        return s.id
    treffer = (await db.execute(sa.select(Subject.id).where(
        sa.func.lower(Subject.fach_code) == angabe.lower()))).scalars().all()
    if len(treffer) != 1:
        raise HTTPException(status_code=404, detail="Fach nicht gefunden")
    return treffer[0]


@router.get("")
async def get_vernetzung(
    fach: str = Query(..., min_length=1, max_length=40),
    schuljahr: Optional[str] = Query(None, description="etwa 2027/28; Vorgabe: das laufende"),
    weg: Optional[int] = Query(None, ge=1, le=13, description="Bezugsstufe: Weg der Klasse, die jetzt in ihr ist"),
    entwuerfe: bool = False,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(lehrkraft),
) -> dict:
    """Zeitachse eines Fachs: Stufen, Kapitel mit Lage, Bezüge, vernetzte Fächer, Leitperspektiven."""
    from app.context.vernetzung import vernetzung

    if schuljahr is not None and weg is not None:
        raise HTTPException(status_code=422, detail="Entweder ein Schuljahr oder der Weg einer Klasse, nicht beides.")
    if schuljahr is not None and not ist_schuljahr(schuljahr):
        raise HTTPException(status_code=422, detail="Schuljahr wie 2027/28 angeben.")
    fach_id = await _fach_id(db, fach)
    try:
        return await vernetzung(db, user, fach_id, modus=vz.WEG if weg is not None else vz.SCHULJAHR,
                                schuljahr=schuljahr, bezugsstufe=weg, entwuerfe=entwuerfe)
    except LookupError:
        raise HTTPException(status_code=404, detail="Fach nicht gefunden")
