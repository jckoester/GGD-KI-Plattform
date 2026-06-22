"""Unit-Tests für app.api.pedagogy (Phase 13, Schritt 4)."""

import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.api.pedagogy import router
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload


def _make_app(payload):
    app = FastAPI()
    app.include_router(router)

    async def fake_user():
        return payload

    app.dependency_overrides[get_current_user] = fake_user
    return app


def _user(roles):
    return JwtPayload(sub="p", roles=roles, grade=None, jti="j", iat=1, exp=9999999999)


def test_augmentations_for_teacher():
    app = _make_app(_user(["teacher"]))
    r = TestClient(app).get("/pedagogy/augmentations")
    assert r.status_code == 200
    items = r.json()["augmentations"]
    keys = {i["key"] for i in items}
    assert "no_complete_homework_solutions" in keys
    assert all("label" in i for i in items)


def test_augmentations_requires_teacher_or_admin():
    app = _make_app(_user(["student"]))
    r = TestClient(app).get("/pedagogy/augmentations")
    assert r.status_code == 403
