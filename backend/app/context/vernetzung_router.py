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


@router.get("/matrix")
async def get_vernetzung_matrix(
    stufe: int = Query(..., ge=1, le=13),
    schuljahr: Optional[str] = Query(None, description="etwa 2027/28; Vorgabe: das laufende"),
    entwuerfe: bool = False,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(lehrkraft),
) -> dict:
    """Teil B (0.67, F10): Fach × Fach einer Klassenstufe mit der Zahl verbundener Kapitelpaare."""
    from app.context.vernetzung import matrix

    if schuljahr is not None and not ist_schuljahr(schuljahr):
        raise HTTPException(status_code=422, detail="Schuljahr wie 2027/28 angeben.")
    return await matrix(db, user, stufe, schuljahr=schuljahr, entwuerfe=entwuerfe)


@router.post("/pdf")
async def vernetzung_pdf(
    anfrage: dict,
    user: JwtPayload = Depends(lehrkraft),
):
    """Die Zeitachse als PDF (Schritt 7, F14 a): je Stufe ein SVG aus dem Browser, geprüft mit
    `pruefe_svg`, und die Liste als Text. Liest und schreibt nichts in der Datenbank."""
    from fastapi import Response
    from pydantic import ValidationError

    from app.context import vernetzung_export as ex

    try:
        a = ex.PdfAnfrage.model_validate(anfrage)
        ex.pruefen(a)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"Ungültige Anfrage: {e.errors()[0].get('msg')}") from None
    except ex.UngueltigesSvg as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    daten = await ex.render_pdf(a)
    return Response(content=daten, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{ex.dateiname(a.fach)}"'})
