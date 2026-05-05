import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.auth.audit import upsert_pseudonym_audit
from app.auth.base import NormalizedIdentity
from app.auth.config import SsoGroupPatterns, SsoConfig
from app.auth.dependencies import get_auth_adapter, get_jwt_service
from app.auth.group_sync import sync_groups
from app.auth.jwt import JwtService
from app.auth.pseudonym import pseudonymize
from app.auth.router import router as auth_router
from app.db.session import get_db
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

os.environ["JWT_SECRET"] = "test-secret-123"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["SCHOOL_SECRET"] = "test-school-secret"
os.environ["ENVIRONMENT"] = "development"

_TEST_SECRET = "test-secret-123"
_SCHOOL_SECRET = "test-school-secret"


def _make_jwt_service() -> JwtService:
    return JwtService(secret=_TEST_SECRET, algorithm="HS256")


def _no_revocation_db():
    async def override():
        db = AsyncMock()
        db.add = MagicMock()
        db.get.return_value = None
        yield db

    return override


# Fixtures for login/callback tests
@pytest.fixture
def mock_direct_adapter():
    """Mock adapter with mode='direct' that returns a test identity."""
    adapter = AsyncMock()
    adapter.mode = "direct"
    return adapter


@pytest.fixture
def mock_redirect_adapter():
    """Mock adapter with mode='redirect' that returns a test identity."""
    adapter = AsyncMock()
    adapter.mode = "redirect"
    return adapter


@pytest.fixture
def test_identity():
    """Sample NormalizedIdentity for testing."""
    return NormalizedIdentity(
        external_id="test_user_123",
        roles=["student"],
        grade="10"
    )


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def jwt_service():
    return _make_jwt_service()


@pytest.fixture
def valid_token(jwt_service):
    token, _ = jwt_service.issue("test_pseudo", ["student"], "10")
    return token


@pytest.fixture
def app_no_revocation():
    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_jwt_service] = _make_jwt_service
    app.dependency_overrides[get_db] = _no_revocation_db()
    return app


class TestAuthRouterUnauthenticated:
    """Error-path tests that reject before any DB access."""

    @pytest.fixture
    def client(self, app_no_revocation):
        return TestClient(app_no_revocation, raise_server_exceptions=False)

    def test_me_without_cookie(self, client):
        response = client.get("/me")
        assert response.status_code == 401
        assert "Nicht authentifiziert" in response.json()["detail"]

    def test_me_with_invalid_token(self, client):
        client.cookies.set("session", "invalid.token.here")
        response = client.get("/me")
        assert response.status_code == 401
        assert "Ungültiger Token" in response.json()["detail"]

    def test_me_with_expired_token(self, client):
        now = datetime.now(timezone.utc)
        expired_payload = {
            "sub": "test_user",
            "roles": ["student"],
            "grade": "10",
            "jti": "expired-jti",
            "iat": int((now - timedelta(days=10)).timestamp()),
            "exp": int((now - timedelta(days=5)).timestamp()),
        }
        token = jose_jwt.encode(expired_payload, _TEST_SECRET, algorithm="HS256")
        client.cookies.set("session", token)
        response = client.get("/me")
        assert response.status_code == 401
        assert "Ungültiger Token" in response.json()["detail"]

    def test_logout_without_cookie(self, client):
        response = client.post("/logout")
        assert response.status_code == 401
        assert "Nicht authentifiziert" in response.json()["detail"]

    def test_logout_with_invalid_token(self, client):
        client.cookies.set("session", "invalid.token.here")
        response = client.post("/logout")
        assert response.status_code == 401
        assert "Ungültiger Token" in response.json()["detail"]


class TestAuthRouterAuthenticated:
    """Happy-path and revocation tests; DB and JwtService are overridden."""

    def test_me_with_valid_cookie(self, app_no_revocation, valid_token):
        client = TestClient(app_no_revocation)
        client.cookies.set("session", valid_token)
        response = client.get("/me")
        assert response.status_code == 200
        data = response.json()
        assert data["pseudonym"] == "test_pseudo"
        assert data["roles"] == ["student"]
        assert data["grade"] == "10"

    def test_me_with_revoked_token(self, valid_token):
        async def revoked_db():
            db = AsyncMock()
            db.get.return_value = MagicMock()  # non-None → token revoked
            yield db

        app = FastAPI()
        app.include_router(auth_router)
        app.dependency_overrides[get_jwt_service] = _make_jwt_service
        app.dependency_overrides[get_db] = revoked_db
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("session", valid_token)
        response = client.get("/me")
        assert response.status_code == 401
        assert "Token revoziert" in response.json()["detail"]

    def test_logout_clears_cookie(self, app_no_revocation, valid_token):
        client = TestClient(app_no_revocation)
        client.cookies.set("session", valid_token)
        response = client.post("/logout")
        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert "session" in set_cookie
        assert "max-age=0" in set_cookie.lower()

    def test_logout_writes_revocation(self, valid_token):
        captured: list[AsyncMock] = []

        async def capturing_db():
            db = AsyncMock()
            db.add = MagicMock()
            db.get.return_value = None
            captured.append(db)
            yield db

        app = FastAPI()
        app.include_router(auth_router)
        app.dependency_overrides[get_jwt_service] = _make_jwt_service
        app.dependency_overrides[get_db] = capturing_db
        client = TestClient(app)
        client.cookies.set("session", valid_token)
        response = client.post("/logout")
        assert response.status_code == 200
        assert len(captured) > 0
        db = captured[-1]
        db.add.assert_called_once()
        db.commit.assert_awaited_once()


class TestLogin:
    """Tests for POST /login endpoint."""

    @pytest.fixture
    def app_with_mocks(self, mock_direct_adapter, test_identity, mock_db):
        """Create app with mocked dependencies for login tests."""
        app = FastAPI()
        app.include_router(auth_router)

        async def get_mock_adapter():
            return mock_direct_adapter

        async def get_mock_db():
            yield mock_db

        app.dependency_overrides[get_auth_adapter] = get_mock_adapter
        app.dependency_overrides[get_db] = get_mock_db
        app.dependency_overrides[get_jwt_service] = _make_jwt_service
        return app

    def test_login_success_sets_cookie(self, app_with_mocks, mock_direct_adapter, test_identity, mock_db):
        """Valid credentials -> 200 + Set-Cookie: session=..."""
        mock_direct_adapter.authenticate_direct = AsyncMock(return_value=test_identity)

        with patch("app.auth.router.pseudonymize") as mock_pseudo, \
             patch("app.auth.router.upsert_pseudonym_audit") as mock_audit, \
             patch("app.auth.router.ensure_litellm_user") as mock_ensure_user, \
             patch("app.auth.router.ensure_litellm_team_membership") as mock_ensure_team, \
             patch("app.auth.router.load_auth_config") as mock_load_config, \
             patch("app.auth.router.sync_groups") as mock_sync, \
             patch("app.auth.router.settings") as mock_settings:
            mock_settings.school_secret = _SCHOOL_SECRET
            mock_settings.environment = "development"
            mock_settings.auth_config_path = "test/path"
            mock_pseudo.return_value = "test_pseudo_abc"
            mock_audit.return_value = ("student", 10)
            mock_ensure_user.return_value = None
            mock_ensure_team.return_value = None
            mock_load_config.return_value = MagicMock(sso=SsoConfig(groups=SsoGroupPatterns()))
            mock_sync.return_value = None

            client = TestClient(app_with_mocks, raise_server_exceptions=False)
            response = client.post(
                "/login",
                json={"username": "testuser", "password": "testpass"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["display_name"] is None
            assert data["username"] == "testuser"
            set_cookie = response.headers.get("set-cookie", "")
            assert "session=" in set_cookie
            assert "HttpOnly" in set_cookie
            assert "Path=/" in set_cookie
            mock_ensure_user.assert_awaited_once_with(
                mock_db,
                "test_pseudo_abc",
                ["student"],
                "10",
                old_role="student",
                old_grade=10,
            )

    def test_login_wrong_password(self, app_with_mocks, mock_direct_adapter, mock_db):
        """authenticate_direct returns None -> 401"""
        mock_direct_adapter.authenticate_direct = AsyncMock(return_value=None)

        client = TestClient(app_with_mocks, raise_server_exceptions=False)
        response = client.post(
            "/login",
            json={"username": "testuser", "password": "wrong"}
        )
        assert response.status_code == 401
        assert "Falsche Anmeldedaten" in response.json()["detail"]

    def test_login_missing_fields(self, app_with_mocks, mock_direct_adapter, mock_db):
        """Body without password -> 400"""
        client = TestClient(app_with_mocks, raise_server_exceptions=False)
        response = client.post(
            "/login",
            json={"username": "testuser"}
        )
        assert response.status_code == 400
        assert "Missing username or password" in response.json()["detail"]

    def test_login_wrong_adapter_mode(self, mock_redirect_adapter, test_identity, mock_db):
        """Redirect adapter on /login -> 405"""
        app = FastAPI()
        app.include_router(auth_router)

        async def get_mock_adapter():
            return mock_redirect_adapter

        async def get_mock_db():
            yield mock_db

        app.dependency_overrides[get_auth_adapter] = get_mock_adapter
        app.dependency_overrides[get_db] = get_mock_db
        app.dependency_overrides[get_jwt_service] = _make_jwt_service

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/login",
            json={"username": "test", "password": "test"}
        )
        assert response.status_code == 405
        assert "Adapter unterstützt kein direktes Login" in response.json()["detail"]

    def test_login_upserts_audit(self, app_with_mocks, mock_direct_adapter, test_identity, mock_db):
        """upsert_pseudonym_audit is called on successful login"""
        mock_direct_adapter.authenticate_direct = AsyncMock(return_value=test_identity)

        with patch("app.auth.router.pseudonymize") as mock_pseudo, \
             patch("app.auth.router.upsert_pseudonym_audit") as mock_audit, \
             patch("app.auth.router.ensure_litellm_user") as mock_ensure_user, \
             patch("app.auth.router.ensure_litellm_team_membership") as mock_ensure_team, \
             patch("app.auth.router.load_auth_config") as mock_load_config, \
             patch("app.auth.router.sync_groups") as mock_sync, \
             patch("app.auth.router.settings") as mock_settings:
            mock_settings.school_secret = _SCHOOL_SECRET
            mock_settings.environment = "development"
            mock_settings.auth_config_path = "test/path"
            mock_pseudo.return_value = "test_pseudo_abc"
            mock_audit.return_value = ("student", 10)
            mock_ensure_user.return_value = None
            mock_ensure_team.return_value = None
            mock_load_config.return_value = MagicMock(sso=SsoConfig(groups=SsoGroupPatterns()))
            mock_sync.return_value = None

            client = TestClient(app_with_mocks, raise_server_exceptions=False)
            response = client.post(
                "/login",
                json={"username": "testuser", "password": "testpass"}
            )
            assert response.status_code == 200
            mock_audit.assert_called_once()

    def test_login_calls_sync_groups(self, app_with_mocks, mock_direct_adapter, mock_db):
        """POST /login ruft sync_groups mit korrekten Parametern auf."""
        identity = NormalizedIdentity(
            external_id="test_user_123",
            roles=["student"],
            grade="10",
            sso_groups=["Klasse.8a", "unterricht.8a.Mathematik"]
        )
        mock_direct_adapter.authenticate_direct = AsyncMock(return_value=identity)

        with patch("app.auth.router.pseudonymize") as mock_pseudo, \
             patch("app.auth.router.upsert_pseudonym_audit") as mock_audit, \
             patch("app.auth.router.ensure_litellm_user") as mock_ensure_user, \
             patch("app.auth.router.ensure_litellm_team_membership") as mock_ensure_team, \
             patch("app.auth.router.load_auth_config") as mock_load_config, \
             patch("app.auth.router.sync_groups") as mock_sync, \
             patch("app.auth.router.settings") as mock_settings:
            mock_settings.school_secret = _SCHOOL_SECRET
            mock_settings.environment = "development"
            mock_settings.auth_config_path = "test/path"
            mock_pseudo.return_value = "test_pseudo_abc"
            mock_audit.return_value = ("student", 10)
            mock_ensure_user.return_value = None
            mock_ensure_team.return_value = None
            mock_load_config.return_value = MagicMock(sso=SsoConfig(groups=SsoGroupPatterns()))
            mock_sync.return_value = None

            client = TestClient(app_with_mocks, raise_server_exceptions=False)
            response = client.post(
                "/login",
                json={"username": "testuser", "password": "testpass"}
            )
            assert response.status_code == 200
            mock_sync.assert_awaited_once()
            call_args = mock_sync.call_args
            assert call_args.kwargs["pseudonym"] == "test_pseudo_abc"
            assert call_args.kwargs["sso_groups"] == ["Klasse.8a", "unterricht.8a.Mathematik"]
            assert call_args.kwargs["primary_role"] == "student"


class TestCallback:
    """Tests for GET /auth/callback endpoint."""

    @pytest.fixture
    def app_with_mocks(self, mock_redirect_adapter, test_identity, mock_db):
        """Create app with mocked dependencies for callback tests."""
        app = FastAPI()
        app.include_router(auth_router)

        async def get_mock_adapter():
            return mock_redirect_adapter

        async def get_mock_db():
            yield mock_db

        app.dependency_overrides[get_auth_adapter] = get_mock_adapter
        app.dependency_overrides[get_db] = get_mock_db
        app.dependency_overrides[get_jwt_service] = _make_jwt_service
        return app

    def test_callback_success_sets_cookie(self, app_with_mocks, mock_redirect_adapter, test_identity, mock_db):
        """Valid code/state -> 200 + Cookie"""
        mock_redirect_adapter.exchange_code = AsyncMock(return_value=test_identity)

        with patch("app.auth.router.pseudonymize") as mock_pseudo, \
             patch("app.auth.router.upsert_pseudonym_audit") as mock_audit, \
             patch("app.auth.router.ensure_litellm_user") as mock_ensure_user, \
             patch("app.auth.router.ensure_litellm_team_membership") as mock_ensure_team, \
             patch("app.auth.router.load_auth_config") as mock_load_config, \
             patch("app.auth.router.sync_groups") as mock_sync, \
             patch("app.auth.router.settings") as mock_settings:
            mock_settings.school_secret = _SCHOOL_SECRET
            mock_settings.environment = "development"
            mock_settings.auth_config_path = "test/path"
            mock_pseudo.return_value = "test_pseudo_abc"
            mock_audit.return_value = ("student", 10)
            mock_ensure_user.return_value = None
            mock_ensure_team.return_value = None
            mock_load_config.return_value = MagicMock(sso=SsoConfig(groups=SsoGroupPatterns()))
            mock_sync.return_value = None

            client = TestClient(app_with_mocks, raise_server_exceptions=False)
            response = client.get("/callback?code=test_code&state=test_state")
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["display_name"] is None
            set_cookie = response.headers.get("set-cookie", "")
            assert "session=" in set_cookie

    def test_callback_missing_params(self, app_with_mocks, mock_redirect_adapter, mock_db):
        """No code -> 400"""
        client = TestClient(app_with_mocks, raise_server_exceptions=False)
        response = client.get("/callback?state=test_state")
        assert response.status_code == 400
        assert "Missing code or state" in response.json()["detail"]

    def test_callback_wrong_adapter_mode(self, mock_direct_adapter, test_identity, mock_db):
        """Direct adapter on /callback -> 405"""
        app = FastAPI()
        app.include_router(auth_router)

        async def get_mock_adapter():
            return mock_direct_adapter

        async def get_mock_db():
            yield mock_db

        app.dependency_overrides[get_auth_adapter] = get_mock_adapter
        app.dependency_overrides[get_db] = get_mock_db
        app.dependency_overrides[get_jwt_service] = _make_jwt_service

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/callback?code=test&state=test")
        assert response.status_code == 405
        assert "Adapter unterstützt kein OIDC-Callback" in response.json()["detail"]

    def test_callback_exchange_error(self, app_with_mocks, mock_redirect_adapter, mock_db):
        """exchange_code raises exception -> 401"""
        mock_redirect_adapter.exchange_code = AsyncMock(side_effect=Exception("Auth failed"))

        client = TestClient(app_with_mocks, raise_server_exceptions=False)
        response = client.get("/callback?code=test&state=test")
        assert response.status_code == 401
        assert "Authentifizierung fehlgeschlagen" in response.json()["detail"]

    def test_callback_calls_sync_groups(self, app_with_mocks, mock_redirect_adapter, mock_db):
        """GET /callback ruft sync_groups mit korrekten Parametern auf."""
        identity = NormalizedIdentity(
            external_id="test_user_456",
            roles=["teacher"],
            grade=None,
            sso_groups=["FS.Mathematik", "Klasse.10b", "unterricht.10b.Physik"]
        )
        mock_redirect_adapter.exchange_code = AsyncMock(return_value=identity)

        with patch("app.auth.router.pseudonymize") as mock_pseudo, \
             patch("app.auth.router.upsert_pseudonym_audit") as mock_audit, \
             patch("app.auth.router.ensure_litellm_user") as mock_ensure_user, \
             patch("app.auth.router.ensure_litellm_team_membership") as mock_ensure_team, \
             patch("app.auth.router.load_auth_config") as mock_load_config, \
             patch("app.auth.router.sync_groups") as mock_sync, \
             patch("app.auth.router.settings") as mock_settings:
            mock_settings.school_secret = _SCHOOL_SECRET
            mock_settings.environment = "development"
            mock_settings.auth_config_path = "test/path"
            mock_pseudo.return_value = "test_pseudo_xyz"
            mock_audit.return_value = ("teacher", None)
            mock_ensure_user.return_value = None
            mock_ensure_team.return_value = None
            mock_load_config.return_value = MagicMock(sso=SsoConfig(groups=SsoGroupPatterns()))
            mock_sync.return_value = None

            client = TestClient(app_with_mocks, raise_server_exceptions=False)
            response = client.get("/callback?code=test_code&state=test_state")
            assert response.status_code == 200
            mock_sync.assert_awaited_once()
            call_args = mock_sync.call_args
            assert call_args.kwargs["pseudonym"] == "test_pseudo_xyz"
            assert call_args.kwargs["sso_groups"] == ["FS.Mathematik", "Klasse.10b", "unterricht.10b.Physik"]
            assert call_args.kwargs["primary_role"] == "teacher"
