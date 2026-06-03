"""Unit-Tests für die context_nodes-CRUD-API (keine echte DB)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.context.router import router as context_router
from app.auth.jwt import JwtPayload


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def make_jwt(roles: list[str] = None, sub: str = "pseudo-teacher") -> JwtPayload:
    return JwtPayload(
        sub=sub,
        roles=roles or ["teacher"],
        grade=None,
        jti="test-jti",
        iat=1000000,
        exp=9999999999,
    )


def make_node(
    *,
    id=None,
    category: str = "concept",
    content_type: str = "funktion",
    title: str = "digitalWrite",
    status: str = "active",
    read_scope: str = "school",
    write_scope: str = "private",
    owner_pseudonym: str = "pseudo-teacher",
):
    from datetime import datetime, timezone, date
    return SimpleNamespace(
        id=id or uuid4(),
        category=category,
        content_type=content_type,
        title=title,
        content=None,
        metadata_={},
        embedding=None,
        owner_pseudonym=owner_pseudonym,
        read_scope=read_scope,
        write_scope=write_scope,
        read_scope_group_id=None,
        write_scope_group_id=None,
        assistant_id=None,
        subject_id=None,
        min_grade=None,
        max_grade=None,
        status=status,
        valid_until=None,
        archived_at=None,
        schuljahr=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def make_app(mock_db, user: JwtPayload = None) -> FastAPI:
    from app.auth.dependencies import get_current_user
    from app.db.session import get_db

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: user or make_jwt()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.include_router(context_router)
    return app


def make_mock_db(nodes: list = None) -> AsyncMock:
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = nodes or []
    db.execute.return_value = execute_result
    db.get.return_value = None
    return db


# ── GET /context/nodes ────────────────────────────────────────────────────

class TestListNodes:

    def test_returns_list(self):
        nodes = [make_node(), make_node(title="analogRead", content_type="funktion")]
        db = make_mock_db(nodes)
        client = TestClient(make_app(db))
        resp = client.get("/context/nodes")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_requires_auth(self):
        from app.auth.dependencies import get_current_user
        from fastapi import HTTPException

        app = FastAPI()
        app.include_router(context_router)
        # kein dependency_override → echter Guard
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/context/nodes")
        assert resp.status_code in (401, 422)  # je nach FastAPI-Version

    def test_student_role_denied(self):
        db = make_mock_db()
        user = make_jwt(roles=["student"])
        client = TestClient(make_app(db, user))
        resp = client.get("/context/nodes")
        assert resp.status_code == 403


# ── POST /context/nodes ───────────────────────────────────────────────────

class TestCreateNode:

    def test_valid_payload_returns_201(self):
        node = make_node()
        db = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda n: None)
        # Simuliere db.add / db.commit ohne echte DB
        db.add = MagicMock()
        db.commit = AsyncMock()

        # router legt ein ContextNode-Objekt an und ruft db.refresh auf;
        # da wir kein echtes Objekt zurückbekommen, patchen wir den Router-Import
        import app.context.router as ctx_router_mod
        original_cn = ctx_router_mod.ContextNode

        created_node = make_node()

        class FakeContextNode:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
                # Felder die der Router nicht setzt aber das Schema erwartet
                from datetime import datetime, timezone
                self.id = created_node.id
                self.status = "active"
                self.embedding = None
                self.archived_at = None
                self.subject_id = None
                self.min_grade = None
                self.max_grade = None
                self.created_at = datetime.now(timezone.utc)
                self.updated_at = datetime.now(timezone.utc)

        ctx_router_mod.ContextNode = FakeContextNode
        try:
            client = TestClient(make_app(db))
            resp = client.post(
                "/context/nodes",
                json={"category": "concept", "content_type": "funktion", "title": "digitalWrite"},
            )
            assert resp.status_code == 201
        finally:
            ctx_router_mod.ContextNode = original_cn

    def test_invalid_content_type_returns_422(self):
        db = make_mock_db()
        client = TestClient(make_app(db))
        resp = client.post(
            "/context/nodes",
            json={"category": "document", "content_type": "fachplan", "title": "Test"},
        )
        assert resp.status_code == 422
        assert "fachplan" in resp.json()["detail"]

    def test_student_cannot_create(self):
        db = make_mock_db()
        user = make_jwt(roles=["student"])
        client = TestClient(make_app(db, user))
        resp = client.post(
            "/context/nodes",
            json={"category": "concept", "content_type": "funktion", "title": "Test"},
        )
        assert resp.status_code == 403


# ── GET /context/nodes/{id} ───────────────────────────────────────────────

class TestGetNode:

    def test_existing_node_returns_200(self):
        node = make_node()
        db = make_mock_db()
        db.get = AsyncMock(return_value=node)
        client = TestClient(make_app(db))
        resp = client.get(f"/context/nodes/{node.id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == node.title

    def test_missing_node_returns_404(self):
        db = make_mock_db()
        db.get = AsyncMock(return_value=None)
        client = TestClient(make_app(db))
        resp = client.get(f"/context/nodes/{uuid4()}")
        assert resp.status_code == 404

    def test_private_node_other_user_returns_403(self):
        node = make_node(read_scope="private", owner_pseudonym="other-user")
        db = make_mock_db()
        db.get = AsyncMock(return_value=node)
        user = make_jwt(roles=["teacher"], sub="pseudo-teacher")
        client = TestClient(make_app(db, user))
        resp = client.get(f"/context/nodes/{node.id}")
        assert resp.status_code == 403


# ── DELETE /context/nodes/{id} ───────────────────────────────────────────

class TestDeleteNode:

    def test_owner_can_delete(self):
        node = make_node(owner_pseudonym="pseudo-teacher")
        db = AsyncMock()
        db.get = AsyncMock(return_value=node)
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        user = make_jwt(roles=["teacher"], sub="pseudo-teacher")
        client = TestClient(make_app(db, user))
        resp = client.delete(f"/context/nodes/{node.id}")
        assert resp.status_code == 204

    def test_non_owner_cannot_delete(self):
        node = make_node(owner_pseudonym="other-user")
        db = AsyncMock()
        db.get = AsyncMock(return_value=node)
        user = make_jwt(roles=["teacher"], sub="pseudo-teacher")
        client = TestClient(make_app(db, user))
        resp = client.delete(f"/context/nodes/{node.id}")
        assert resp.status_code == 403

    def test_admin_can_delete_any(self):
        node = make_node(owner_pseudonym="other-user")
        db = AsyncMock()
        db.get = AsyncMock(return_value=node)
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        user = make_jwt(roles=["teacher", "admin"], sub="pseudo-admin")
        client = TestClient(make_app(db, user))
        resp = client.delete(f"/context/nodes/{node.id}")
        assert resp.status_code == 204
