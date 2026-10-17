"""Hinweise auf Neuerungen: lesen und wegklicken (`app/neuigkeiten/quelle.py`)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.models import PseudonymAudit
from app.db.session import get_db
from app.neuigkeiten.quelle import alle, sichtbar
from app.preferences.service import neuigkeit_gelesen_merken, neuigkeiten_gelesen, ui_stufe
from app.ui.levels import load_ui_levels

router = APIRouter(prefix="/neuigkeiten", tags=["neuigkeiten"])


class NeuigkeitRead(BaseModel):
    id: str
    titel: str
    text: str
    link: str | None = None


@router.get("", response_model=list[NeuigkeitRead])
async def meine_neuigkeiten(
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NeuigkeitRead]:
    konto_seit = (await db.execute(
        select(PseudonymAudit.created_at).where(PseudonymAudit.pseudonym == current_user.sub)
    )).scalar_one_or_none()
    liste = sichtbar(
        alle(),
        rollen=list(current_user.roles),
        gelesen=await neuigkeiten_gelesen(db, current_user.sub),
        konto_seit=konto_seit,
        stufe=await ui_stufe(db, current_user.sub, list(current_user.roles)),
        stufen=load_ui_levels(),
        heute=date.today(),
    )
    return [NeuigkeitRead(id=n.id, titel=n.titel, text=n.text, link=n.link) for n in liste]


@router.post("/{kennung}/gelesen", status_code=204)
async def neuigkeit_gelesen(
    kennung: str,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if kennung not in {n.id for n in alle()}:
        raise HTTPException(status_code=404, detail="Diesen Hinweis gibt es nicht.")
    await neuigkeit_gelesen_merken(db, current_user.sub, kennung)
