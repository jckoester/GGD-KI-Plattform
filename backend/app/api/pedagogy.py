"""Pädagogik-Konfiguration für die UI (Phase 13).

Liefert die verfügbaren Lernverhalten-Augmentierungen (Key + Label) für die
Checkbox-Liste im Assistenten-Editor. Read-only; die Texte selbst liegen in
``pedagogy.yaml`` und werden nur im Backend beim System-Prompt-Aufbau verwendet.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import require_any_role
from app.auth.jwt import JwtPayload
from app.assistants import bausteine as bausteine_
from app.pedagogy.config import list_augmentations

router = APIRouter(prefix="/pedagogy", tags=["pedagogy"])


class AugmentationItem(BaseModel):
    key: str
    label: str


class AugmentationsResponse(BaseModel):
    augmentations: list[AugmentationItem]


@router.get("/augmentations", response_model=AugmentationsResponse)
async def get_augmentations(
    _: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
) -> AugmentationsResponse:
    return AugmentationsResponse(augmentations=list_augmentations())


class BausteinItem(BaseModel):
    key: str
    label: str
    beschreibung: str


class BausteineResponse(BaseModel):
    bausteine: list[BausteinItem]


@router.get("/bausteine", response_model=BausteineResponse)
async def get_bausteine(
    _: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
) -> BausteineResponse:
    """Bausteine hinter dem Prompt (0.26) — für die Auswahl im Editor."""
    return BausteineResponse(bausteine=bausteine_.liste())
