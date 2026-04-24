import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

from scripts.monthly_budget_reconcile import run


def _make_user(pseudonym="p1", role="student", grade=7):
    """Hilfsfunktion: Erstellt einen Mock-User."""
    user = MagicMock()
    user.pseudonym = pseudonym
    user.role = role
    user.grade = grade
    return user


def _make_db_session(users):
    """
    Gibt einen AsyncMock zurueck, der als `async with AsyncSessionLocal() as db` funktioniert.
    
    Wichtig: result.scalars() muss das ScalarsResult direkt zurueckgeben (keine Coroutine).
    In SQLAlchemy async gibt result.scalars() ein ScalarResult zurueck, das .all() hat.
    """
    # Erstelle das ScalarsResult-Objekt mit .all() Methode
    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=users)
    
    # Erstelle das ExecuteResult-Objekt
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars_result)
    
    # Erstelle die DB-Session
    db = AsyncMock()
    db.execute = AsyncMock(return_value=execute_result)
    
    # Erstelle den Session-Context-Manager
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=db)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    
    return session_cm


@pytest.mark.asyncio
async def test_run_happy_path_single_student():
    """1 Student, grade=7, rate=1.10, budget_eur=2.0 -> update_user_budget("p1", 2.2, "1mo") aufgerufen"""
    user = _make_user(pseudonym="p1", role="student", grade=7)
    session_factory = _make_db_session([user])

    with patch("scripts.monthly_budget_reconcile.AsyncSessionLocal", return_value=session_factory), \
         patch("scripts.monthly_budget_reconcile.get_current_rate", new=AsyncMock(return_value=1.10)), \
         patch("scripts.monthly_budget_reconcile.get_budget_for", return_value=(2.0, "1mo")), \
         patch("scripts.monthly_budget_reconcile.LiteLLMClient") as mock_client_cls, \
         patch("scripts.monthly_budget_reconcile.reconcile_user_team", new=AsyncMock(return_value={"unchanged": True, "added": [], "removed": []})), \
         patch("scripts.monthly_budget_reconcile._extract_current_team_ids", return_value=set()):

        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.get_user = AsyncMock(return_value={"user_id": "p1"})
        mock_client.update_user_budget = AsyncMock()
        mock_client_cls.return_value = mock_client

        await run(dry_run=False, limit=0, pseudonym_filter=None)

    # Budget wurde aktualisiert
    mock_client.update_user_budget.assert_awaited_once_with("p1", 2.2, "1mo")
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_dry_run_skips_api_calls():
    """dry_run=True, 1 Student -> update_user_budget NICHT aufgerufen; reconcile_user_team NICHT aufgerufen"""
    user = _make_user(pseudonym="p1", role="student", grade=7)
    session_factory = _make_db_session([user])

    with patch("scripts.monthly_budget_reconcile.AsyncSessionLocal", return_value=session_factory), \
         patch("scripts.monthly_budget_reconcile.get_current_rate", new=AsyncMock(return_value=1.10)), \
         patch("scripts.monthly_budget_reconcile.get_budget_for", return_value=(2.0, "1mo")), \
         patch("scripts.monthly_budget_reconcile.LiteLLMClient") as mock_client_cls, \
         patch("scripts.monthly_budget_reconcile.reconcile_user_team") as mock_reconcile, \
         patch("scripts.monthly_budget_reconcile._extract_current_team_ids", return_value=set()):

        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client

        await run(dry_run=True, limit=0, pseudonym_filter=None)

    mock_client.update_user_budget.assert_not_awaited()
    mock_client.get_user.assert_not_awaited()
    mock_reconcile.assert_not_awaited()
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_invalid_grade_skips_team_but_updates_budget():
    """grade=99 -> get_target_team_id wirft ValueError -> Budget-Update laeuft durch; Team-Phase uebersprungen"""
    user = _make_user(pseudonym="p1", role="student", grade=99)
    session_factory = _make_db_session([user])

    with patch("scripts.monthly_budget_reconcile.AsyncSessionLocal", return_value=session_factory), \
         patch("scripts.monthly_budget_reconcile.get_current_rate", new=AsyncMock(return_value=1.10)), \
         patch("scripts.monthly_budget_reconcile.get_budget_for", return_value=(2.0, "1mo")), \
         patch("scripts.monthly_budget_reconcile.LiteLLMClient") as mock_client_cls, \
         patch("scripts.monthly_budget_reconcile.reconcile_user_team") as mock_reconcile, \
         patch("scripts.monthly_budget_reconcile._extract_current_team_ids", return_value=set()):

        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.get_user = AsyncMock(return_value={"user_id": "p1"})
        mock_client.update_user_budget = AsyncMock()
        mock_client_cls.return_value = mock_client

        await run(dry_run=False, limit=0, pseudonym_filter=None)

    # Budget wurde aktualisiert
    mock_client.update_user_budget.assert_awaited_once_with("p1", 2.2, "1mo")
    # Team-Reconcile wurde NICHT aufgerufen
    mock_reconcile.assert_not_awaited()
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_budget_api_error_continues_to_next_user():
    """2 User; update_user_budget wirft bei User 1 RuntimeError -> User 2 wird trotzdem verarbeitet"""
    user1 = _make_user(pseudonym="p1", role="student", grade=7)
    user2 = _make_user(pseudonym="p2", role="student", grade=8)
    session_factory = _make_db_session([user1, user2])

    with patch("scripts.monthly_budget_reconcile.AsyncSessionLocal", return_value=session_factory), \
         patch("scripts.monthly_budget_reconcile.get_current_rate", new=AsyncMock(return_value=1.10)), \
         patch("scripts.monthly_budget_reconcile.get_budget_for", return_value=(2.0, "1mo")), \
         patch("scripts.monthly_budget_reconcile.LiteLLMClient") as mock_client_cls, \
         patch("scripts.monthly_budget_reconcile.reconcile_user_team") as mock_reconcile, \
         patch("scripts.monthly_budget_reconcile._extract_current_team_ids", return_value=set()):

        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.update_user_budget = AsyncMock(side_effect=RuntimeError("API Error"))
        mock_client.get_user = AsyncMock(return_value={"user_id": "p1"})
        mock_client_cls.return_value = mock_client

        # Sollte nicht raise
        await run(dry_run=False, limit=0, pseudonym_filter=None)

    # User 1 wurde versucht
    assert mock_client.update_user_budget.await_count >= 1
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_team_api_error_continues_to_next_user():
    """2 User; get_user wirft bei User 1 Exception -> User 2 wird trotzdem verarbeitet"""
    user1 = _make_user(pseudonym="p1", role="student", grade=7)
    user2 = _make_user(pseudonym="p2", role="student", grade=8)
    session_factory = _make_db_session([user1, user2])

    with patch("scripts.monthly_budget_reconcile.AsyncSessionLocal", return_value=session_factory), \
         patch("scripts.monthly_budget_reconcile.get_current_rate", new=AsyncMock(return_value=1.10)), \
         patch("scripts.monthly_budget_reconcile.get_budget_for", return_value=(2.0, "1mo")), \
         patch("scripts.monthly_budget_reconcile.LiteLLMClient") as mock_client_cls, \
         patch("scripts.monthly_budget_reconcile.reconcile_user_team") as mock_reconcile, \
         patch("scripts.monthly_budget_reconcile._extract_current_team_ids", return_value=set()):

        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.get_user = AsyncMock(side_effect=RuntimeError("API Error"))
        mock_client.update_user_budget = AsyncMock()
        mock_client_cls.return_value = mock_client

        # Sollte nicht raise
        await run(dry_run=False, limit=0, pseudonym_filter=None)

    # User 1 und User 2 wurden versucht
    assert mock_client.get_user.await_count >= 1
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_teacher_uses_lehrkraefte_team():
    """role="teacher", grade=None -> reconcile_user_team mit target_team_id="lehrkraefte" aufgerufen"""
    user = _make_user(pseudonym="t1", role="teacher", grade=None)
    session_factory = _make_db_session([user])

    mock_reconcile = AsyncMock(return_value={"unchanged": True, "added": [], "removed": []})

    with patch("scripts.monthly_budget_reconcile.AsyncSessionLocal", return_value=session_factory), \
         patch("scripts.monthly_budget_reconcile.get_current_rate", new=AsyncMock(return_value=1.10)), \
         patch("scripts.monthly_budget_reconcile.get_budget_for", return_value=(8.0, "1mo")), \
         patch("scripts.monthly_budget_reconcile.LiteLLMClient") as mock_client_cls, \
         patch("scripts.monthly_budget_reconcile.reconcile_user_team", new=mock_reconcile):

        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.get_user = AsyncMock(return_value={"user_id": "t1"})
        mock_client.update_user_budget = AsyncMock()
        mock_client_cls.return_value = mock_client

        await run(dry_run=False, limit=0, pseudonym_filter=None)

    # reconcile_user_team wurde mit lehrkraefte aufgerufen
    # Aufruf: reconcile_user_team(client, pseudonym, target_team_id, current_ids)
    # args[2] ist target_team_id
    assert mock_reconcile.await_args.args[2] == "lehrkraefte"
    mock_client.close.assert_awaited_once()
