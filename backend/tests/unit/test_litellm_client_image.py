import base64
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.config import settings
from app.litellm.client import LiteLLMClient

_PNG = b"\x89PNG\r\n\x1a\n-fake-image-bytes"
_B64 = base64.b64encode(_PNG).decode()


def _mock_response(status_code=200, json_body=None, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body if json_body is not None else {}
    response.text = text
    return response


@pytest.mark.asyncio
async def test_generate_image_returns_decoded_bytes():
    """data[0].b64_json -> dekodierte Roh-Bytes."""
    client = LiteLLMClient()
    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=_mock_response(
        json_body={"data": [{"b64_json": _B64, "url": None}]}
    ))

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        result = await client.generate_image(
            "ein roter Würfel", model="gpt-image-1", api_key="sk-user", user="pseudo-1",
        )

    assert result == _PNG


@pytest.mark.asyncio
async def test_generate_image_uses_user_key_and_payload_shape():
    """Auth = User-Virtual-Key (nicht Master-Key); Payload trägt model/prompt/size/user/n/response_format."""
    client = LiteLLMClient()
    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=_mock_response(
        json_body={"data": [{"b64_json": _B64}]}
    ))

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        await client.generate_image(
            "ein Baum", model="gpt-image-1", api_key="sk-user-vkey", user="pseudo-42",
            size="1024x1024",
        )

    call = http_client.post.await_args
    # URL ohne /v1-Präfix (Konvention wie /chat/completions, /models)
    assert call.args[0].endswith("/images/generations")
    # Abrechnung über den User-Key, nicht den Master-Key
    assert call.kwargs["headers"]["Authorization"] == "Bearer sk-user-vkey"
    assert call.kwargs["headers"]["Authorization"] != f"Bearer {settings.litellm_master_key}"
    payload = call.kwargs["json"]
    assert payload["model"] == "gpt-image-1"
    assert payload["prompt"] == "ein Baum"
    assert payload["size"] == "1024x1024"
    assert payload["user"] == "pseudo-42"
    assert payload["n"] == 1
    assert payload["response_format"] == "b64_json"
    # Eigenes, großzügiges Timeout (nicht der 30s-Default des Clients)
    assert call.kwargs["timeout"] == settings.image_generation_timeout


@pytest.mark.asyncio
async def test_generate_image_size_defaults_from_settings():
    """Ohne size-Argument greift settings.image_default_size."""
    client = LiteLLMClient()
    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=_mock_response(
        json_body={"data": [{"b64_json": _B64}]}
    ))

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        await client.generate_image(
            "x", model="gpt-image-1", api_key="k", user="u",
        )

    assert http_client.post.await_args.kwargs["json"]["size"] == settings.image_default_size


@pytest.mark.asyncio
async def test_generate_image_response_format_none_omitted():
    """response_format=None -> Parameter wird NICHT gesendet (für gpt-image-1, das ihn ablehnt)."""
    client = LiteLLMClient()
    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=_mock_response(
        json_body={"data": [{"b64_json": _B64}]}
    ))

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        await client.generate_image(
            "x", model="gpt-image-1", api_key="k", user="u", response_format=None,
        )

    assert "response_format" not in http_client.post.await_args.kwargs["json"]


@pytest.mark.asyncio
async def test_generate_image_url_response_rejected():
    """Datenschutz: Provider liefert URL statt Base64 -> RuntimeError (keine externen URLs)."""
    client = LiteLLMClient()
    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=_mock_response(
        json_body={"data": [{"b64_json": None, "url": "https://provider.example/img.png"}]}
    ))

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        with pytest.raises(RuntimeError, match="external image URLs"):
            await client.generate_image("x", model="dall-e-3", api_key="k", user="u")


@pytest.mark.asyncio
async def test_generate_image_non_200_raises():
    """status != 200 -> RuntimeError."""
    client = LiteLLMClient()
    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=_mock_response(status_code=429, text="budget exceeded"))

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        with pytest.raises(RuntimeError, match="Failed to generate image"):
            await client.generate_image("x", model="gpt-image-1", api_key="k", user="u")


@pytest.mark.asyncio
async def test_generate_image_empty_data_raises():
    """Leere data-Liste -> RuntimeError."""
    client = LiteLLMClient()
    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=_mock_response(json_body={"data": []}))

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        with pytest.raises(RuntimeError, match="no data"):
            await client.generate_image("x", model="gpt-image-1", api_key="k", user="u")


@pytest.mark.asyncio
async def test_generate_image_missing_image_data_raises():
    """Weder b64_json noch url -> RuntimeError."""
    client = LiteLLMClient()
    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=_mock_response(
        json_body={"data": [{"revised_prompt": "..."}]}
    ))

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        with pytest.raises(RuntimeError, match="missing image data"):
            await client.generate_image("x", model="gpt-image-1", api_key="k", user="u")
