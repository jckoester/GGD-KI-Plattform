import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("STUDENT_GRADES", "[5,6,7,8,9,10,11,12,13]")

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.chat.router import router as chat_router
from app.litellm.client import LiteLLMClient


def _fake_student_payload(grade: int = 10) -> JwtPayload:
    return JwtPayload(
        sub="pseudo-1",
        roles=["student"],
        grade=str(grade),
        jti="jti-1",
        iat=1,
        exp=9999999999,
    )


def _fake_teacher_payload() -> JwtPayload:
    return JwtPayload(
        sub="pseudo-1",
        roles=["teacher"],
        grade=None,
        jti="jti-1",
        iat=1,
        exp=9999999999,
    )


def _fake_admin_payload() -> JwtPayload:
    return JwtPayload(
        sub="pseudo-1",
        roles=["admin"],
        grade=None,
        jti="jti-1",
        iat=1,
        exp=9999999999,
    )


def _make_app(current_user_payload: JwtPayload) -> FastAPI:
    app = FastAPI()
    app.include_router(chat_router)

    async def fake_current_user():
        return current_user_payload

    app.dependency_overrides[get_current_user] = fake_current_user
    return app


@pytest.mark.asyncio
async def test_list_models_filters_by_team_allowlist():
    """Test: Nur Modelle in der Team-Allowlist werden zurückgegeben."""
    app = _make_app(_fake_student_payload(grade=10))

    with patch("app.chat.router.LiteLLMClient") as client_cls:
        client = AsyncMock()
        client.list_models.return_value = ["gpt-4o-mini", "gpt-4o"]
        client.get_team_info.return_value = {"models": ["gpt-4o-mini"]}
        client.close.return_value = None
        client_cls.return_value = client

        test_client = TestClient(app)
        response = test_client.get("/models")

    assert response.status_code == 200
    model_ids = [m["id"] for m in response.json()["models"]]
    assert model_ids == ["gpt-4o-mini"]


@pytest.mark.asyncio
async def test_list_models_returns_empty_for_no_default_models():
    """Test: Bei 'no-default-models' wird leere Liste zurückgegeben."""
    app = _make_app(_fake_student_payload(grade=10))

    with patch("app.chat.router.LiteLLMClient") as client_cls:
        client = AsyncMock()
        client.list_models.return_value = ["gpt-4o-mini", "gpt-4o"]
        client.get_team_info.return_value = {"models": ["no-default-models"]}
        client.close.return_value = None
        client_cls.return_value = client

        test_client = TestClient(app)
        response = test_client.get("/models")

    assert response.status_code == 200
    assert response.json()["models"] == []


@pytest.mark.asyncio
async def test_list_models_returns_empty_for_empty_allowlist():
    """Test: Bei leerer Allowlist wird leere Liste zurückgegeben."""
    app = _make_app(_fake_student_payload(grade=10))

    with patch("app.chat.router.LiteLLMClient") as client_cls:
        client = AsyncMock()
        client.list_models.return_value = ["gpt-4o-mini", "gpt-4o"]
        client.get_team_info.return_value = {"models": []}
        client.close.return_value = None
        client_cls.return_value = client

        test_client = TestClient(app)
        response = test_client.get("/models")

    assert response.status_code == 200
    assert response.json()["models"] == []


@pytest.mark.asyncio
async def test_list_models_returns_all_for_admin():
    """Test: Admin erhält alle Modelle (kein Filter)."""
    app = _make_app(_fake_admin_payload())

    with patch("app.chat.router.LiteLLMClient") as client_cls:
        client = AsyncMock()
        client.list_models.return_value = ["gpt-4o-mini", "gpt-4o", "gpt-4"]
        client.close.return_value = None
        client_cls.return_value = client

        test_client = TestClient(app)
        response = test_client.get("/models")

    assert response.status_code == 200
    model_ids = [m["id"] for m in response.json()["models"]]
    assert model_ids == ["gpt-4o-mini", "gpt-4o", "gpt-4"]


@pytest.mark.asyncio
async def test_list_models_returns_all_for_teacher():
    """Test: Teacher erhält alle Modelle aus seiner Team-Allowlist."""
    app = _make_app(_fake_teacher_payload())

    with patch("app.chat.router.LiteLLMClient") as client_cls:
        client = AsyncMock()
        client.list_models.return_value = ["gpt-4o-mini", "gpt-4o"]
        client.get_team_info.return_value = {"models": ["gpt-4o-mini", "gpt-4o"]}
        client.close.return_value = None
        client_cls.return_value = client

        test_client = TestClient(app)
        response = test_client.get("/models")

    assert response.status_code == 200
    model_ids = [m["id"] for m in response.json()["models"]]
    assert model_ids == ["gpt-4o-mini", "gpt-4o"]


@pytest.mark.asyncio
async def test_list_models_fallback_on_litellm_error():
    """Test: Bei LiteLLM-Fehler werden alle Modelle zurückgegeben (kein Hard-Fail)."""
    app = _make_app(_fake_student_payload(grade=10))

    with patch("app.chat.router.LiteLLMClient") as client_cls:
        client = AsyncMock()
        client.list_models.return_value = ["gpt-4o-mini", "gpt-4o"]
        client.get_team_info.side_effect = RuntimeError("Connection failed")
        client.close.return_value = None
        client_cls.return_value = client

        test_client = TestClient(app)
        response = test_client.get("/models")

    assert response.status_code == 200
    model_ids = [m["id"] for m in response.json()["models"]]
    assert model_ids == ["gpt-4o-mini", "gpt-4o"]


@pytest.mark.asyncio
async def test_list_models_fallback_on_missing_team_info():
    """Test: Bei fehlendem Team-Info (None) werden alle Modelle zurückgegeben."""
    app = _make_app(_fake_student_payload(grade=10))

    with patch("app.chat.router.LiteLLMClient") as client_cls:
        client = AsyncMock()
        client.list_models.return_value = ["gpt-4o-mini", "gpt-4o"]
        client.get_team_info.return_value = None
        client.close.return_value = None
        client_cls.return_value = client

        test_client = TestClient(app)
        response = test_client.get("/models")

    assert response.status_code == 200
    model_ids = [m["id"] for m in response.json()["models"]]
    assert model_ids == ["gpt-4o-mini", "gpt-4o"]


@pytest.mark.asyncio
async def test_list_models_preserves_default_model():
    """Test: Das default_model Feld wird immer gesetzt."""
    app = _make_app(_fake_admin_payload())

    with patch("app.chat.router.LiteLLMClient") as client_cls, \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "openai/gpt-4o-mini"
        client = AsyncMock()
        client.list_models.return_value = []
        client.close.return_value = None
        client_cls.return_value = client

        test_client = TestClient(app)
        response = test_client.get("/models")

    assert response.status_code == 200
    assert response.json()["default_model"] == "openai/gpt-4o-mini"
