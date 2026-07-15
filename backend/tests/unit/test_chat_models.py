import os
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.chat.router import chat, router as chat_router
from app.chat.schemas import ChatRequest
from app.litellm.client import LiteLLMClient
import app.chat.router as _chat_router_mod


@pytest.fixture(autouse=True)
def _reset_model_info_cache():
    _chat_router_mod._model_info_cache = None
    yield
    _chat_router_mod._model_info_cache = None


_FAKE_LITELLM_KEY = "sk-test-key"


def _make_execute_mock(*specific_results):
    """Returns an AsyncMock for db.execute that returns specific_results in order,
    then falls back to a generic MagicMock that includes a fake litellm key."""
    call_count = [0]

    def _side_effect(*args, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(specific_results):
            return specific_results[idx]
        generic = MagicMock()
        generic.scalars.return_value.all.return_value = []
        generic.scalars.return_value.first.return_value = None
        generic.scalar_one_or_none.return_value = _FAKE_LITELLM_KEY
        generic.fetchone.return_value = None
        return generic

    return AsyncMock(side_effect=_side_effect)


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
        client.get_team_info.return_value = {"models": ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"]}
        client.get_model_info.return_value = {}
        client.close.return_value = None
        client_cls.return_value = client

        test_client = TestClient(app)
        response = test_client.get("/models")

    assert response.status_code == 200
    model_ids = [m["id"] for m in response.json()["models"]]
    assert model_ids == ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"]
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


class _FakeStreamResponse:
    status_code = 200

    async def aiter_lines(self):
        yield "data: [DONE]"

    async def aclose(self):
        return None

    async def aread(self):
        return b""


class _FakeHttpClient:
    def __init__(self):
        self.last_json = None

    def build_request(self, method, url, headers=None, json=None):
        self.last_json = json
        return {"method": method, "url": url}

    async def send(self, request, stream=False):
        return _FakeStreamResponse()

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_post_chat_new_conversation_uses_requested_model_id():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    db.commit = AsyncMock()
    db.execute = _make_execute_mock()

    fake_http_client = _FakeHttpClient()
    request = ChatRequest(
        messages=[{"role": "user", "content": "Hallo"}],
        model_id="openai/gpt-4.1-mini",
    )

    with patch("app.chat.router.httpx.AsyncClient", return_value=fake_http_client), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "openai/gpt-4o-mini"
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3

        await chat(request, current_user=_fake_payload(), db=db)

    assert fake_http_client.last_json["model"] == "openai/gpt-4.1-mini"


@pytest.mark.asyncio
async def test_post_chat_new_conversation_without_model_uses_default():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = _make_execute_mock()
    db.flush = AsyncMock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    db.commit = AsyncMock()

    fake_http_client = _FakeHttpClient()
    request = ChatRequest(
        messages=[{"role": "user", "content": "Hallo"}],
        model_id=None,
    )

    with patch("app.chat.router.httpx.AsyncClient", return_value=fake_http_client), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "openai/gpt-4o-mini"
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3

        await chat(request, current_user=_fake_payload(), db=db)

    assert fake_http_client.last_json["model"] == "openai/gpt-4o-mini"


@pytest.mark.asyncio
async def test_post_chat_existing_conversation_without_model_uses_stored_model():
    """Wenn kein model_id übergeben, wird das gespeicherte Modell der Konversation verwendet."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()

    conversation_id = uuid4()
    existing_conv = MagicMock()
    existing_conv.id = conversation_id
    existing_conv.pseudonym = "pseudo-1"
    existing_conv.model_used = "openai/gpt-4o-mini"
    existing_conv.system_prompt_snapshot = None
    existing_conv.assistant_id = None

    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=existing_conv)

    # First call: Conversation lookup; subsequent calls use generic fallback (incl. key)
    db.execute = _make_execute_mock(result)
    db.add = MagicMock()

    fake_http_client = _FakeHttpClient()
    request = ChatRequest(
        messages=[{"role": "user", "content": "Weiter"}],
        conversation_id=conversation_id,
        model_id=None,
    )

    with patch("app.chat.router.httpx.AsyncClient", return_value=fake_http_client), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "openai/gpt-4o-mini"
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3

        await chat(request, current_user=_fake_payload(), db=db)

    assert fake_http_client.last_json["model"] == "openai/gpt-4o-mini"
