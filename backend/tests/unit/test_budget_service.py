from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.budget.service import (
    _build_response,
    _empty_budget,
    _usd_to_eur,
    get_budget_info,
)


# ========== Helfer-Funktionen Tests ==========


def test_usd_to_eur_with_valid_value():
    assert _usd_to_eur(2.75, 1.10) == 2.5
    assert _usd_to_eur(0.55, 1.10) == 0.5


def test_usd_to_eur_with_none():
    assert _usd_to_eur(None, 1.10) is None


def test_usd_to_eur_rounding():
    assert _usd_to_eur(1.00, 3.00) == 0.33
    assert _usd_to_eur(1.00, 2.00) == 0.5


def test_empty_budget():
    result = _empty_budget(1.10)
    assert result["max_budget_usd"] is None
    assert result["spend_usd"] is None
    assert result["remaining_usd"] is None
    assert result["budget_duration"] is None
    assert result["budget_reset_at"] is None
    assert result["max_budget_eur"] is None
    assert result["spend_eur"] is None
    assert result["remaining_eur"] is None
    assert result["eur_usd_rate"] == 1.10


def test_build_response_all_fields_present():
    user_info = {
        "max_budget": 2.75,
        "spend": 0.42,
        "budget_duration": "1mo",
        "budget_reset_at": "2026-05-01T00:00:00Z",
    }
    result = _build_response(user_info, 1.10)

    assert result["max_budget_usd"] == 2.75
    assert result["spend_usd"] == 0.42
    assert result["remaining_usd"] == 2.33
    assert result["budget_duration"] == "1mo"
    assert result["budget_reset_at"] == "2026-05-01T00:00:00Z"
    assert result["max_budget_eur"] == 2.5
    assert result["spend_eur"] == 0.38
    assert result["remaining_eur"] == 2.12
    assert result["eur_usd_rate"] == 1.10


def test_build_response_max_budget_null():
    user_info = {
        "max_budget": None,
        "spend": 0.42,
        "budget_duration": "1mo",
        "budget_reset_at": "2026-05-01T00:00:00Z",
    }
    result = _build_response(user_info, 1.10)

    assert result["max_budget_usd"] is None
    assert result["spend_usd"] == 0.42
    assert result["remaining_usd"] is None
    assert result["max_budget_eur"] is None
    assert result["spend_eur"] == 0.38
    assert result["remaining_eur"] is None


def test_build_response_spend_missing():
    user_info = {
        "max_budget": 2.75,
        "budget_duration": "1mo",
        "budget_reset_at": "2026-05-01T00:00:00Z",
    }
    result = _build_response(user_info, 1.10)

    assert result["max_budget_usd"] == 2.75
    assert result["spend_usd"] is None
    assert result["remaining_usd"] is None
    assert result["max_budget_eur"] == 2.5
    assert result["spend_eur"] is None
    assert result["remaining_eur"] is None


def test_build_response_all_fields_missing():
    user_info = {}
    result = _build_response(user_info, 1.10)

    assert result["max_budget_usd"] is None
    assert result["spend_usd"] is None
    assert result["remaining_usd"] is None
    assert result["budget_duration"] is None
    assert result["budget_reset_at"] is None
    assert result["max_budget_eur"] is None
    assert result["spend_eur"] is None
    assert result["remaining_eur"] is None
    assert result["eur_usd_rate"] == 1.10


# ========== get_budget_info Tests ==========


@pytest.mark.asyncio
async def test_get_budget_info_normal_case():
    """Test 1 — Normaler Fall: Alle Felder vorhanden"""
    db = AsyncMock()
    mock_client = AsyncMock()
    mock_client.get_user.return_value = {
        "user_id": "pseudo-xyz",
        "max_budget": 2.75,
        "spend": 0.42,
        "budget_duration": "1mo",
        "budget_reset_at": "2026-05-01T00:00:00Z",
    }

    with patch(
        "app.budget.service.get_current_rate", new=AsyncMock(return_value=1.10)
    ), patch("app.budget.service.LiteLLMClient", return_value=mock_client):
        result = await get_budget_info(db, "pseudo-xyz")

    assert result["max_budget_usd"] == 2.75
    assert result["spend_usd"] == 0.42
    assert result["remaining_usd"] == 2.33
    assert result["budget_duration"] == "1mo"
    assert result["budget_reset_at"] == "2026-05-01T00:00:00Z"
    assert result["max_budget_eur"] == 2.5
    assert result["spend_eur"] == 0.38
    assert result["remaining_eur"] == 2.12
    assert result["eur_usd_rate"] == 1.10
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_budget_info_user_not_in_litellm():
    """Test 2 — User nicht in LiteLLM (get_user -> None)"""
    db = AsyncMock()
    mock_client = AsyncMock()
    mock_client.get_user.return_value = None

    with patch(
        "app.budget.service.get_current_rate", new=AsyncMock(return_value=1.10)
    ), patch("app.budget.service.LiteLLMClient", return_value=mock_client):
        result = await get_budget_info(db, "pseudo-unknown")

    assert result["max_budget_usd"] is None
    assert result["spend_usd"] is None
    assert result["remaining_usd"] is None
    assert result["budget_duration"] is None
    assert result["budget_reset_at"] is None
    assert result["max_budget_eur"] is None
    assert result["spend_eur"] is None
    assert result["remaining_eur"] is None
    assert result["eur_usd_rate"] == 1.10
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_budget_info_max_budget_null():
    """Test 3 — max_budget ist null (kein Limit)"""
    db = AsyncMock()
    mock_client = AsyncMock()
    mock_client.get_user.return_value = {
        "max_budget": None,
        "spend": 0.42,
        "budget_duration": "1mo",
    }

    with patch(
        "app.budget.service.get_current_rate", new=AsyncMock(return_value=1.10)
    ), patch("app.budget.service.LiteLLMClient", return_value=mock_client):
        result = await get_budget_info(db, "pseudo-xyz")

    assert result["max_budget_usd"] is None
    assert result["spend_usd"] == 0.42
    assert result["remaining_usd"] is None
    assert result["max_budget_eur"] is None
    assert result["spend_eur"] == 0.38
    assert result["remaining_eur"] is None
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_budget_info_spend_missing():
    """Test 4 — spend fehlt im LiteLLM-Response"""
    db = AsyncMock()
    mock_client = AsyncMock()
    mock_client.get_user.return_value = {
        "max_budget": 2.75,
        "budget_duration": "1mo",
    }

    with patch(
        "app.budget.service.get_current_rate", new=AsyncMock(return_value=1.10)
    ), patch("app.budget.service.LiteLLMClient", return_value=mock_client):
        result = await get_budget_info(db, "pseudo-xyz")

    assert result["max_budget_usd"] == 2.75
    assert result["spend_usd"] is None
    assert result["remaining_usd"] is None
    assert result["max_budget_eur"] == 2.5
    assert result["spend_eur"] is None
    assert result["remaining_eur"] is None
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_budget_info_litellm_exception():
    """Test 5 — LiteLLM wirft Exception -> 503"""
    db = AsyncMock()
    mock_client = AsyncMock()
    mock_client.get_user.side_effect = RuntimeError("Connection failed")

    with patch(
        "app.budget.service.get_current_rate", new=AsyncMock(return_value=1.10)
    ), patch("app.budget.service.LiteLLMClient", return_value=mock_client):
        with pytest.raises(Exception) as exc_info:
            await get_budget_info(db, "pseudo-xyz")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Budget-Daten voruebergehend nicht verfuegbar"
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_budget_info_eur_conversion_specific_rate():
    """Test 6 — EUR-Umrechnung mit konkretem Kurs"""
    db = AsyncMock()
    mock_client = AsyncMock()
    mock_client.get_user.return_value = {
        "max_budget": 2.75,
        "spend": 0.55,
        "budget_duration": "1mo",
    }

    with patch(
        "app.budget.service.get_current_rate", new=AsyncMock(return_value=1.10)
    ), patch("app.budget.service.LiteLLMClient", return_value=mock_client):
        result = await get_budget_info(db, "pseudo-xyz")

    assert result["max_budget_eur"] == 2.5
    assert result["spend_eur"] == 0.5
    assert result["remaining_usd"] == 2.2
    assert result["remaining_eur"] == 2.0
