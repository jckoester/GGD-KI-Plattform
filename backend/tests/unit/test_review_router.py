"""Unit-Tests für die Zweitfreigabe-Guards (Phase 12, Schritt 6).

Rollen- und Step-up-Erzwingung mit TestClient; die Freigabe-Logik selbst deckt der
Integrationstest test_crisis_approval.py ab.
"""

import os
from types import SimpleNamespace
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
ADMIN = JwtPayload(sub="p-admin", roles=["teacher", "admin"], grade=None, jti="j", iat=1, exp=9999999999)


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


def test_pending_count_review():
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=2)
    app = _make_app(REVIEW, db=db)
    r = TestClient(app).get("/access-requests/pending-count")
    assert r.status_code == 200
    assert r.json() == {"count": 2}


def test_pending_count_requires_review():
    app = _make_app(TEACHER)
    r = TestClient(app).get("/access-requests/pending-count")
    assert r.status_code == 403


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


# ---------- Gewaltenteilung / Vier-Augen (Audit #3) ----------

REVIEW_ADMIN = JwtPayload(
    sub="p-review-admin", roles=["review", "admin"], grade=None, jti="j", iat=1, exp=9999999999
)


def _pending_req(requested_by="p-antragsteller"):
    from datetime import datetime, timezone
    return SimpleNamespace(
        id=uuid4(), conversation_id=uuid4(), flag_id=uuid4(),
        requested_by=requested_by, status="pending", access_window_hours=24,
        coreviewer=None, coreviewer_approved_at=None, access_granted_until=None,
        requested_at=datetime.now(timezone.utc),
    )


def test_approve_rejected_for_self():
    db = AsyncMock()
    db.get = AsyncMock(return_value=_pending_req(requested_by="p-review"))
    app = _make_app(REVIEW, db=db)
    client = TestClient(app)
    client.cookies.set("stepup", _stepup_cookie("p-review"))
    r = client.post(f"/access-requests/{uuid4()}/approve")
    assert r.status_code == 403
    assert "Selbst-Freigabe" in r.json()["detail"]


def test_approve_rejected_for_admin_reviewer():
    # additive Rollen review+admin: darf NICHT freigeben (Unabhängigkeit)
    db = AsyncMock()
    db.get = AsyncMock(return_value=_pending_req(requested_by="p-antragsteller"))
    app = _make_app(REVIEW_ADMIN, db=db)
    client = TestClient(app)
    client.cookies.set("stepup", _stepup_cookie("p-review-admin"))
    r = client.post(f"/access-requests/{uuid4()}/approve")
    assert r.status_code == 403
    assert "Admin" in r.json()["detail"]


def test_approve_allowed_for_independent_reviewer():
    db = AsyncMock()
    db.get = AsyncMock(return_value=_pending_req(requested_by="p-antragsteller"))
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    app = _make_app(REVIEW, db=db)
    client = TestClient(app)
    client.cookies.set("stepup", _stepup_cookie("p-review"))
    r = client.post(f"/access-requests/{uuid4()}/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    assert r.json()["coreviewer"] == "p-review"


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


# ---------- Resolution: nur Admin, Notiz Pflicht (Schritt 8) ----------

def test_resolve_requires_admin():
    app = _make_app(REVIEW)  # review, aber kein admin
    r = TestClient(app).post(
        f"/access-requests/{uuid4()}/resolve",
        json={"outcome": "resolved", "note": "abgeschlossen"},
    )
    assert r.status_code == 403


def test_resolve_blank_note_422():
    app = _make_app(ADMIN)
    r = TestClient(app).post(
        f"/access-requests/{uuid4()}/resolve",
        json={"outcome": "resolved", "note": "   "},
    )
    assert r.status_code == 422


def test_resolve_invalid_outcome_422():
    app = _make_app(ADMIN)
    r = TestClient(app).post(
        f"/access-requests/{uuid4()}/resolve",
        json={"outcome": "bogus", "note": "x"},
    )
    assert r.status_code == 422
