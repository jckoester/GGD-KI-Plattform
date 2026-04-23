from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.litellm.user_service import (_extract_current_team_ids,
                                        ensure_litellm_team_membership,
                                        ensure_litellm_user)


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


def test_extract_current_team_ids_from_multiple_shapes():
    data = {
        "team_id": "jahrgang-9",
        "team_alias": "jahrgang-9",
        "team": {"team_alias": "jahrgang-10"},
        "team_ids": ["jahrgang-11"],
        "teams": [
            "lehrkraefte",
            {"team_id": "jahrgang-12"},
            {"team_alias": "jahrgang-8"},
            {"id": "jahrgang-7"},
        ],
    }

    team_ids = _extract_current_team_ids(data)
    assert "jahrgang-9" in team_ids
    assert "jahrgang-10" in team_ids
    assert "jahrgang-11" in team_ids
    assert "jahrgang-12" in team_ids
    assert "jahrgang-8" in team_ids
    assert "jahrgang-7" in team_ids
    assert "lehrkraefte" in team_ids


@pytest.mark.asyncio
async def test_ensure_litellm_user_generates_key_when_none_in_db():
    """Kein Key in DB → generate_key wird aufgerufen und Key committed."""
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=execute_result)
    client = AsyncMock()
    client.get_user.return_value = None
    client.generate_key = AsyncMock(return_value="sk-new-key")

    with patch("app.litellm.user_service.get_budget_for", return_value=(2.0, "1mo")), \
         patch("app.litellm.user_service.get_current_rate", new=AsyncMock(return_value=1.0)), \
         patch("app.litellm.user_service.LiteLLMClient", return_value=client):
        await ensure_litellm_user(
            db,
            pseudonym="pseudo-key",
            roles=["student"],
            grade="9",
            old_role=None,
            old_grade=None,
        )

    client.generate_key.assert_awaited_once_with("pseudo-key")
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_litellm_user_skips_key_generation_when_key_exists():
    """Key bereits in DB → generate_key wird nicht aufgerufen."""
    db = AsyncMock()
    db.execute.return_value.scalar_one_or_none.return_value = "sk-existing-key"
    client = AsyncMock()
    client.get_user.return_value = {"user_id": "pseudo-has-key"}

    with patch("app.litellm.user_service.get_budget_for", return_value=(2.0, "1mo")), \
         patch("app.litellm.user_service.get_current_rate", new=AsyncMock(return_value=1.0)), \
         patch("app.litellm.user_service.LiteLLMClient", return_value=client):
        await ensure_litellm_user(
            db,
            pseudonym="pseudo-has-key",
            roles=["student"],
            grade="9",
            old_role="student",
            old_grade=9,
        )

    client.generate_key.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_litellm_user_api_error_is_logged_but_not_raised():
    db = AsyncMock()
    client = AsyncMock()
    client.get_user.side_effect = RuntimeError("LiteLLM unreachable")

    with patch("app.litellm.user_service.get_budget_for", return_value=(2.0, "1mo")), \
         patch("app.litellm.user_service.get_current_rate", new=AsyncMock(return_value=1.0)), \
         patch("app.litellm.user_service.LiteLLMClient", return_value=client):
        await ensure_litellm_user(
            db,
            pseudonym="pseudo-5",
            roles=["student"],
            grade="10",
            old_role="student",
            old_grade=10,
        )

    client.get_user.assert_awaited_once_with("pseudo-5")
    client.close.assert_awaited_once()


# --- Tests for ensure_litellm_team_membership ---


@pytest.mark.asyncio
async def test_ensure_litellm_team_membership_no_change_needed():
    """User ist bereits im Zielteam → reconcile User ist unchanged, keine API-Calls."""
    mock_client = AsyncMock()
    mock_client.get_user.return_value = {
        "user_id": "pseudo-1",
        "teams": [{"team_id": "jahrgang-10"}],
    }

    reconcile_mock = AsyncMock(return_value={"unchanged": True, "added": [], "removed": []})

    with patch("app.litellm.user_service.reconcile_user_team", new=reconcile_mock), \
         patch("app.litellm.user_service.LiteLLMClient", return_value=mock_client):
        await ensure_litellm_team_membership(
            pseudonym="pseudo-1",
            roles=["student"],
            grade="10",
        )

    mock_client.get_user.assert_awaited_once_with("pseudo-1")
    reconcile_mock.assert_awaited_once()
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_litellm_team_membership_team_change():
    """User wechselt von jahrgang-7 zu jahrgang-8 → remove + add."""
    mock_client = AsyncMock()
    mock_client.get_user.return_value = {
        "user_id": "pseudo-2",
        "teams": [{"team_id": "jahrgang-7"}],
    }

    reconcile_mock = AsyncMock(return_value={
        "unchanged": False,
        "added": ["jahrgang-8"],
        "removed": ["jahrgang-7"],
    })

    with patch("app.litellm.user_service.reconcile_user_team", new=reconcile_mock), \
         patch("app.litellm.user_service.LiteLLMClient", return_value=mock_client):
        await ensure_litellm_team_membership(
            pseudonym="pseudo-2",
            roles=["student"],
            grade=8,
        )

    reconcile_mock.assert_awaited_once()
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_litellm_team_membership_new_user_no_litellm_entry():
    """get_user liefert None → current_team_ids = {} → add-Call."""
    mock_client = AsyncMock()
    mock_client.get_user.return_value = None

    reconcile_mock = AsyncMock(return_value={
        "unchanged": False,
        "added": ["jahrgang-9"],
        "removed": [],
    })

    with patch("app.litellm.user_service.reconcile_user_team", new=reconcile_mock), \
         patch("app.litellm.user_service.LiteLLMClient", return_value=mock_client):
        await ensure_litellm_team_membership(
            pseudonym="pseudo-new",
            roles=["student"],
            grade="9",
        )

    mock_client.get_user.assert_awaited_once_with("pseudo-new")
    reconcile_mock.assert_awaited_once()
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_litellm_team_membership_invalid_grade():
    """get_target_team_id wirft ValueError → loggt und kehrt zurück."""
    mock_client = AsyncMock()

    with patch("app.litellm.user_service.get_target_team_id", side_effect=ValueError("Ungültiger Grade")), \
         patch("app.litellm.user_service.LiteLLMClient", return_value=mock_client):
        await ensure_litellm_team_membership(
            pseudonym="pseudo-invalid",
            roles=["student"],
            grade=199,  # Ungültiger Jahrgang
        )

    # Wenn ValueError vor Client-Erstellung auftritt, wird Client nicht erstellt
    # und daher auch nicht geschlossen
    mock_client.get_user.assert_not_awaited()
    mock_client.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_litellm_team_membership_litellm_unreachable():
    """get_user wirft Exception → loggt und kehrt zurück."""
    mock_client = AsyncMock()
    mock_client.get_user.side_effect = RuntimeError("Connection failed")

    with patch("app.litellm.user_service.LiteLLMClient", return_value=mock_client):
        await ensure_litellm_team_membership(
            pseudonym="pseudo-error",
            roles=["student"],
            grade="10",
        )

    mock_client.get_user.assert_awaited_once_with("pseudo-error")
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_litellm_team_membership_teacher():
    """Lehrer landet im lehrkraefte Team."""
    mock_client = AsyncMock()
    mock_client.get_user.return_value = {
        "user_id": "teacher-1",
        "teams": [],
    }

    reconcile_mock = AsyncMock(return_value={
        "unchanged": False,
        "added": ["lehrkraefte"],
        "removed": [],
    })

    with patch("app.litellm.user_service.reconcile_user_team", new=reconcile_mock), \
         patch("app.litellm.user_service.LiteLLMClient", return_value=mock_client):
        await ensure_litellm_team_membership(
            pseudonym="teacher-1",
            roles=["teacher"],
            grade=None,
        )

    reconcile_mock.assert_awaited_once()
    mock_client.close.assert_awaited_once()
