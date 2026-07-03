import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.litellm.client import LiteLLMClient
from app.litellm.teams import TEACHER_TEAM_ID, STUDENT_TEAM_PREFIX, VALID_GRADES
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_client = LiteLLMClient()


def phase1_team_ids() -> list[str]:
    """Feste Reihenfolge: jahrgang-5..12, dann lehrkraefte."""
    grades = sorted(VALID_GRADES)
    return [f"{STUDENT_TEAM_PREFIX}{g}" for g in grades] + [TEACHER_TEAM_ID]


class ModelMatrixResponse(BaseModel):
    models: list[str]  # alle Modell-IDs aus LiteLLM
    teams: list[str]  # Phase-1-Teams in fester Reihenfolge
    allowlists: dict[str, list[str]]  # team_id -> freigeschaltete Modell-IDs


class ModelMatrixUpdate(BaseModel):
    allowlists: dict[str, list[str]]  # gewünschter Zielzustand (vollständig)


router = APIRouter(prefix="/models", tags=["admin-models"])

_NO_DEFAULT = ["no-default-models"]


async def _fetch_matrix() -> ModelMatrixResponse:
    """Interne Hilfsfunktion: Fetcht die aktuelle Chat-Matrix aus LiteLLM.

    Bild-Modelle (``model_info.mode == "image_generation"``) werden ausgeblendet —
    sie laufen über die eigene Bild-Matrix (``/admin/image-models/matrix``), teilen
    sich aber dieselbe Team-Allowlist.
    """
    teams = phase1_team_ids()
    all_models, image_ids, team_infos = await asyncio.gather(
        _client.list_models(),
        _client.get_image_model_ids(),
        asyncio.gather(*[_client.get_team_info(t) for t in teams]),
    )
    image_set = set(image_ids)
    chat_models = [m for m in all_models if m not in image_set]
    allowlists = {}
    for team_id, info in zip(teams, team_infos):
        team_models = (info.get("models") if info else None) or []
        if team_models == _NO_DEFAULT:
            team_models = []
        allowlists[team_id] = [m for m in team_models if m not in image_set]
    return ModelMatrixResponse(models=chat_models, teams=teams, allowlists=allowlists)


@router.get("/matrix", response_model=ModelMatrixResponse)
async def get_model_matrix(
    _: JwtPayload = Depends(require_role("admin")),
) -> ModelMatrixResponse:
    """Liefert die aktuelle Modell-Freischaltungsmatrix für alle Phase-1-Teams."""
    return await _fetch_matrix()


@router.post("/matrix", response_model=ModelMatrixResponse)
async def save_model_matrix(
    update: ModelMatrixUpdate,
    _: JwtPayload = Depends(require_role("admin")),
) -> ModelMatrixResponse:
    """
    Speichert die Chat-Modell-Freischaltung für alle Phase-1-Teams.
    Nimmt den gewünschten Zielzustand entgegen und ruft update_team_models
    nur für bekannte Phase-1-Teams auf. Unbekannte Team-IDs werden ignoriert.

    **Merge mit der Bild-Matrix:** Beide Matrizen schreiben in dieselbe LiteLLM-
    Team-Allowlist. Damit das Speichern der Chat-Matrix die per Bild-Matrix erteilten
    Freigaben nicht wegwischt, werden die aktuell freigeschalteten Bild-Modelle des
    Teams gelesen und der neuen Chat-Auswahl beigefügt (statt sie zu ersetzen).
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
        existing_image = [m for m in current if m in image_set]  # Bild-Freigaben bewahren
        chat_models = [m for m in update.allowlists[team_id] if m not in image_set]
        merged = chat_models + existing_image
        updates[team_id] = merged if merged else _NO_DEFAULT

    await asyncio.gather(*[
        _client.update_team_models(team_id, models)
        for team_id, models in updates.items()
    ])
    # Aktualisierten Zustand zurückliefern
    return await _fetch_matrix()
