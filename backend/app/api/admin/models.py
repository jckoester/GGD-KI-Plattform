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


async def _fetch_matrix() -> ModelMatrixResponse:
    """Interne Hilfsfunktion: Fetcht die aktuelle Matrix aus LiteLLM."""
    teams = phase1_team_ids()
    models, team_infos = await asyncio.gather(
        _client.list_models(),
        asyncio.gather(*[_client.get_team_info(t) for t in teams]),
    )
    _NO_DEFAULT = ["no-default-models"]
    allowlists = {
        team_id: []
        if (not info or (info.get("models") or []) == _NO_DEFAULT)
        else (info.get("models") or [])
        for team_id, info in zip(teams, team_infos)
    }
    return ModelMatrixResponse(models=models, teams=teams, allowlists=allowlists)


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
    Speichert die Modell-Freischaltung für alle Phase-1-Teams.
    Nimmt den gewünschten Zielzustand entgegen und ruft update_team_models
    nur für bekannte Phase-1-Teams auf. Unbekannte Team-IDs werden ignoriert.
    """
    valid_teams = set(phase1_team_ids())
    updates = {
        team_id: (models if models else ["no-default-models"])
        for team_id, models in update.allowlists.items()
        if team_id in valid_teams
    }
    await asyncio.gather(*[
        _client.update_team_models(team_id, models)
        for team_id, models in updates.items()
    ])
    # Aktualisierten Zustand zurückliefern
    return await _fetch_matrix()
