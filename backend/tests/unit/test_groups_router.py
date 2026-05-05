"""Unit tests für GET /groups und GET /groups/me."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.groups import router as groups_router
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.session import get_db


_FAKE_USER = JwtPayload(
    sub="test-pseudo", roles=["student"], grade="8",
    jti="jti", iat=1_000_000, exp=9_999_999_999,
)

_TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _make_group(**kwargs) -> MagicMock:
    defaults = dict(id=1, name="Testgruppe", slug="testgruppe",
                    type="teaching_group", subject_id=None,
                    sso_group_id=None, created_at=_TS)
    defaults.update(kwargs)
    g = MagicMock()
    for k, v in defaults.items():
        setattr(g, k, v)
    return g


def _make_db_mock(items: list) -> MagicMock:
    mock_result = MagicMock()
    mock_result.scalars.return_value = MagicMock(all=lambda: items)
    db = MagicMock()
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _make_app(db_mock, user=None) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_db] = lambda: db_mock
    app.dependency_overrides[get_current_user] = lambda: (user or _FAKE_USER)
    app.include_router(groups_router)
    return app


# ── GET /groups ───────────────────────────────────────────────────────────────

def test_get_groups_empty():
    client = TestClient(_make_app(_make_db_mock([])))
    resp = client.get("/groups")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_get_groups_returns_items_in_db_order():
    g1 = _make_group(id=1, slug="activity-gruppe", type="activity_group")
    g2 = _make_group(id=2, slug="lerngruppe", type="teaching_group")
    client = TestClient(_make_app(_make_db_mock([g1, g2])))

    items = client.get("/groups").json()["items"]
    assert len(items) == 2
    assert items[0]["type"] == "activity_group"
    assert items[1]["type"] == "teaching_group"


def test_get_groups_all_fields_present():
    client = TestClient(_make_app(_make_db_mock([_make_group(subject_id=5, sso_group_id="sso-1")])))
    item = client.get("/groups").json()["items"][0]
    for field in ("id", "name", "slug", "type", "subject_id", "sso_group_id", "created_at"):
        assert field in item, f"Feld '{field}' fehlt"
    assert item["subject_id"] == 5
    assert item["sso_group_id"] == "sso-1"


def test_get_groups_nullable_fields():
    client = TestClient(_make_app(_make_db_mock([_make_group()])))
    item = client.get("/groups").json()["items"][0]
    assert item["subject_id"] is None
    assert item["sso_group_id"] is None


# ── GET /groups/me ────────────────────────────────────────────────────────────

def test_get_groups_me_empty():
    client = TestClient(_make_app(_make_db_mock([])))
    resp = client.get("/groups/me")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_get_groups_me_returns_user_groups():
    g = _make_group(id=1, name="Meine Gruppe")
    client = TestClient(_make_app(_make_db_mock([g])))
    items = client.get("/groups/me").json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Meine Gruppe"
