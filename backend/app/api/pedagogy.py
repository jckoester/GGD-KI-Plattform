"""Pädagogik-Konfiguration für die UI (Phase 13).

Liefert die verfügbaren Lernverhalten-Augmentierungen (Key + Label) für die
Checkbox-Liste im Assistenten-Editor. Read-only; die Texte selbst liegen in
``pedagogy.yaml`` und werden nur im Backend beim System-Prompt-Aufbau verwendet.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import require_any_role
from app.auth.jwt import JwtPayload
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
