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


# ── Sicherheits-Audit #1: Lese-Berechtigung für fremde group-Knoten ───────────

def _group_node(group_id=7, owner="other-user"):
    node = make_node(read_scope="group", owner_pseudonym=owner)
    node.read_scope_group_id = group_id
    return node


class TestReadPermissionAudit1:

    def test_group_node_member_returns_200(self):
        node = _group_node()
        db = AsyncMock()
        db.get = AsyncMock(return_value=node)
        db.execute = AsyncMock(return_value=_exec_result(scalar=1))   # ist Mitglied
        user = make_jwt(roles=["teacher"], sub="pseudo-teacher")
        resp = TestClient(make_app(db, user)).get(f"/context/nodes/{node.id}")
        assert resp.status_code == 200

    def test_group_node_non_member_returns_403(self):
        node = _group_node()
        db = AsyncMock()
        db.get = AsyncMock(return_value=node)
        db.execute = AsyncMock(return_value=_exec_result(scalar=None))  # kein Mitglied
        user = make_jwt(roles=["teacher"], sub="fremde-lehrkraft")
        resp = TestClient(make_app(db, user)).get(f"/context/nodes/{node.id}")
        assert resp.status_code == 403

    def test_group_node_admin_returns_200_without_membership_check(self):
        node = _group_node()
        db = AsyncMock()
        db.get = AsyncMock(return_value=node)
        db.execute = AsyncMock(side_effect=AssertionError("Admin darf keine Mitgliedsprüfung auslösen"))
        user = make_jwt(roles=["teacher", "admin"], sub="pseudo-admin")
        resp = TestClient(make_app(db, user)).get(f"/context/nodes/{node.id}")
        assert resp.status_code == 200

    def test_private_node_admin_returns_403(self):
        # Privat ist owner-only — auch Admins sehen fremde private Knoten NICHT
        # (konsistent mit dem Listen-Filter _read_scope_clause).
        node = make_node(read_scope="private", owner_pseudonym="other-user")
        db = AsyncMock()
        db.get = AsyncMock(return_value=node)
        user = make_jwt(roles=["teacher", "admin"], sub="pseudo-admin")
        resp = TestClient(make_app(db, user)).get(f"/context/nodes/{node.id}")
        assert resp.status_code == 403

    def test_private_node_owner_admin_returns_200(self):
        # Der Owner (auch wenn Admin) darf seinen eigenen privaten Knoten lesen.
        node = make_node(read_scope="private", owner_pseudonym="pseudo-admin")
        db = AsyncMock()
        db.get = AsyncMock(return_value=node)
        user = make_jwt(roles=["teacher", "admin"], sub="pseudo-admin")
        resp = TestClient(make_app(db, user)).get(f"/context/nodes/{node.id}")
        assert resp.status_code == 200

    def test_school_node_readable_by_any_teacher(self):
        node = make_node(read_scope="school", owner_pseudonym="other-user")
        db = AsyncMock()
        db.get = AsyncMock(return_value=node)
        db.execute = AsyncMock(side_effect=AssertionError("school braucht keine Mitgliedsprüfung"))
        user = make_jwt(roles=["teacher"], sub="pseudo-teacher")
        resp = TestClient(make_app(db, user)).get(f"/context/nodes/{node.id}")
        assert resp.status_code == 200

    def test_copy_foreign_group_node_non_member_returns_403(self):
        node = _group_node()
        db = AsyncMock()
        db.get = AsyncMock(return_value=node)
        db.execute = AsyncMock(return_value=_exec_result(scalar=None))
        user = make_jwt(roles=["teacher"], sub="fremde-lehrkraft")
        resp = TestClient(make_app(db, user)).post(f"/context/nodes/{node.id}/copy", json={})
        assert resp.status_code == 403

    def test_create_node_ignores_client_owner_override(self):
        import app.context.router as ctx_router_mod
        original_cn = ctx_router_mod.ContextNode
        captured = {}

        class FakeContextNode:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
                from datetime import datetime, timezone
                self.id = uuid4()
                self.status = "active"
                self.embedding = None
                self.archived_at = None
                self.created_at = datetime.now(timezone.utc)
                self.updated_at = datetime.now(timezone.utc)
                captured["node"] = self

        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda n: None)
        ctx_router_mod.ContextNode = FakeContextNode
        try:
            user = make_jwt(roles=["teacher"], sub="echte-lehrkraft")
            resp = TestClient(make_app(db, user)).post(
                "/context/nodes",
                json={
                    "category": "concept", "content_type": "funktion", "title": "x",
                    "owner_pseudonym": "fremdes-pseudonym",
                },
            )
            assert resp.status_code == 201
            assert captured["node"].owner_pseudonym == "echte-lehrkraft"  # Override ignoriert
        finally:
            ctx_router_mod.ContextNode = original_cn


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


# ── POST /context/curricula/new ──────────────────────────────────────────────

def _exec_result(*, fetchone=None, scalar=None):
    """Hilfsobjekt für db.execute()-Rückgaben."""
    m = MagicMock()
    m.fetchone.return_value = fetchone
    m.scalar_one_or_none.return_value = scalar
    return m


def _make_curriculum_db(execute_results, *, fachplan_node=None):
    """Baut ein AsyncMock-DB mit sequenziellen execute()-Ergebnissen.

    execute_results: sequenzielle Rückgaben für db.execute()
    fachplan_node:   Rückgabe für db.get() (Fachplan-Lookup per UUID)
    """
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock(side_effect=execute_results)
    db.get = AsyncMock(return_value=fachplan_node)

    from datetime import datetime, timezone

    async def _refresh(obj):
        if not hasattr(obj, "id") or obj.id is None:
            import uuid
            obj.id = uuid.uuid4()
        if not hasattr(obj, "created_at") or obj.created_at is None:
            obj.created_at = datetime.now(timezone.utc)
        if not hasattr(obj, "updated_at") or obj.updated_at is None:
            obj.updated_at = datetime.now(timezone.utc)

    db.refresh = _refresh
    return db


FACHPLAN_UUID = str(uuid4())

VALID_CURRICULUM_PAYLOAD = {
    "fach_code": "ETH",
    "schulart": "Gymnasium",
    "jahrgangsstufe": "7",
    "bp_version": "2016",
    "schule": "Testschule",
    "fachplan_node_id": FACHPLAN_UUID,  # Node-UUID, nicht metadata.fachplan_id
}


class TestCreateCurriculumNode:

    def test_unknown_fach_returns_422(self):
        # fachplan_node=None → db.get() None → 422
        db = _make_curriculum_db([], fachplan_node=None)
        user = make_jwt(roles=["teacher"])
        client = TestClient(make_app(db, user))
        resp = client.post("/context/curricula/new", json=VALID_CURRICULUM_PAYLOAD)
        assert resp.status_code == 422
        assert "Bildungsplan" in resp.json()["detail"]

    def test_no_subject_on_fachplan_returns_422(self):
        fp = make_node(content_type="fachplan")
        fp.subject_id = None
        db = _make_curriculum_db([], fachplan_node=fp)
        user = make_jwt(roles=["teacher"])
        client = TestClient(make_app(db, user))
        resp = client.post("/context/curricula/new", json=VALID_CURRICULUM_PAYLOAD)
        assert resp.status_code == 422
        assert "Fachplan" in resp.json()["detail"]

    def test_non_member_without_dept_group_proceeds(self):
        """Wenn keine Fachschaft-Gruppe existiert, wird die Mitgliedschaftsprüfung übersprungen."""
        fp = make_node(content_type="fachplan")
        fp.subject_id = 42
        db = _make_curriculum_db(
            [
                _exec_result(fetchone=None),   # kein dept group → kein Check
                _exec_result(scalar=None),     # kein existing node
            ],
            fachplan_node=fp,
        )
        user = make_jwt(roles=["teacher"], sub="pseudo-teacher")
        client = TestClient(make_app(db, user))
        resp = client.post("/context/curricula/new", json=VALID_CURRICULUM_PAYLOAD)
        assert resp.status_code == 201

    def test_non_member_with_dept_group_returns_403(self):
        fp = make_node(content_type="fachplan")
        fp.subject_id = 42
        dept_id = 99
        db = _make_curriculum_db(
            [
                _exec_result(fetchone=(dept_id,)),  # dept group
                _exec_result(scalar=None),          # kein Mitglied
            ],
            fachplan_node=fp,
        )
        user = make_jwt(roles=["teacher"], sub="pseudo-teacher")
        client = TestClient(make_app(db, user))
        resp = client.post("/context/curricula/new", json=VALID_CURRICULUM_PAYLOAD)
        assert resp.status_code == 403

    def test_no_fachplan_returns_422(self):
        db = _make_curriculum_db([], fachplan_node=None)
        user = make_jwt(roles=["teacher"], sub="pseudo-teacher")
        client = TestClient(make_app(db, user))
        resp = client.post("/context/curricula/new", json=VALID_CURRICULUM_PAYLOAD)
        assert resp.status_code == 422
        assert "Bildungsplan" in resp.json()["detail"]

    def test_admin_bypasses_membership_check(self):
        fp = make_node(content_type="fachplan")
        fp.subject_id = 42
        dept_id = 99
        db = _make_curriculum_db(
            [
                _exec_result(fetchone=(dept_id,)),  # dept group
                _exec_result(scalar=None),          # kein Mitglied
                _exec_result(scalar=None),          # kein existing node
            ],
            fachplan_node=fp,
        )
        user = make_jwt(roles=["teacher", "admin"], sub="pseudo-admin")
        client = TestClient(make_app(db, user))
        resp = client.post("/context/curricula/new", json=VALID_CURRICULUM_PAYLOAD)
        assert resp.status_code == 201

    def test_idempotency_returns_existing_node(self):
        fp = make_node(content_type="fachplan")
        fp.subject_id = 42
        dept_id = 99
        existing = make_node(content_type="curriculum")
        db = _make_curriculum_db(
            [
                _exec_result(fetchone=(dept_id,)),  # dept group
                _exec_result(scalar=1),             # Mitglied
                _exec_result(scalar=existing),      # bereits vorhanden → zurückliefern
            ],
            fachplan_node=fp,
        )
        user = make_jwt(roles=["teacher"], sub="pseudo-teacher")
        client = TestClient(make_app(db, user))
        resp = client.post("/context/curricula/new", json=VALID_CURRICULUM_PAYLOAD)
        assert resp.status_code == 201
        assert resp.json()["id"] == str(existing.id)

    def test_valid_payload_creates_node_and_returns_201(self):
        from uuid import UUID
        fp = make_node(content_type="fachplan", id=UUID(FACHPLAN_UUID))
        fp.subject_id = 42
        fp.metadata_ = {"fachplan_id": "BP2016_GYM_ETH"}  # Geschäftsschlüssel
        db = _make_curriculum_db(
            [
                _exec_result(fetchone=None),   # kein dept group → kein Check
                _exec_result(scalar=None),     # kein existing node
            ],
            fachplan_node=fp,
        )
        user = make_jwt(roles=["teacher"], sub="pseudo-teacher")
        client = TestClient(make_app(db, user))
        resp = client.post("/context/curricula/new", json=VALID_CURRICULUM_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["content_type"] == "curriculum"
        assert body["metadata"]["fach_code"] == "ETH"
        assert body["metadata"]["jahrgangsstufe"] == "7"
        assert body["metadata"]["bp_version"] == "2016"
        # Geschäftsschlüssel kommt vom Fachplan-Knoten, nicht aus dem Payload
        assert body["metadata"]["fachplan_id"] == "BP2016_GYM_ETH"
        # Node-UUID des Fachplans wird separat abgelegt
        assert body["metadata"]["fachplan_node_id"] == FACHPLAN_UUID


class TestGetSubjectByFachCode:
    """GET /context/subjects/by-code/{fach_code} — Auflösung über subjects.fach_code."""

    def test_resolves_fach_code_to_subject(self):
        # db.execute(...).fetchone() liefert (subject_id, slug)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_exec_result(fetchone=(42, "chemie")))
        client = TestClient(make_app(db, make_jwt(roles=["teacher"])))
        resp = client.get("/context/subjects/by-code/CH")
        assert resp.status_code == 200
        assert resp.json() == {"subject_id": 42, "subject_slug": "chemie"}

    def test_lowercase_input_is_normalized(self):
        # Eingabe 'ch' wird auf 'CH' normalisiert — Resolver matcht trotzdem.
        captured = {}

        async def _exec(stmt):
            captured["stmt"] = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            return _exec_result(fetchone=(42, "chemie"))

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=_exec)
        client = TestClient(make_app(db, make_jwt(roles=["teacher"])))
        resp = client.get("/context/subjects/by-code/ch")
        assert resp.status_code == 200
        # Es wird gegen den Großbuchstaben-Code gefiltert, nicht gegen den Slug.
        assert "'CH'" in captured["stmt"]
        assert "fach_code" in captured["stmt"]

    def test_unknown_fach_code_returns_404(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_exec_result(fetchone=None))
        client = TestClient(make_app(db, make_jwt(roles=["teacher"])))
        resp = client.get("/context/subjects/by-code/XYZ")
        assert resp.status_code == 404
