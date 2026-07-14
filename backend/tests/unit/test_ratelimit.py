"""Unit-Tests: Ratelimiting (Sicherheits-Audit #2)."""
import os

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.ratelimit import config, store
from app.ratelimit.dependency import rate_limit


@pytest.fixture(autouse=True)
def _clean_store():
    store.reset()
    yield
    store.reset()


# ── store.allow ───────────────────────────────────────────────────────────────

def test_allow_within_and_over_limit():
    assert store.allow("b", "u", 2, 60.0, now=100.0) == (True, 0.0)
    assert store.allow("b", "u", 2, 60.0, now=100.0)[0] is True
    ok, retry = store.allow("b", "u", 2, 60.0, now=100.0)   # 3. > Limit 2
    assert ok is False and retry == pytest.approx(60.0)


def test_window_resets():
    for _ in range(2):
        store.allow("b", "u", 2, 60.0, now=100.0)
    assert store.allow("b", "u", 2, 60.0, now=100.0)[0] is False
    # nach Ablauf des Fensters wieder erlaubt
    assert store.allow("b", "u", 2, 60.0, now=161.0)[0] is True


def test_separate_keys_per_user_and_bucket():
    store.allow("b", "u1", 1, 60.0, now=100.0)
    assert store.allow("b", "u1", 1, 60.0, now=100.0)[0] is False  # u1 voll
    assert store.allow("b", "u2", 1, 60.0, now=100.0)[0] is True   # u2 eigener Zähler
    assert store.allow("other", "u1", 1, 60.0, now=100.0)[0] is True  # anderer Bucket


def test_limit_zero_disables():
    for _ in range(5):
        assert store.allow("b", "u", 0, 60.0, now=100.0)[0] is True


# ── config.resolve ────────────────────────────────────────────────────────────

def test_resolve_builtin_default(monkeypatch):
    monkeypatch.setattr(config, "_cache", {})   # leere Config
    assert config.resolve("chat", []) == (60, 60.0)
    assert config.resolve("unbekannt", []) == (60, 60.0)  # Fallback


def test_resolve_bucket_and_role_override(monkeypatch):
    monkeypatch.setattr(config, "_cache", {
        "buckets": {"chat": {"limit": 40, "window": 60}},
        "roles": {"teacher": {"chat": {"limit": 120, "window": 60}}},
    })
    assert config.resolve("chat", ["student"]) == (40, 60.0)         # Bucket-Default
    assert config.resolve("chat", ["teacher"]) == (120, 60.0)        # Rollen-Override
    # großzügigstes Rollen-Limit gewinnt
    monkeypatch.setattr(config, "_cache", {
        "roles": {"a": {"chat": {"limit": 10, "window": 60}},
                  "b": {"chat": {"limit": 99, "window": 60}}},
    })
    assert config.resolve("chat", ["a", "b"]) == (99, 60.0)


# ── Dependency (429) ──────────────────────────────────────────────────────────

def _app(monkeypatch, limit=2):
    monkeypatch.setattr(config, "resolve", lambda bucket, roles: (limit, 60.0))
    app = FastAPI()

    @app.get("/x")
    async def x(user: JwtPayload = Depends(rate_limit("x"))):
        return {"sub": user.sub}

    app.dependency_overrides[get_current_user] = lambda: JwtPayload(
        sub="p", roles=["teacher"], grade=None, jti="j", iat=1, exp=9999999999
    )
    return TestClient(app)


def test_dependency_429_after_limit(monkeypatch):
    client = _app(monkeypatch, limit=2)
    assert client.get("/x").status_code == 200
    assert client.get("/x").status_code == 200
    resp = client.get("/x")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_dependency_returns_user(monkeypatch):
    client = _app(monkeypatch, limit=5)
    assert client.get("/x").json() == {"sub": "p"}
