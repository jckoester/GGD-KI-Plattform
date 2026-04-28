import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("STUDENT_GRADES", "[5,6,7,8,9,10,11,12,13]")

from app.api.admin.stats import (
    _build_team_where,
    _format_period,
    _team_conditions,
    router as stats_router,
)
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.session import get_db


def _fake_stats_payload() -> JwtPayload:
    return JwtPayload(sub="p-1", roles=["statistics"], grade=None,
                      jti="j-1", iat=1, exp=9999999999)


def _fake_admin_payload() -> JwtPayload:
    return JwtPayload(sub="p-1", roles=["admin"], grade=None,
                      jti="j-1", iat=1, exp=9999999999)


def _fake_teacher_payload() -> JwtPayload:
    return JwtPayload(sub="p-1", roles=["teacher"], grade=None,
                      jti="j-1", iat=1, exp=9999999999)


def _make_stats_app(payload: JwtPayload, mock_db) -> FastAPI:
    app = FastAPI()
    app.include_router(stats_router)

    async def fake_user():
        return payload

    async def fake_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[get_db] = fake_db
    return app


def _mock_heatmap_db(rows) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    session.execute.return_value = result
    return session


def _mock_spend_db(rate, rows) -> AsyncMock:
    session = AsyncMock()
    rate_result = MagicMock()
    rate_result.scalar_one_or_none.return_value = rate
    spend_result = MagicMock()
    spend_result.fetchall.return_value = rows
    session.execute.side_effect = [rate_result, spend_result]
    return session


# --- _team_conditions ---

def test_team_conditions_none_returns_empty():
    assert _team_conditions(None) == []


def test_team_conditions_teacher():
    assert _team_conditions("lehrkraefte") == [("role", "teacher")]


def test_team_conditions_student_grade_10():
    result = _team_conditions("jahrgang-10")
    assert ("role", "student") in result
    assert ("grade", 10) in result


def test_team_conditions_student_grade_5():
    result = _team_conditions("jahrgang-5")
    assert ("role", "student") in result
    assert ("grade", 5) in result


def test_team_conditions_unknown_team():
    assert _team_conditions("unknown-team") == []


def test_team_conditions_invalid_grade():
    assert _team_conditions("jahrgang-abc") == []


# --- _build_team_where ---

def test_build_team_where_none():
    where_clause, params = _build_team_where(None, {})
    assert where_clause == ""
    assert params == {}


def test_build_team_where_teacher():
    where_clause, params = _build_team_where("lehrkraefte", {})
    assert "pa.role = :pa_role" in where_clause
    assert params["pa_role"] == "teacher"


def test_build_team_where_student():
    where_clause, params = _build_team_where("jahrgang-10", {})
    assert "pa.role = :pa_role" in where_clause
    assert "pa.grade = :pa_grade" in where_clause
    assert params["pa_role"] == "student"
    assert params["pa_grade"] == 10


# --- _format_period ---

def test_format_period_month():
    assert _format_period(datetime(2026, 4, 15), "month") == "2026-04"


def test_format_period_week():
    result = _format_period(datetime(2026, 4, 20), "week")
    assert result == "2026-W17"


def test_format_period_day():
    assert _format_period(datetime(2026, 4, 26), "day") == "2026-04-26"


# --- Heatmap Endpoint ---

def test_get_heatmap_returns_correct_structure():
    mock_db = _mock_heatmap_db([(0, 9, 5), (2, 14, 3)])
    app = _make_stats_app(_fake_stats_payload(), mock_db)
    client = TestClient(app)
    response = client.get("/stats/heatmap")
    assert response.status_code == 200
    data = response.json()
    assert data["cells"][0] == {"dow": 0, "hour": 9, "count": 5}
    assert data["cells"][1] == {"dow": 2, "hour": 14, "count": 3}
    assert "week_start" in data
    assert "week_end" in data
    assert "team_id" in data


def test_get_heatmap_empty_week_returns_no_cells():
    mock_db = _mock_heatmap_db([])
    app = _make_stats_app(_fake_stats_payload(), mock_db)
    client = TestClient(app)
    response = client.get("/stats/heatmap")
    assert response.status_code == 200
    assert response.json()["cells"] == []


def test_get_heatmap_team_id_is_reflected_in_response():
    mock_db = _mock_heatmap_db([])
    app = _make_stats_app(_fake_stats_payload(), mock_db)
    client = TestClient(app)
    response = client.get("/stats/heatmap?team_id=lehrkraefte")
    assert response.status_code == 200
    assert response.json()["team_id"] == "lehrkraefte"


def test_get_heatmap_requires_statistics_or_admin_role():
    mock_db = _mock_heatmap_db([])
    app = _make_stats_app(_fake_teacher_payload(), mock_db)
    client = TestClient(app)
    response = client.get("/stats/heatmap")
    assert response.status_code == 403


# --- Spend Endpoint ---

def test_get_spend_returns_monthly_aggregation():
    mock_db = _mock_spend_db(1.08, [(datetime(2026, 4, 1), 1.08)])
    app = _make_stats_app(_fake_stats_payload(), mock_db)
    client = TestClient(app)
    response = client.get("/stats/spend?from_date=2026-04-01&to_date=2026-04-30")
    assert response.status_code == 200
    data = response.json()
    assert data["entries"][0]["period"] == "2026-04"
    assert abs(data["entries"][0]["usd"] - 1.08) < 0.001
    assert abs(data["entries"][0]["eur"] - 1.0) < 0.001
    assert abs(data["eur_usd_rate"] - 1.08) < 0.001


def test_get_spend_sums_total_correctly():
    mock_db = _mock_spend_db(1.0, [
        (datetime(2026, 3, 1), 100.0),
        (datetime(2026, 4, 1), 50.0),
    ])
    app = _make_stats_app(_fake_stats_payload(), mock_db)
    client = TestClient(app)
    response = client.get("/stats/spend")
    assert response.status_code == 200
    data = response.json()
    assert abs(data["total_usd"] - 150.0) < 0.001
    assert abs(data["total_eur"] - 150.0) < 0.001


def test_get_spend_falls_back_to_rate_1_if_no_exchange_rate():
    mock_db = _mock_spend_db(None, [(datetime(2026, 4, 1), 100.0)])
    app = _make_stats_app(_fake_stats_payload(), mock_db)
    client = TestClient(app)
    response = client.get("/stats/spend")
    assert response.status_code == 200
    data = response.json()
    assert abs(data["eur_usd_rate"] - 1.0) < 0.001
    assert abs(data["total_eur"] - data["total_usd"]) < 0.001


def test_get_spend_requires_statistics_or_admin_role():
    mock_db = _mock_spend_db(1.0, [])
    app = _make_stats_app(_fake_teacher_payload(), mock_db)
    client = TestClient(app)
    response = client.get("/stats/spend")
    assert response.status_code == 403


def test_get_heatmap_model_filter_is_passed_to_sql():
    """Test: Modell-Filter (?model=) wird korrekt an SQL weitergegeben"""
    from sqlalchemy import text
    
    # Mock DB mit Aufruf-Rückverfolgung
    session = AsyncMock()
    captured_params = {}
    
    def track_execute(stmt, params=None):
        nonlocal captured_params
        captured_params = params or {}
        result = MagicMock()
        result.fetchall.return_value = []
        return result
    
    session.execute.side_effect = track_execute
    
    app = _make_stats_app(_fake_stats_payload(), session)
    client = TestClient(app)
    response = client.get("/stats/heatmap?model=gpt-4o-mini")
    
    assert response.status_code == 200
    assert "model" in captured_params
    assert captured_params["model"] == "gpt-4o-mini"


def test_get_spend_model_filter_is_passed_to_sql():
    """Test: Modell-Filter in /stats/spend wird korrekt an SQL weitergegeben"""
    # Mock DB mit Aufruf-Rückverfolgung
    session = AsyncMock()
    captured_params = {}
    
    def track_execute(stmt, params=None):
        nonlocal captured_params
        captured_params = params or {}
        result = MagicMock()
        # Für Spend-Endpoint: erster Aufruf = rate, zweiter = spend
        if "eur_usd_rate" in str(stmt):
            result.scalar_one_or_none.return_value = 1.08
        else:
            result.fetchall.return_value = []
        return result
    
    session.execute.side_effect = track_execute
    
    app = _make_stats_app(_fake_stats_payload(), session)
    client = TestClient(app)
    response = client.get("/stats/spend?model=gpt-4o")
    
    assert response.status_code == 200
    # Prüfe dass model-Parameter in wenigstens einem der SQL-Aufrufe war
    assert "model" in captured_params
