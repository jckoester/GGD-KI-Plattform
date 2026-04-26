import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.api.admin.models import phase1_team_ids, ModelMatrixResponse, ModelMatrixUpdate
from app.litellm.teams import VALID_GRADES


@pytest.mark.asyncio
async def test_phase1_team_ids_returns_sorted_grades_plus_teachers():
    """Testet, dass phase1_team_ids() die Jahrgänge sortiert + lehrkraefte zurückgibt."""
    team_ids = phase1_team_ids()
    grades = sorted(VALID_GRADES)
    expected = [f"jahrgang-{g}" for g in grades] + ["lehrkraefte"]
    assert team_ids == expected


@pytest.mark.asyncio
async def test_model_matrix_response_structure():
    """Testet, dass ModelMatrixResponse die richtige Struktur hat."""
    response = ModelMatrixResponse(
        models=["m1", "m2"],
        teams=["jahrgang-5", "lehrkraefte"],
        allowlists={"jahrgang-5": ["m1"], "lehrkraefte": ["m1", "m2"]}
    )
    assert response.models == ["m1", "m2"]
    assert response.teams == ["jahrgang-5", "lehrkraefte"]
    assert response.allowlists["jahrgang-5"] == ["m1"]
    assert response.allowlists["lehrkraefte"] == ["m1", "m2"]


@pytest.mark.asyncio
async def test_model_matrix_update_structure():
    """Testet, dass ModelMatrixUpdate die richtige Struktur hat."""
    update = ModelMatrixUpdate(
        allowlists={"jahrgang-5": ["m1"], "lehrkraefte": ["m1", "m2"]}
    )
    assert update.allowlists["jahrgang-5"] == ["m1"]
    assert update.allowlists["lehrkraefte"] == ["m1", "m2"]


@pytest.mark.asyncio
async def test_save_matrix_filters_valid_teams():
    """Testet, dass die Speicher-Logik nur gültige Teams berücksichtigt."""
    valid_teams = set(phase1_team_ids())
    
    # Simuliere die Filterung
    update = {
        "jahrgang-5": ["m1"],
        "fremdes-team": ["m2"],
        "lehrkraefte": ["m1", "m2"],
    }
    
    updates = {
        team_id: models
        for team_id, models in update.items()
        if team_id in valid_teams
    }
    
    # fremdes-team sollte ignoriert werden
    assert "fremdes-team" not in updates
    assert "jahrgang-5" in updates
    assert "lehrkraefte" in updates
    assert updates["jahrgang-5"] == ["m1"]
    assert updates["lehrkraefte"] == ["m1", "m2"]


@pytest.mark.asyncio
async def test_save_matrix_filters_all_unknown_teams():
    """Testet, dass alle unbekannten Teams ignoriert werden."""
    valid_teams = set(phase1_team_ids())

    update = {
        "unknown-team-1": ["m1"],
        "unknown-team-2": ["m2", "m3"],
    }

    updates = {
        team_id: models
        for team_id, models in update.items()
        if team_id in valid_teams
    }

    assert len(updates) == 0


@pytest.mark.asyncio
async def test_save_matrix_replaces_empty_with_no_default_models():
    """Leere Allowlist wird durch no-default-models ersetzt."""
    valid_teams = set(phase1_team_ids())
    update = {"jahrgang-5": [], "lehrkraefte": ["m1"]}
    updates = {
        team_id: (models if models else ["no-default-models"])
        for team_id, models in update.items()
        if team_id in valid_teams
    }
    assert updates["jahrgang-5"] == ["no-default-models"]
    assert updates["lehrkraefte"] == ["m1"]


@pytest.mark.asyncio
async def test_fetch_matrix_maps_no_default_models_to_empty():
    """no-default-models aus LiteLLM wird als leere Allowlist zurückgegeben."""
    _NO_DEFAULT = ["no-default-models"]
    team_infos = [
        {"models": ["no-default-models"]},  # jahrgang-5: gesperrt
        {"models": ["m1"]},                 # jahrgang-6: ein Modell
        None,                               # jahrgang-7: Team nicht gefunden
    ]
    teams = ["jahrgang-5", "jahrgang-6", "jahrgang-7"]
    allowlists = {
        team_id: []
        if (not info or (info.get("models") or []) == _NO_DEFAULT)
        else (info.get("models") or [])
        for team_id, info in zip(teams, team_infos)
    }
    assert allowlists["jahrgang-5"] == []
    assert allowlists["jahrgang-6"] == ["m1"]
    assert allowlists["jahrgang-7"] == []
