import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.chat.router import router as chat_router
from app.chat.schemas import ChatRequest
from app.litellm.client import LiteLLMClient


def _fake_payload() -> JwtPayload:
    return JwtPayload(
        sub="pseudo-1",
        roles=["student"],
        grade="10",
        jti="jti-1",
        iat=1,
        exp=9999999999,
    )


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(chat_router)

    async def fake_current_user():
        return _fake_payload()

    app.dependency_overrides[get_current_user] = fake_current_user
    return app


def test_chat_request_model_id_is_normalized():
    request = ChatRequest(
        messages=[{"role": "user", "content": "Hallo"}],
        model_id="  openai/gpt-4o-mini  ",
    )
    assert request.model_id == "openai/gpt-4o-mini"

    empty_model = ChatRequest(
        messages=[{"role": "user", "content": "Hallo"}],
        model_id="   ",
    )
    assert empty_model.model_id is None


@pytest.mark.asyncio
async def test_litellm_list_models_parses_and_deduplicates():
    litellm_client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "data": [
            {"id": "openai/gpt-4o-mini"},
            {"model_name": "openai/gpt-4.1-mini"},
            {"id": "openai/gpt-4o-mini"},
        ]
    }
    http_client.get = AsyncMock(return_value=response)

    with patch.object(litellm_client, "_get_client", new=AsyncMock(return_value=http_client)):
        models = await litellm_client.list_models()

    assert models == ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"]


def test_get_models_success():
    app = _make_app()

    with patch("app.chat.router.LiteLLMClient") as client_cls:
        client = AsyncMock()
        client.list_models.return_value = ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"]
        client.close.return_value = None
        client_cls.return_value = client

        test_client = TestClient(app)
        response = test_client.get("/models")

    assert response.status_code == 200
    assert response.json()["models"] == [
        {"id": "openai/gpt-4o-mini"},
        {"id": "openai/gpt-4.1-mini"},
    ]
    assert "default_model" in response.json()


def test_get_models_returns_502_when_litellm_fails():
    app = _make_app()

    with patch("app.chat.router.LiteLLMClient") as client_cls:
        client = AsyncMock()
        client.list_models.side_effect = RuntimeError("boom")
        client.close.return_value = None
        client_cls.return_value = client

        test_client = TestClient(app)
        response = test_client.get("/models")

    assert response.status_code == 502
    assert response.json()["detail"] == "LiteLLM Proxy nicht erreichbar"
