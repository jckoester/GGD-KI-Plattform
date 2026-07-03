import asyncio
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.litellm.client import LiteLLMClient
from app.api.admin.models import phase1_team_ids

logger = logging.getLogger(__name__)

_client = LiteLLMClient()

_NO_DEFAULT = ["no-default-models"]


class ImageModelMatrixResponse(BaseModel):
    models: list[str]  # nur Bild-Modelle (model_info.mode == "image_generation")
    teams: list[str]  # Phase-1-Teams in fester Reihenfolge
    allowlists: dict[str, list[str]]  # team_id -> freigeschaltete Bild-Modell-IDs


class ImageModelMatrixUpdate(BaseModel):
    allowlists: dict[str, list[str]]  # gewünschter Zielzustand (nur Bild-Modelle)


router = APIRouter(prefix="/image-models", tags=["admin-image-models"])


async def _fetch_matrix() -> ImageModelMatrixResponse:
    """Fetcht die aktuelle Bild-Modell-Matrix aus LiteLLM.

    Spalten sind ausschließlich Bild-Modelle; die Allowlist je Team wird auf Bild-
    Modelle gefiltert (Chat-Modelle in derselben Allowlist bleiben unberührt).
    """
    teams = phase1_team_ids()
    image_ids, team_infos = await asyncio.gather(
        _client.get_image_model_ids(),
        asyncio.gather(*[_client.get_team_info(t) for t in teams]),
    )
    image_set = set(image_ids)
    allowlists = {}
    for team_id, info in zip(teams, team_infos):
        team_models = (info.get("models") if info else None) or []
        if team_models == _NO_DEFAULT:
            team_models = []
        allowlists[team_id] = [m for m in team_models if m in image_set]
    return ImageModelMatrixResponse(
        models=list(image_ids), teams=teams, allowlists=allowlists
    )


@router.get("/matrix", response_model=ImageModelMatrixResponse)
async def get_image_model_matrix(
    _: JwtPayload = Depends(require_role("admin")),
) -> ImageModelMatrixResponse:
    """Liefert die aktuelle Bild-Modell-Freischaltungsmatrix für alle Phase-1-Teams."""
    return await _fetch_matrix()


@router.post("/matrix", response_model=ImageModelMatrixResponse)
async def save_image_model_matrix(
    update: ImageModelMatrixUpdate,
    _: JwtPayload = Depends(require_role("admin")),
) -> ImageModelMatrixResponse:
    """
    Speichert die Bild-Modell-Freischaltung für alle Phase-1-Teams.

    **Merge mit der Chat-Matrix:** Beide Matrizen schreiben in dieselbe LiteLLM-Team-
    Allowlist. Beim Speichern werden die aktuell freigeschalteten Chat-Modelle des
    Teams gelesen und der neuen Bild-Auswahl beigefügt (statt sie zu ersetzen).
    Unbekannte Team-IDs und Nicht-Bild-Modelle in der Eingabe werden ignoriert.
    """
    valid_teams = set(phase1_team_ids())
    teams_to_update = [t for t in update.allowlists if t in valid_teams]

    image_set = set(await _client.get_image_model_ids())
    team_infos = await asyncio.gather(
        *[_client.get_team_info(t) for t in teams_to_update]
    )

    updates: dict[str, list[str]] = {}
    for team_id, info in zip(teams_to_update, team_infos):
        current = (info.get("models") if info else None) or []
        if current == _NO_DEFAULT:
            current = []
        chat_models = [m for m in current if m not in image_set]  # Chat-Freigaben bewahren
        desired_image = [m for m in update.allowlists[team_id] if m in image_set]
        merged = chat_models + desired_image
        updates[team_id] = merged if merged else _NO_DEFAULT

    await asyncio.gather(*[
        _client.update_team_models(team_id, models)
        for team_id, models in updates.items()
    ])
    return await _fetch_matrix()
