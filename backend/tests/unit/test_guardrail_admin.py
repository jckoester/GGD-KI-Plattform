"""
Tests für app.api.admin.guardrail
"""
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.models import SiteConfig
from app.db.session import get_db
from app.api.admin.guardrail import router


def _admin() -> JwtPayload:
    return JwtPayload(sub="p-admin", roles=["admin"], grade=None,
                      jti="j-1", iat=1, exp=9999999999)


def _teacher() -> JwtPayload:
    return JwtPayload(sub="p-teacher", roles=["teacher"], grade=None,
                      jti="j-2", iat=1, exp=9999999999)


def _make_app(payload: JwtPayload, mock_db) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    async def fake_user():
        return payload

    async def fake_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[get_db] = fake_db
    return app


def _db_with_row(row) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    session.execute.return_value = result
    return session


# ========== GET /prompt ==========


def test_get_guardrail_prompt_returns_prompt():
    """DB-Eintrag vorhanden → Prompt + Metadaten zurück."""
    row = MagicMock(spec=SiteConfig)
    row.value = "Sei stets altersgerecht."
    row.updated_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    row.updated_by = "p-admin"

    app = _make_app(_admin(), _db_with_row(row))
    response = TestClient(app).get("/guardrail/prompt")

    assert response.status_code == 200
    data = response.json()
    assert data["prompt"] == "Sei stets altersgerecht."
    assert data["updated_by"] == "p-admin"


def test_get_guardrail_prompt_returns_null_when_missing():
    """Kein DB-Eintrag → prompt: null."""
    app = _make_app(_admin(), _db_with_row(None))
    response = TestClient(app).get("/guardrail/prompt")

    assert response.status_code == 200
    assert response.json()["prompt"] is None


def test_get_guardrail_prompt_requires_admin():
    """Lehrkraft → 403."""
    app = _make_app(_teacher(), AsyncMock())
    response = TestClient(app).get("/guardrail/prompt")
    assert response.status_code == 403


# ========== PUT /prompt ==========


def test_put_guardrail_prompt_sets_new_prompt():
    """PUT mit Prompt → 200, Prompt wird zurückgegeben, Cache wird geleert."""
    import app.chat.router as chat_router
    chat_router._guardrail_prompt_cache = ("alter Wert", 9999999999.0)

    updated_row = MagicMock(spec=SiteConfig)
    updated_row.value = "Neuer Prompt"
    updated_row.updated_at = datetime(2026, 5, 21, tzinfo=timezone.utc)
    updated_row.updated_by = "p-admin"

    session = AsyncMock()
    result_after = MagicMock()
    result_after.scalar_one.return_value = updated_row
    session.execute.return_value = result_after
    session.commit = AsyncMock()

    app = _make_app(_admin(), session)
    response = TestClient(app).put("/guardrail/prompt", json={"prompt": "Neuer Prompt"})

    assert response.status_code == 200
    assert response.json()["prompt"] == "Neuer Prompt"
    assert chat_router._guardrail_prompt_cache is None


def test_put_guardrail_prompt_null_deactivates():
    """PUT mit prompt=null → 200, prompt: null."""
    updated_row = MagicMock(spec=SiteConfig)
    updated_row.value = None
    updated_row.updated_at = datetime(2026, 5, 21, tzinfo=timezone.utc)
    updated_row.updated_by = "p-admin"

    session = AsyncMock()
    result_after = MagicMock()
    result_after.scalar_one.return_value = updated_row
    session.execute.return_value = result_after
    session.commit = AsyncMock()

    app = _make_app(_admin(), session)
    response = TestClient(app).put("/guardrail/prompt", json={"prompt": None})

    assert response.status_code == 200
    assert response.json()["prompt"] is None


def test_put_guardrail_prompt_too_long_returns_422():
    """Prompt > 10 000 Zeichen → 422."""
    app = _make_app(_admin(), AsyncMock())
    response = TestClient(app).put("/guardrail/prompt", json={"prompt": "x" * 10_001})
    assert response.status_code == 422


def test_put_guardrail_prompt_requires_admin():
    """Lehrkraft → 403."""
    app = _make_app(_teacher(), AsyncMock())
    response = TestClient(app).put("/guardrail/prompt", json={"prompt": "Text"})
    assert response.status_code == 403


# ========== GET /litellm ==========


def test_get_litellm_guardrails_returns_list():
    """LiteLLM liefert zwei Guardrails → normalisierte Liste."""
    guardrails = [
        {"name": "pii-guard", "mode": "pre_call"},
        {"name": "violence-guard", "mode": "post_call"},
    ]
    app = _make_app(_admin(), AsyncMock())

    with patch("app.api.admin.guardrail._litellm") as mock_client:
        mock_client.list_guardrails = AsyncMock(return_value=guardrails)
        response = TestClient(app).get("/guardrail/litellm")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert len(data["guardrails"]) == 2
    assert data["guardrails"][0]["name"] == "pii-guard"
    assert data["guardrails"][0]["mode"] == "pre_call"


def test_get_litellm_guardrails_empty_when_none_configured():
    """LiteLLM liefert leere Liste → leere guardrails, available: True."""
    app = _make_app(_admin(), AsyncMock())

    with patch("app.api.admin.guardrail._litellm") as mock_client:
        mock_client.list_guardrails = AsyncMock(return_value=[])
        response = TestClient(app).get("/guardrail/litellm")

    assert response.status_code == 200
    assert response.json()["guardrails"] == []
    assert response.json()["available"] is True


def test_get_litellm_guardrails_requires_admin():
    """Lehrkraft → 403."""
    app = _make_app(_teacher(), AsyncMock())
    response = TestClient(app).get("/guardrail/litellm")
    assert response.status_code == 403
