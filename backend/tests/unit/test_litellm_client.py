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
