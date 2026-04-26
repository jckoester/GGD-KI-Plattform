import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.litellm.client import LiteLLMClient


@pytest.mark.asyncio
async def test_delete_user_accepts_404_as_success():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 404
    response.text = "not found"
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        await client.delete_user("pseudo-1")


@pytest.mark.asyncio
async def test_delete_user_raises_on_unexpected_status():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 500
    response.text = "internal error"
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        with pytest.raises(RuntimeError):
            await client.delete_user("pseudo-1")


@pytest.mark.asyncio
async def test_delete_user_calls_expected_endpoint():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 204
    response.text = ""
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        await client.delete_user("pseudo-abc")

    call_args = http_client.post.await_args
    assert call_args is not None
    assert call_args.args[0].endswith("/user/delete")
    assert call_args.kwargs["json"] == {"user_ids": ["pseudo-abc"]}


@pytest.mark.asyncio
async def test_list_teams_parses_data_shape():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"data": [{"team_alias": "jahrgang-7"}]}
    http_client.get = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        teams = await client.list_teams()

    assert teams == [{"team_alias": "jahrgang-7"}]


@pytest.mark.asyncio
async def test_add_team_member_calls_expected_endpoint_and_payload():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.text = ""
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        await client.add_team_member("jahrgang-8", "pseudo-a")

    call_args = http_client.post.await_args
    assert call_args.args[0].endswith("/team/member_add")
    assert call_args.kwargs["json"] == {
        "team_id": "jahrgang-8",
        "member": {"role": "user", "user_id": "pseudo-a"},
    }


@pytest.mark.asyncio
async def test_remove_team_member_calls_expected_endpoint_and_payload():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.text = ""
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        await client.remove_team_member("lehrkraefte", "pseudo-b")

    call_args = http_client.post.await_args
    assert call_args.args[0].endswith("/team/member_delete")
    assert call_args.kwargs["json"] == {
        "team_id": "lehrkraefte",
        "user_id": "pseudo-b",
    }


@pytest.mark.asyncio
async def test_add_team_member_raises_on_unexpected_status():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 500
    response.text = "error"
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        with pytest.raises(RuntimeError):
            await client.add_team_member("jahrgang-9", "pseudo-c")


@pytest.mark.asyncio
async def test_create_team_calls_expected_endpoint_and_payload():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.text = ""
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        await client.create_team("jahrgang-7")

    call_args = http_client.post.await_args
    assert call_args is not None
    assert call_args.args[0].endswith("/team/new")
    assert call_args.kwargs["json"] == {
        "team_id": "jahrgang-7",
        "team_alias": "jahrgang-7",
    }


@pytest.mark.asyncio
async def test_create_team_accepts_201_as_success():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 201
    response.text = ""
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        await client.create_team("jahrgang-8")


@pytest.mark.asyncio
async def test_create_team_accepts_409_as_success_idempotent():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 409
    response.text = "already exists"
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        await client.create_team("jahrgang-8")


@pytest.mark.asyncio
async def test_create_team_raises_on_unexpected_status():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 500
    response.text = "internal error"
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        with pytest.raises(RuntimeError):
            await client.create_team("jahrgang-8")


@pytest.mark.asyncio
async def test_generate_key_returns_key_string():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"key": "sk-abc123"}
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        key = await client.generate_key("pseudo-1")

    assert key == "sk-abc123"
    call_args = http_client.post.await_args
    assert call_args.args[0].endswith("/key/generate")
    assert call_args.kwargs["json"] == {"user_id": "pseudo-1"}


@pytest.mark.asyncio
async def test_generate_key_raises_on_error():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 500
    response.text = "internal error"
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        with pytest.raises(RuntimeError):
            await client.generate_key("pseudo-1")


@pytest.mark.asyncio
async def test_delete_key_accepts_404_as_success():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 404
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        await client.delete_key("sk-abc123")

    call_args = http_client.post.await_args
    assert call_args.args[0].endswith("/key/delete")
    assert call_args.kwargs["json"] == {"keys": ["sk-abc123"]}


@pytest.mark.asyncio
async def test_delete_key_raises_on_unexpected_status():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 500
    response.text = "error"
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        with pytest.raises(RuntimeError):
            await client.delete_key("sk-abc123")


@pytest.mark.asyncio
async def test_get_team_info_returns_models():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"team_id": "jahrgang-5", "models": ["gpt-4o-mini"]}
    http_client.get = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        result = await client.get_team_info("jahrgang-5")

    assert result == {"team_id": "jahrgang-5", "models": ["gpt-4o-mini"]}
    call_args = http_client.get.await_args
    assert call_args.args[0].endswith("/team/info")
    assert call_args.kwargs["params"]["team_id"] == "jahrgang-5"


@pytest.mark.asyncio
async def test_get_team_info_returns_none_on_404():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 404
    response.text = "not found"
    http_client.get = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        result = await client.get_team_info("nonexistent-team")

    assert result is None


@pytest.mark.asyncio
async def test_get_team_info_returns_empty_list_for_missing_models_field():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"team_id": "jahrgang-5"}
    http_client.get = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        result = await client.get_team_info("jahrgang-5")

    assert result == {"team_id": "jahrgang-5"}


@pytest.mark.asyncio
async def test_update_team_models_calls_correct_payload():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.text = ""
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        await client.update_team_models("jahrgang-7", ["gpt-4o-mini", "gpt-3.5-turbo"])

    call_args = http_client.post.await_args
    assert call_args.args[0].endswith("/team/update")
    assert call_args.kwargs["json"] == {
        "team_id": "jahrgang-7",
        "models": ["gpt-4o-mini", "gpt-3.5-turbo"],
    }


@pytest.mark.asyncio
async def test_update_team_models_accepts_201_as_success():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 201
    response.text = ""
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        await client.update_team_models("lehrkraefte", ["gpt-4"])


@pytest.mark.asyncio
async def test_update_team_models_raises_on_unexpected_status():
    client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 500
    response.text = "internal error"
    http_client.post = AsyncMock(return_value=response)

    with patch.object(client, "_get_client", new=AsyncMock(return_value=http_client)):
        with pytest.raises(RuntimeError):
            await client.update_team_models("jahrgang-8", ["gpt-4"])
