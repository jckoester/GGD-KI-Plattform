"""Unit-Tests für app.api.admin.flags (Krisen-Einsicht Phase 12, Schritt 3).

Shape + Autorisierung mit gemockter DB. DB-Verhalten (Join, EXISTS, Filter) wird im
Integrationstest test_crisis_flag_dashboard.py gegen die echte Test-DB geprüft.
"""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.api.admin.flags import router
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.session import get_db


def _admin() -> JwtPayload:
    return JwtPayload(sub="p-admin", roles=["admin"], grade=None, jti="j-1", iat=1, exp=9999999999)


def _teacher() -> JwtPayload:
    return JwtPayload(sub="p-teacher", roles=["teacher"], grade=None, jti="j-2", iat=1, exp=9999999999)


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


def _fake_flag():
    flag = MagicMock()
    flag.id = uuid4()
    flag.conversation_id = uuid4()
    flag.flag_source = "auto_crisis"
    flag.flag_category = "suizidalitaet"
    flag.severity = "alert"
    flag.trigger_rule = "crisis_triggers:suizidalitaet"
    flag.flagged_at = datetime(2026, 6, 20, 10, 0, tzinfo=timezone.utc)
    flag.status = "open"
    return flag


def _db_with_rows(total, rows):
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=total)
    result = MagicMock()
    result.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


def test_list_flags_returns_pseudonymous_items():
    flag = _fake_flag()
    db = _db_with_rows(1, [(flag, "pseudo-x", True)])
    app = _make_app(_admin(), db)

    response = TestClient(app).get("/flags")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["pseudonym"] == "pseudo-x"
    assert item["flag_category"] == "suizidalitaet"
    assert item["severity"] == "alert"
    assert item["has_active_request"] is True
    # Keine Chat-Inhalte im Dashboard
    assert "content" not in item
    assert "messages" not in item


def test_list_flags_empty():
    db = _db_with_rows(0, [])
    app = _make_app(_admin(), db)
    response = TestClient(app).get("/flags")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 25, "offset": 0}


def test_list_flags_requires_admin():
    app = _make_app(_teacher(), AsyncMock())
    response = TestClient(app).get("/flags")
    assert response.status_code == 403


def test_list_flags_rejects_bad_limit():
    app = _make_app(_admin(), AsyncMock())
    response = TestClient(app).get("/flags?limit=500")
    assert response.status_code == 422
