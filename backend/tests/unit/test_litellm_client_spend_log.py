import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.litellm.client import LiteLLMClient


@pytest.mark.asyncio
async def test_get_spend_log_returns_spend():
    """Response mit data[0]["spend"] = 0.001191 -> 0.001191"""
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "data": [{"spend": "0.001191", "request_id": "req-1"}]
    }
    http_client.get = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        result = await client.get_spend_log("req-1")

    assert result == 0.001191


@pytest.mark.asyncio
async def test_get_spend_log_fallback_to_cost_breakdown():
    """spend=0, metadata.cost_breakdown.total_cost=0.0016 -> 0.0016"""
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "data": [{
            "spend": 0,
            "metadata": {"cost_breakdown": {"total_cost": "0.0016"}}
        }]
    }
    http_client.get = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        result = await client.get_spend_log("req-2")

    assert result == 0.0016


@pytest.mark.asyncio
async def test_get_spend_log_empty_data():
    """{"data": [], "total": 0} -> None"""
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"data": [], "total": 0}
    http_client.get = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        result = await client.get_spend_log("req-3")

    assert result is None


@pytest.mark.asyncio
async def test_get_spend_log_non_200_status():
    """status=400 -> None (kein Raise)"""
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 400
    response.text = "Bad Request"
    http_client.get = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        result = await client.get_spend_log("req-4")

    assert result is None


@pytest.mark.asyncio
async def test_get_spend_log_exception_returns_none():
    """_get_client wirft Exception -> None"""
    client = LiteLLMClient()

    with patch.object(client, "_get_client", new=AsyncMock(side_effect=RuntimeError("Connection failed"))):
        result = await client.get_spend_log("req-5")

    assert result is None


@pytest.mark.asyncio
async def test_get_spend_log_sends_required_date_params():
    """Prueft start_date + end_date im Aufruf sind vorhanden und nicht leer"""
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"data": [{"spend": "0.001"}]}
    http_client.get = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        await client.get_spend_log("req-6")

    call_args = http_client.get.await_args
    assert call_args is not None
    params = call_args.kwargs.get("params", {})
    assert "start_date" in params
    assert "end_date" in params
    assert params["start_date"]  # nicht leer
    assert params["end_date"]  # nicht leer
    assert params["request_id"] == "req-6"
