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


# ========== POST /{flag_id}/access-requests ==========

_FLAG_ID = "11111111-1111-1111-1111-111111111111"
_VALID_REASON = (
    "Schülerin hat in mehreren Nachrichten deutliche Suizidalität geäußert; "
    "Einsicht zur Einschätzung der akuten Gefährdung erforderlich."
)


def _flag_obj(status="open"):
    flag = MagicMock()
    flag.id = _FLAG_ID
    flag.conversation_id = "22222222-2222-2222-2222-222222222222"
    flag.status = status
    return flag


def _db_for_create(flag, existing=None):
    session = AsyncMock()
    session.get = AsyncMock(return_value=flag)
    session.scalar = AsyncMock(return_value=existing)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def test_create_access_request_requires_admin():
    app = _make_app(_teacher(), AsyncMock())
    r = TestClient(app).post(
        f"/flags/{_FLAG_ID}/access-requests",
        json={"reason": _VALID_REASON, "window_hours": 24},
    )
    assert r.status_code == 403


def test_create_access_request_reason_too_long_422():
    app = _make_app(_admin(), AsyncMock())
    r = TestClient(app).post(
        f"/flags/{_FLAG_ID}/access-requests", json={"reason": "x" * 2001}
    )
    assert r.status_code == 422


def test_create_access_request_window_out_of_range_422():
    app = _make_app(_admin(), AsyncMock())
    r = TestClient(app).post(
        f"/flags/{_FLAG_ID}/access-requests",
        json={"reason": _VALID_REASON, "window_hours": 999},
    )
    assert r.status_code == 422


def test_create_access_request_flag_not_found_404():
    app = _make_app(_admin(), _db_for_create(None))
    r = TestClient(app).post(
        f"/flags/{_FLAG_ID}/access-requests", json={"reason": _VALID_REASON}
    )
    assert r.status_code == 404


def test_create_access_request_closed_flag_409():
    app = _make_app(_admin(), _db_for_create(_flag_obj(status="resolved")))
    r = TestClient(app).post(
        f"/flags/{_FLAG_ID}/access-requests", json={"reason": _VALID_REASON}
    )
    assert r.status_code == 409


def test_create_access_request_duplicate_409():
    app = _make_app(_admin(), _db_for_create(_flag_obj(), existing="existing-id"))
    r = TestClient(app).post(
        f"/flags/{_FLAG_ID}/access-requests", json={"reason": _VALID_REASON}
    )
    assert r.status_code == 409
