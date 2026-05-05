"""Unit tests für Admin-Gruppen-Endpunkte und Validierung."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.admin.groups import (
    GroupCreate,
    MemberAdd,
    VALID_GROUP_TYPES,
    router as admin_groups_router,
)
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.session import get_db


_ADMIN = JwtPayload(
    sub="admin-pseudo", roles=["admin", "teacher"], grade=None,
    jti="jti", iat=1_000_000, exp=9_999_999_999,
)

_TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _make_group_mock(**kwargs) -> MagicMock:
    defaults = dict(id=1, name="Testgruppe", slug="testgruppe",
                    type="teaching_group", subject_id=None,
                    sso_group_id=None, created_at=_TS)
    defaults.update(kwargs)
    g = MagicMock()
    for k, v in defaults.items():
        setattr(g, k, v)
    return g


def _make_app(db_mock) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_db] = lambda: db_mock
    app.dependency_overrides[get_current_user] = lambda: _ADMIN
    app.include_router(admin_groups_router)
    return app


# ── Pydantic-Schema-Tests (kein DB) ──────────────────────────────────────────

class TestGroupCreate:
    def test_valid_type_accepted(self):
        for t in VALID_GROUP_TYPES:
            gc = GroupCreate(name="X", slug="x", type=t)
            assert gc.type == t

    def test_invalid_slug_uppercase_raises(self):
        with pytest.raises(ValidationError):
            GroupCreate(name="X", slug="Invalid-Slug", type="teaching_group")

    def test_invalid_slug_leading_dash_raises(self):
        with pytest.raises(ValidationError):
            GroupCreate(name="X", slug="-start", type="teaching_group")

    def test_valid_slug_with_dot_accepted(self):
        gc = GroupCreate(name="X", slug="kl.8a", type="school_class")
        assert gc.slug == "kl.8a"


class TestMemberAdd:
    def test_valid_roles_accepted(self):
        for role in ("teacher", "student", None):
            m = MemberAdd(pseudonym="abc", role_in_group=role)
            assert m.role_in_group == role

    def test_empty_pseudonym_raises(self):
        with pytest.raises(ValidationError):
            MemberAdd(pseudonym="", role_in_group="student")


# ── HTTP-Endpunkt-Tests ───────────────────────────────────────────────────────

def test_create_group_invalid_type_returns_422():
    """POST /groups mit ungültigem type → 422."""
    db = MagicMock()
    db.execute = AsyncMock()
    client = TestClient(_make_app(db))
    resp = client.post("/groups", json={"name": "X", "slug": "x", "type": "invalid_type"})
    assert resp.status_code == 422


def test_create_group_duplicate_slug_returns_409():
    """POST /groups mit bereits existierendem slug → 409."""
    existing = _make_group_mock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    db = MagicMock()
    db.execute = AsyncMock(return_value=mock_result)

    client = TestClient(_make_app(db))
    resp = client.post("/groups", json={"name": "X", "slug": "testgruppe", "type": "teaching_group"})
    assert resp.status_code == 409
    assert "existiert bereits" in resp.json()["detail"]


def test_delete_group_with_referencing_assistants_returns_409():
    """DELETE /groups/{id} schlägt fehl, wenn Assistenten darauf referenzieren → 409."""
    count_result = MagicMock()
    count_result.scalar.return_value = 3

    group_result = MagicMock()
    group_result.scalar_one_or_none.return_value = _make_group_mock()

    call_count = [0]

    async def mock_execute(_stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return count_result
        return group_result

    db = MagicMock()
    db.execute = mock_execute

    client = TestClient(_make_app(db))
    resp = client.delete("/groups/1")
    assert resp.status_code == 409
    assert "3" in resp.json()["detail"]


def test_add_member_invalid_role_returns_422():
    """POST /groups/{id}/members mit ungültiger Rolle → 422."""
    group = _make_group_mock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = group
    db = MagicMock()
    db.execute = AsyncMock(return_value=mock_result)

    client = TestClient(_make_app(db))
    resp = client.post("/groups/1/members", json={"pseudonym": "abc", "role_in_group": "principal"})
    assert resp.status_code == 422
    assert "Ungueltige Rolle" in resp.json()["detail"]


def test_add_member_group_not_found_returns_404():
    """POST /groups/{id}/members mit nicht existierender Gruppe → 404."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db = MagicMock()
    db.execute = AsyncMock(return_value=mock_result)

    client = TestClient(_make_app(db))
    resp = client.post("/groups/999/members", json={"pseudonym": "abc", "role_in_group": "student"})
    assert resp.status_code == 404


def test_remove_member_not_found_returns_404():
    """DELETE /groups/{id}/members/{pseudonym} — Mitgliedschaft nicht gefunden → 404."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db = MagicMock()
    db.execute = AsyncMock(return_value=mock_result)

    client = TestClient(_make_app(db))
    resp = client.delete("/groups/1/members/unbekannt")
    assert resp.status_code == 404


def test_get_group_not_found_returns_404():
    """GET /groups/{id} mit unbekannter ID → 404."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db = MagicMock()
    db.execute = AsyncMock(return_value=mock_result)

    client = TestClient(_make_app(db))
    resp = client.get("/groups/999")
    assert resp.status_code == 404
