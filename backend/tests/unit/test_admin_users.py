"""Tests: Admin-Nutzer-/Sitzungsverwaltung (Sicherheits-Audit #11, „D")."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin.users import router
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.session import get_db


def _payload(roles):
    return JwtPayload(sub="admin-1", roles=roles, grade=None, jti="j", iat=1, exp=9999999999)


def _row(pseudonym, roles, role, grade=None):
    return SimpleNamespace(
        pseudonym=pseudonym, roles=roles, role=role, grade=grade,
        last_login_at=datetime(2026, 7, 1, tzinfo=timezone.utc), revoked_all_before=None,
    )


def _app(db, *, roles=("teacher", "admin")):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _payload(list(roles))

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app, raise_server_exceptions=False)


def _list_db(rows):
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    db.execute = AsyncMock(return_value=result)
    return db


def test_list_users_returns_effective_roles():
    rows = [
        _row("p-teach", ["teacher", "admin"], "teacher"),
        _row("p-legacy", None, "student", grade=8),  # vor Rollout: roles=NULL → Fallback
    ]
    client = _app(_list_db(rows))
    resp = client.get("/users")
    assert resp.status_code == 200
    users = {u["pseudonym"]: u for u in resp.json()["users"]}
    assert users["p-teach"]["roles"] == ["teacher", "admin"]
    assert users["p-legacy"]["roles"] == ["student"]


def test_list_users_role_filter():
    rows = [
        _row("p-admin", ["teacher", "admin"], "teacher"),
        _row("p-teacher", ["teacher"], "teacher"),
    ]
    client = _app(_list_db(rows))
    resp = client.get("/users", params={"role": "admin"})
    assert resp.status_code == 200
    pseudos = [u["pseudonym"] for u in resp.json()["users"]]
    assert pseudos == ["p-admin"]


def test_revoke_sessions_sets_timestamp():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
    client = _app(db)
    resp = client.post("/users/p-x/revoke-sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["pseudonym"] == "p-x"
    assert body["revoked_all_before"]
    db.commit.assert_awaited_once()


def test_revoke_sessions_unknown_user_404():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(rowcount=0))
    client = _app(db)
    resp = client.post("/users/nope/revoke-sessions")
    assert resp.status_code == 404
    db.commit.assert_not_awaited()


def test_list_users_requires_admin():
    client = _app(_list_db([]), roles=("teacher",))  # kein admin
    resp = client.get("/users")
    assert resp.status_code == 403


def test_revoke_requires_admin():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
    client = _app(db, roles=("teacher",))
    resp = client.post("/users/p-x/revoke-sessions")
    assert resp.status_code == 403
    db.commit.assert_not_awaited()
