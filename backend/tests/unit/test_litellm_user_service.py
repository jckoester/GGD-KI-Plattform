from unittest.mock import AsyncMock, patch

import pytest

from app.litellm.user_service import ensure_litellm_user


@pytest.mark.asyncio
async def test_ensure_litellm_user_first_login_creates_user_no_update():
    db = AsyncMock()
    client = AsyncMock()
    client.get_user.return_value = None

    with patch("app.litellm.user_service.get_budget_for", return_value=(2.0, "1mo")), \
         patch("app.litellm.user_service.get_current_rate", new=AsyncMock(return_value=1.1)), \
         patch("app.litellm.user_service.LiteLLMClient", return_value=client):
        await ensure_litellm_user(
            db,
            pseudonym="pseudo-1",
            roles=["student"],
            grade="10",
            old_role=None,
            old_grade=None,
        )

    client.create_user.assert_awaited_once_with("pseudo-1", 2.2, "1mo")
    client.update_user_budget.assert_not_awaited()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_litellm_user_existing_user_no_change_no_update():
    db = AsyncMock()
    client = AsyncMock()
    client.get_user.return_value = {"user_id": "pseudo-2"}

    with patch("app.litellm.user_service.get_budget_for", return_value=(2.0, "1mo")), \
         patch("app.litellm.user_service.get_current_rate", new=AsyncMock(return_value=1.0)), \
         patch("app.litellm.user_service.LiteLLMClient", return_value=client):
        await ensure_litellm_user(
            db,
            pseudonym="pseudo-2",
            roles=["student"],
            grade="10",
            old_role="student",
            old_grade=10,
        )

    client.create_user.assert_not_awaited()
    client.update_user_budget.assert_not_awaited()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_litellm_user_existing_user_grade_change_updates_budget():
    db = AsyncMock()
    client = AsyncMock()
    client.get_user.return_value = {"user_id": "pseudo-3"}

    with patch("app.litellm.user_service.get_budget_for", return_value=(3.5, "1mo")), \
         patch("app.litellm.user_service.get_current_rate", new=AsyncMock(return_value=1.0)), \
         patch("app.litellm.user_service.LiteLLMClient", return_value=client):
        await ensure_litellm_user(
            db,
            pseudonym="pseudo-3",
            roles=["student"],
            grade="11",
            old_role="student",
            old_grade=10,
        )

    client.update_user_budget.assert_awaited_once_with("pseudo-3", 3.5, "1mo")
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_litellm_user_teacher_plus_admin_keeps_teacher_budget():
    db = AsyncMock()
    client = AsyncMock()
    client.get_user.return_value = {"user_id": "pseudo-4"}

    with patch("app.litellm.user_service.get_budget_for", return_value=(8.0, "1mo")), \
         patch("app.litellm.user_service.get_current_rate", new=AsyncMock(return_value=1.0)), \
         patch("app.litellm.user_service.LiteLLMClient", return_value=client):
        await ensure_litellm_user(
            db,
            pseudonym="pseudo-4",
            roles=["teacher", "admin"],
            grade=None,
            old_role="teacher",
            old_grade=None,
        )

    client.update_user_budget.assert_not_awaited()
    client.close.assert_awaited_once()
