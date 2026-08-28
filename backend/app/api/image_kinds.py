"""Bildarten für den Assistenten-Editor (Mehrmodell-Plan, Schritt 4).

Liefert die konfigurierten Bildarten samt der Frage, für **welche Jahrgänge das jeweilige
Bildmodell überhaupt freigeschaltet ist**. Damit kann der Editor warnen, bevor gespeichert
wird — dorthin gehört das Problem: Ein Admin kann eine Freigabe setzen, eine Schülerin
kann es nicht, und zur Laufzeit bliebe nur eine Fehlermeldung.

Read-only. Die Bildarten selbst stehen in ``config/image_models.yaml``, die Freigabe je
Team im LiteLLM-Proxy.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.admin.models import phase1_team_ids
from app.auth.dependencies import require_any_role
from app.auth.jwt import JwtPayload
from app.chat.image_models import alle_bildarten, load_image_models
from app.litellm.client import LiteLLMClient
from app.litellm.teams import STUDENT_TEAM_PREFIX, TEACHER_TEAM_ID

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/image-kinds", tags=["image-kinds"])

_client = LiteLLMClient()

_NO_DEFAULT = ["no-default-models"]


class ImageKindItem(BaseModel):
    id: str
    label: str
    beschreibung: str
    modell: str
    formate: list[str]
    # Jahrgänge, für die das Modell dieser Bildart **nicht** freigeschaltet ist.
    fehlt_fuer_jahrgaenge: list[int] = []
    # Dasselbe für das Lehrkräfte-Team.
    fehlt_fuer_lehrkraefte: bool = False


class ImageKindsResponse(BaseModel):
    bildarten: list[ImageKindItem]
    standard_bildart: str
    # False, wenn der Proxy nicht erreichbar war. Dann sind die `fehlt_fuer_*`-Angaben
    # bedeutungslos und die Oberfläche darf **nicht** warnen: Eine Falschwarnung, die bei
    # jedem Speichern erscheint, wird binnen einer Woche weggeklickt — und mit ihr die
    # echten. Lieber keine Auskunft als eine erfundene.
    freigabe_bekannt: bool = True


async def _freigaben() -> tuple[dict[str, set[str]], bool]:
    """team_id → freigeschaltete Modelle, plus ob die Auskunft überhaupt zustande kam."""
    teams = phase1_team_ids()
    try:
        infos = await asyncio.gather(
            *[_client.get_team_info(t) for t in teams], return_exceptions=True
        )
    except Exception:
        logger.exception("Team-Freigaben nicht abrufbar")
        return {}, False

    freigaben: dict[str, set[str]] = {}
    erreichbar = False
    for team_id, info in zip(teams, infos):
        if isinstance(info, Exception) or info is None:
            # Ein unbekanntes Team (404) oder ein Fehler: Über dieses Team wissen wir
            # nichts. Es als „nichts freigeschaltet" zu werten, erzeugte Falschwarnungen.
            continue
        erreichbar = True
        modelle = info.get("models") or []
        if modelle == _NO_DEFAULT:
            modelle = []
        freigaben[team_id] = set(modelle)
    return freigaben, erreichbar


@router.get("", response_model=ImageKindsResponse)
async def get_image_kinds(
    _: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
) -> ImageKindsResponse:
    """Konfigurierte Bildarten + für welche Jahrgänge ihr Modell fehlt."""
    bildarten = alle_bildarten()
    freigaben, bekannt = await _freigaben()

    items: list[ImageKindItem] = []
    for b in bildarten:
        fehlt_jahrgaenge: list[int] = []
        fehlt_lehrkraefte = False
        if bekannt:
            for team_id, modelle in freigaben.items():
                if b.modell in modelle:
                    continue
                if team_id == TEACHER_TEAM_ID:
                    fehlt_lehrkraefte = True
                elif team_id.startswith(STUDENT_TEAM_PREFIX):
                    rest = team_id[len(STUDENT_TEAM_PREFIX):]
                    if rest.isdigit():
                        fehlt_jahrgaenge.append(int(rest))
        items.append(
            ImageKindItem(
                id=b.id,
                label=b.label,
                beschreibung=" ".join(b.beschreibung.split()),
                modell=b.modell,
                formate=list(b.formate),
                fehlt_fuer_jahrgaenge=sorted(fehlt_jahrgaenge),
                fehlt_fuer_lehrkraefte=fehlt_lehrkraefte,
            )
        )

    return ImageKindsResponse(
        bildarten=items,
        standard_bildart=load_image_models().standard_bildart,
        freigabe_bekannt=bekannt,
    )
