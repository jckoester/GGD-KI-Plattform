import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.litellm.client import LiteLLMClient
from app.api.admin import image_models as im
from app.api.admin import models as cm


def _mock_response(status_code=200, json_body=None, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body if json_body is not None else {}
    response.text = text
    return response


# ========== Client: Bild-Modell-Klassifizierung ==========


@pytest.mark.asyncio
async def test_get_image_model_ids_filters_by_mode():
    """Nur Modelle mit model_info.mode == 'image_generation' werden zurückgegeben."""
    client = LiteLLMClient()
    http_client = AsyncMock()
    http_client.get = AsyncMock(return_value=_mock_response(json_body={"data": [
        {"model_name": "gpt-4o-mini", "model_info": {"mode": "chat"}},
        {"model_name": "gpt-image-1", "model_info": {"mode": "image_generation"}},
        {"model_name": "gpt-image-1.5", "model_info": {"mode": "image_generation"}},
        {"model_name": "ollama-fallback", "model_info": {}},
    ]}))
    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        ids = await client.get_image_model_ids()
    assert ids == ["gpt-image-1", "gpt-image-1.5"]


@pytest.mark.asyncio
async def test_get_image_model_ids_empty_on_error():
    """Nicht-200 → leere Liste (kein Hard-Fail, saubere Degradierung)."""
    client = LiteLLMClient()
    http_client = AsyncMock()
    http_client.get = AsyncMock(return_value=_mock_response(status_code=500, text="boom"))
    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        ids = await client.get_image_model_ids()
    assert ids == []


# ========== Bild-Matrix: GET filtert auf Bild-Modelle ==========


@pytest.mark.asyncio
async def test_image_matrix_fetch_shows_only_image_models():
    """Spalten = Bild-Modelle; Allowlist je Team auf Bild-Modelle gefiltert."""
    mock = AsyncMock()
    mock.get_image_model_ids.return_value = ["gpt-image-1"]
    # Team-Allowlist enthält Chat- + Bild-Modell gemischt
    mock.get_team_info.return_value = {"models": ["gpt-4o-mini", "gpt-image-1"]}
    with patch.object(im, "_client", mock):
        result = await im._fetch_matrix()
    assert result.models == ["gpt-image-1"]
    for team in result.teams:
        assert result.allowlists[team] == ["gpt-image-1"]  # Chat-Modell ausgeblendet


@pytest.mark.asyncio
async def test_image_matrix_fetch_empty_when_no_image_models():
    """Keine Bild-Modelle konfiguriert → leere Matrix, keine Allowlist-Einträge."""
    mock = AsyncMock()
    mock.get_image_model_ids.return_value = []
    mock.get_team_info.return_value = {"models": ["gpt-4o-mini"]}
    with patch.object(im, "_client", mock):
        result = await im._fetch_matrix()
    assert result.models == []
    assert all(v == [] for v in result.allowlists.values())


# ========== Bild-Matrix: POST merged, ohne Chat-Freigaben zu verlieren ==========


@pytest.mark.asyncio
async def test_image_matrix_save_preserves_chat_models():
    """Speichern der Bild-Matrix erhält die Chat-Modelle des Teams (Merge)."""
    mock = AsyncMock()
    mock.get_image_model_ids.return_value = ["gpt-image-1", "gpt-image-1.5"]
    # Team hat aktuell ein Chat-Modell + ein Bild-Modell
    mock.get_team_info.return_value = {"models": ["gpt-4o-mini", "gpt-image-1"]}
    mock.update_team_models.return_value = None
    update = im.ImageModelMatrixUpdate(allowlists={"lehrkraefte": ["gpt-image-1.5"]})
    with patch.object(im, "_client", mock):
        await im.save_image_model_matrix(update, _=None)

    # update_team_models für lehrkraefte mit gemergter Liste aufgerufen
    calls = [c for c in mock.update_team_models.call_args_list if c.args[0] == "lehrkraefte"]
    assert len(calls) == 1
    written = calls[0].args[1]
    assert "gpt-4o-mini" in written        # Chat-Modell bewahrt
    assert "gpt-image-1.5" in written      # neue Bild-Auswahl gesetzt
    assert "gpt-image-1" not in written    # abgewähltes Bild-Modell entfernt


@pytest.mark.asyncio
async def test_image_matrix_save_ignores_unknown_teams_and_non_image_models():
    """Unbekannte Teams + Nicht-Bild-Modelle in der Eingabe werden ignoriert."""
    mock = AsyncMock()
    mock.get_image_model_ids.return_value = ["gpt-image-1"]
    mock.get_team_info.return_value = {"models": ["no-default-models"]}
    mock.update_team_models.return_value = None
    update = im.ImageModelMatrixUpdate(allowlists={
        "fremdes-team": ["gpt-image-1"],       # unbekannt → ignoriert
        "lehrkraefte": ["gpt-4o-mini"],        # kein Bild-Modell → ignoriert
    })
    with patch.object(im, "_client", mock):
        await im.save_image_model_matrix(update, _=None)

    updated_teams = {c.args[0] for c in mock.update_team_models.call_args_list}
    assert "fremdes-team" not in updated_teams
    # lehrkraefte: leerer Merge → no-default-models Sentinel
    lk = [c for c in mock.update_team_models.call_args_list if c.args[0] == "lehrkraefte"]
    assert lk and lk[0].args[1] == ["no-default-models"]


# ========== Chat-Matrix: blendet Bild-Modelle aus + Merge bewahrt sie ==========


@pytest.mark.asyncio
async def test_chat_matrix_fetch_excludes_image_models():
    """Die bestehende Chat-Matrix zeigt Bild-Modelle nicht mehr an."""
    mock = AsyncMock()
    mock.list_models.return_value = ["gpt-4o-mini", "gpt-4o", "gpt-image-1"]
    mock.get_image_model_ids.return_value = ["gpt-image-1"]
    mock.get_team_info.return_value = {"models": ["gpt-4o-mini", "gpt-image-1"]}
    with patch.object(cm, "_client", mock):
        result = await cm._fetch_matrix()
    assert "gpt-image-1" not in result.models
    assert set(result.models) == {"gpt-4o-mini", "gpt-4o"}
    for team in result.teams:
        assert "gpt-image-1" not in result.allowlists[team]


@pytest.mark.asyncio
async def test_chat_matrix_save_preserves_image_models():
    """Speichern der Chat-Matrix wischt die Bild-Freigaben des Teams nicht weg."""
    mock = AsyncMock()
    mock.list_models.return_value = ["gpt-4o-mini", "gpt-4o", "gpt-image-1"]
    mock.get_image_model_ids.return_value = ["gpt-image-1"]
    mock.get_team_info.return_value = {"models": ["gpt-4o-mini", "gpt-image-1"]}
    mock.update_team_models.return_value = None
    update = cm.ModelMatrixUpdate(allowlists={"lehrkraefte": ["gpt-4o"]})
    with patch.object(cm, "_client", mock):
        await cm.save_model_matrix(update, _=None)

    calls = [c for c in mock.update_team_models.call_args_list if c.args[0] == "lehrkraefte"]
    assert len(calls) == 1
    written = calls[0].args[1]
    assert "gpt-4o" in written             # neue Chat-Auswahl
    assert "gpt-image-1" in written        # Bild-Freigabe bewahrt
    assert "gpt-4o-mini" not in written    # abgewähltes Chat-Modell entfernt
