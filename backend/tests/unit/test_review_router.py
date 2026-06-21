"""Unit-Tests für die Zweitfreigabe-Guards (Phase 12, Schritt 6).

Rollen- und Step-up-Erzwingung mit TestClient; die Freigabe-Logik selbst deckt der
Integrationstest test_crisis_approval.py ab.
"""

import os
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.api.review import router
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.auth.stepup import issue_stepup_token
from app.config import settings
from app.db.session import get_db

REVIEW = JwtPayload(sub="p-review", roles=["review"], grade=None, jti="j", iat=1, exp=9999999999)
TEACHER = JwtPayload(sub="p-teacher", roles=["teacher"], grade=None, jti="j", iat=1, exp=9999999999)


def _make_app(user, db=None):
    app = FastAPI()
    app.include_router(router)

    async def fake_user():
        return user

    async def fake_db():
        yield db or AsyncMock()

    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[get_db] = fake_db
    return app


def _empty_db():
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    return db


# ---------- GET /access-requests (Liste, nur review) ----------

def test_list_requires_review_role():
    app = _make_app(TEACHER)
    r = TestClient(app).get("/access-requests")
    assert r.status_code == 403


def test_list_allowed_for_review():
    app = _make_app(REVIEW, db=_empty_db())
    r = TestClient(app).get("/access-requests")
    assert r.status_code == 200
    assert r.json() == {"items": []}


# ---------- approve/deny: Rolle + Step-up ----------

def _stepup_cookie(sub):
    return issue_stepup_token(settings.jwt_secret, sub)


def test_approve_requires_review_role():
    # Lehrkraft mit frischem Step-up → trotzdem 403 (keine review-Rolle)
    app = _make_app(TEACHER)
    client = TestClient(app)
    client.cookies.set("stepup", _stepup_cookie("p-teacher"))
    r = client.post(f"/access-requests/{uuid4()}/approve")
    assert r.status_code == 403


def test_approve_requires_fresh_stepup():
    # review-Rolle, aber ohne Step-up-Cookie → 401 mit Hinweis-Header
    app = _make_app(REVIEW)
    r = TestClient(app).post(f"/access-requests/{uuid4()}/approve")
    assert r.status_code == 401
    assert r.headers.get("X-Stepup-Required") == "1"


def test_deny_requires_fresh_stepup():
    app = _make_app(REVIEW)
    r = TestClient(app).post(f"/access-requests/{uuid4()}/deny")
    assert r.status_code == 401


def test_deny_requires_review_role():
    app = _make_app(TEACHER)
    client = TestClient(app)
    client.cookies.set("stepup", _stepup_cookie("p-teacher"))
    r = client.post(f"/access-requests/{uuid4()}/deny")
    assert r.status_code == 403


# ---------- Reader-View: Step-up erzwungen (Schritt 7) ----------

def test_read_conversation_requires_fresh_stepup():
    app = _make_app(REVIEW)
    r = TestClient(app).get(f"/access-requests/{uuid4()}/conversation")
    assert r.status_code == 401
    assert r.headers.get("X-Stepup-Required") == "1"


def test_export_requires_fresh_stepup():
    app = _make_app(REVIEW)
    r = TestClient(app).post(f"/access-requests/{uuid4()}/export")
    assert r.status_code == 401
