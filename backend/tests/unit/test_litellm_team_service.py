import os
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.litellm.team_service import reconcile_user_team


@pytest.mark.asyncio
async def test_reconcile_user_team_no_changes_when_already_in_target():
    client = AsyncMock()

    result = await reconcile_user_team(
        client=client,
        pseudonym="pseudo-1",
        target_team_id="jahrgang-7",
        current_team_ids={"jahrgang-7"},
    )

    client.remove_team_member.assert_not_awaited()
    client.add_team_member.assert_not_awaited()
    assert result["unchanged"] is True
    assert result["added"] == []
    assert result["removed"] == []


@pytest.mark.asyncio
async def test_reconcile_user_team_removes_wrong_team_and_adds_target():
    client = AsyncMock()

    result = await reconcile_user_team(
        client=client,
        pseudonym="pseudo-2",
        target_team_id="jahrgang-8",
        current_team_ids={"jahrgang-7"},
    )

    client.remove_team_member.assert_awaited_once_with("jahrgang-7", "pseudo-2")
    client.add_team_member.assert_awaited_once_with("jahrgang-8", "pseudo-2")
    assert result["removed"] == ["jahrgang-7"]
    assert result["added"] == ["jahrgang-8"]
    assert result["unchanged"] is False


@pytest.mark.asyncio
async def test_reconcile_user_team_removes_multiple_phase1_teams():
    client = AsyncMock()

    result = await reconcile_user_team(
        client=client,
        pseudonym="pseudo-3",
        target_team_id="jahrgang-10",
        current_team_ids={"jahrgang-7", "jahrgang-9"},
    )

    assert client.remove_team_member.await_count == 2
    client.add_team_member.assert_awaited_once_with("jahrgang-10", "pseudo-3")
    assert result["removed"] == ["jahrgang-7", "jahrgang-9"]
    assert result["added"] == ["jahrgang-10"]


@pytest.mark.asyncio
async def test_reconcile_user_team_keeps_foreign_teams_untouched():
    client = AsyncMock()

    result = await reconcile_user_team(
        client=client,
        pseudonym="pseudo-4",
        target_team_id="lehrkraefte",
        current_team_ids={"lehrkraefte", "fachschaft-mathe"},
    )

    client.remove_team_member.assert_not_awaited()
    client.add_team_member.assert_not_awaited()
    assert result["unchanged"] is True
