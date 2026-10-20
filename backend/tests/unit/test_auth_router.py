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

    def test_me_returns_sso_groups_and_roles(self, app_no_revocation, jwt_service):
        """/me liefert die rohen SSO-Gruppen/-Rollen für die Profil-Diagnose."""
        token, _ = jwt_service.issue(
            "test_pseudo", ["teacher"], None,
            sso_groups=["Kollegium", "FS.Mathematik"], sso_roles=["Lehrer"],
        )
        client = TestClient(app_no_revocation)
        client.cookies.set("session", token)
        response = client.get("/me")
        assert response.status_code == 200
        data = response.json()
        assert data["sso_groups"] == ["Kollegium", "FS.Mathematik"]
        assert data["sso_roles"] == ["Lehrer"]

    def test_me_sso_fields_default_empty_for_legacy_token(
        self, app_no_revocation, valid_token
    ):
        """Alt-Token ohne SSO-Felder: /me liefert leere Listen (kein Fehler)."""
        client = TestClient(app_no_revocation)
        client.cookies.set("session", valid_token)
        data = client.get("/me").json()
        assert data["sso_groups"] == []
        assert data["sso_roles"] == []

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

    def test_logout_clears_session_and_stepup_cookies(self, app_no_revocation, valid_token):
        # Audit #12: Logout löscht auch das stepup-Cookie, beide mit Path=/.
        client = TestClient(app_no_revocation)
        client.cookies.set("session", valid_token)
        response = client.post("/logout")
        assert response.status_code == 200
        cookies = "\n".join(response.headers.get_list("set-cookie")).lower()
        assert "session=" in cookies
        assert "stepup=" in cookies
        # Beide werden gelöscht (max-age=0) und mit Path=/ überschrieben.
        assert cookies.count("max-age=0") >= 2
        assert cookies.count("path=/") >= 2

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
            client.cookies.set("oauth_login", "test_state|verifier123")  # Browser-Bindung (Audit #4)
            response = client.get(
                "/callback?code=test_code&state=test_state", follow_redirects=False
            )
            # Erfolg → 303-Redirect auf /welcome (Frontend-Route) mit Session-Cookie
            assert response.status_code == 303
            assert response.headers["location"] == "/welcome"
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
        client.cookies.set("oauth_login", "test|verifier123")  # Bindung ok → erreicht exchange_code
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
            client.cookies.set("oauth_login", "test_state|verifier123")  # Browser-Bindung (Audit #4)
            response = client.get(
                "/callback?code=test_code&state=test_state", follow_redirects=False
            )
            assert response.status_code == 303
            mock_sync.assert_awaited_once()
            call_args = mock_sync.call_args
            assert call_args.kwargs["pseudonym"] == "test_pseudo_xyz"
            assert call_args.kwargs["sso_groups"] == ["FS.Mathematik", "Klasse.10b", "unterricht.10b.Physik"]
            assert call_args.kwargs["primary_role"] == "teacher"

    def test_callback_missing_binding_cookie_401(self, app_with_mocks, mock_redirect_adapter, mock_db):
        """Kein Browser-Bindungs-Cookie → 401, exchange_code wird nicht erreicht (Login-CSRF, Audit #4)."""
        mock_redirect_adapter.exchange_code = AsyncMock()
        client = TestClient(app_with_mocks, raise_server_exceptions=False)
        response = client.get("/callback?code=test&state=test_state")
        assert response.status_code == 401
        mock_redirect_adapter.exchange_code.assert_not_awaited()

    def test_callback_state_cookie_mismatch_401(self, app_with_mocks, mock_redirect_adapter, mock_db):
        """State im Cookie ≠ State in der Query → 401 (fremder Login untergeschoben)."""
        mock_redirect_adapter.exchange_code = AsyncMock()
        client = TestClient(app_with_mocks, raise_server_exceptions=False)
        client.cookies.set("oauth_login", "anderer_state|verifier123")
        response = client.get("/callback?code=test&state=test_state")
        assert response.status_code == 401
        mock_redirect_adapter.exchange_code.assert_not_awaited()


_ANTRAG = "00000000-0000-0000-0000-0000000000aa"


class TestStepupCallback:
    """Rücksprung der erneuten Anmeldung (0.18.1): Ablehnungen landen lesbar auf der
    Ausgangsseite und mit Grund im Log — vorher JSON-401 an der Callback-URL, Log leer."""

    @pytest.fixture
    def client(self, mock_redirect_adapter, jwt_service):
        from app.auth.base import FreshIdentity

        app = FastAPI()
        app.include_router(auth_router)

        async def get_mock_adapter():
            return mock_redirect_adapter

        app.dependency_overrides[get_auth_adapter] = get_mock_adapter
        app.dependency_overrides[get_db] = _no_revocation_db()
        app.dependency_overrides[get_jwt_service] = _make_jwt_service
        self.adapter = mock_redirect_adapter
        self.adapter.stepup_amr = ["mfa"]
        self.fresh = lambda auth_time, ext="lehrer_1", diagnose=None, amr=("pwd", "mfa", "otp"): FreshIdentity(
            identity=NormalizedIdentity(external_id=ext, roles=["teacher"]),
            auth_time=auth_time, diagnose=diagnose or {}, amr=list(amr) if amr is not None else None,
        )
        token, _ = jwt_service.issue(pseudonymize("lehrer_1", _SCHOOL_SECRET), ["teacher"], None)
        c = TestClient(app, raise_server_exceptions=False)
        c.cookies.set("session", token)
        with patch("app.auth.router.settings") as s:
            s.school_secret = _SCHOOL_SECRET
            s.jwt_secret = _TEST_SECRET
            s.environment = "development"
            yield c

    def _state(self, return_to="/profile", sub=None):
        from app.auth.stepup import sign_stepup_state

        sub = sub or pseudonymize("lehrer_1", _SCHOOL_SECRET)
        return sign_stepup_state(_SCHOOL_SECRET, sub, return_to, "n0nce", "read", _ANTRAG)

    def _jetzt(self):
        return int(datetime.now(timezone.utc).timestamp())

    def test_erfolg_setzt_cookie_und_springt_zurueck(self, client):
        self.adapter.exchange_code_fresh = AsyncMock(return_value=self.fresh(self._jetzt() - 5))
        r = client.get(f"/callback?code=c&state={self._state()}", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/profile"
        assert "stepup=" in r.headers.get("set-cookie", "")

    def test_alt_nennt_alter_und_diagnose(self, client, caplog):
        diagnose = {"id_token": True, "signatur": "ungeprueft", "claims": ["auth_time", "sub"]}
        self.adapter.exchange_code_fresh = AsyncMock(
            return_value=self.fresh(self._jetzt() - 3600, diagnose=diagnose))
        with caplog.at_level("WARNING", logger="app.auth.router"):
            r = client.get(f"/callback?code=c&state={self._state()}", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/profile?stepup_fehler=nicht_frisch"
        assert "stepup=" not in r.headers.get("set-cookie", "")
        zeile = next(m for m in caplog.messages if "Step-up abgelehnt" in m)
        assert "(nicht_frisch)" in zeile and "aktion=read" in zeile
        assert "alter_s=3600" in zeile or "alter_s=3601" in zeile
        assert "'claims': ['auth_time', 'sub']" in zeile

    def test_zukunft_als_negatives_alter(self, client, caplog):
        self.adapter.exchange_code_fresh = AsyncMock(return_value=self.fresh(self._jetzt() + 30))
        with caplog.at_level("WARNING", logger="app.auth.router"):
            r = client.get(f"/callback?code=c&state={self._state()}", follow_redirects=False)
        assert r.headers["location"].endswith("stepup_fehler=nicht_frisch")
        assert any("alter_s=-" in m for m in caplog.messages)

    def test_ohne_auth_time_mit_2fa_angenommen(self, client, caplog):
        """0.19 Schritt 4b: Das Schulkonto liefert kein auth_time, beachtet aber prompt=login
        (Passwort + 2FA, auf Prod geprüft 19.10.2026). Dann zählt der Rücksprung — mit Logzeile."""
        self.adapter.exchange_code_fresh = AsyncMock(return_value=self.fresh(None))
        with caplog.at_level("INFO", logger="app.auth.router"):
            r = client.get(f"/callback?code=c&state={self._state()}", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/profile"
        assert "stepup=" in r.headers.get("set-cookie", "")
        assert any("Vertrauen auf prompt=login" in m and "aktion=read" in m for m in caplog.messages)

    @pytest.mark.parametrize("amr", [["pwd"], None, []])
    def test_ohne_zweiten_faktor_abgelehnt(self, client, caplog, amr):
        self.adapter.exchange_code_fresh = AsyncMock(return_value=self.fresh(None, amr=amr))
        with caplog.at_level("WARNING", logger="app.auth.router"):
            r = client.get(f"/callback?code=c&state={self._state()}", follow_redirects=False)
        assert r.headers["location"] == "/profile?stepup_fehler=ohne_2fa"
        assert "stepup=" not in r.headers.get("set-cookie", "")
        assert any("(ohne_2fa)" in m and "['mfa']" in m for m in caplog.messages)

    def test_zweiter_faktor_gilt_auch_mit_auth_time(self, client):
        self.adapter.exchange_code_fresh = AsyncMock(
            return_value=self.fresh(self._jetzt() - 5, amr=["pwd"]))
        r = client.get(f"/callback?code=c&state={self._state()}", follow_redirects=False)
        assert r.headers["location"].endswith("stepup_fehler=ohne_2fa")

    def test_ohne_pflichtwerte_reicht_der_ruecksprung(self, client):
        """`stepup_amr: []` — eine Schule ohne 2FA beim Anbieter."""
        self.adapter.stepup_amr = []
        self.adapter.exchange_code_fresh = AsyncMock(return_value=self.fresh(None, amr=None))
        r = client.get(f"/callback?code=c&state={self._state()}", follow_redirects=False)
        assert r.headers["location"] == "/profile"

    def test_anderes_konto(self, client):
        self.adapter.exchange_code_fresh = AsyncMock(
            return_value=self.fresh(self._jetzt(), ext="jemand_anders"))
        r = client.get(f"/callback?code=c&state={self._state('/review?x=1')}", follow_redirects=False)
        assert r.headers["location"] == "/review?x=1&stepup_fehler=anderes_konto"

    def test_code_tausch_scheitert(self, client):
        self.adapter.exchange_code_fresh = AsyncMock(side_effect=RuntimeError("boom"))
        r = client.get(f"/callback?code=c&state={self._state()}", follow_redirects=False)
        assert r.headers["location"] == "/profile?stepup_fehler=fehlgeschlagen"

    def test_abbruch_beim_provider(self, client):
        self.adapter.exchange_code_fresh = AsyncMock()
        r = client.get(f"/callback?error=access_denied&state={self._state()}", follow_redirects=False)
        assert r.headers["location"] == "/profile?stepup_fehler=abgebrochen"
        self.adapter.exchange_code_fresh.assert_not_awaited()

    def test_gefaelschter_state_springt_nicht_ans_ziel(self, client):
        self.adapter.exchange_code_fresh = AsyncMock()
        state = self._state("/profile")[:-2] + "xx"
        r = client.get(f"/callback?code=c&state={state}", follow_redirects=False)
        assert r.headers["location"] == "/welcome?stepup_fehler=fehlgeschlagen"
        self.adapter.exchange_code_fresh.assert_not_awaited()

    def test_fremder_state_springt_mit_fehler_zurueck(self, client):
        self.adapter.exchange_code_fresh = AsyncMock()
        r = client.get(f"/callback?code=c&state={self._state(sub='fremd')}", follow_redirects=False)
        assert r.headers["location"] == "/profile?stepup_fehler=fehlgeschlagen"
        self.adapter.exchange_code_fresh.assert_not_awaited()

    def test_ohne_sitzung_zur_anmeldung(self, client):
        client.cookies.clear()
        self.adapter.exchange_code_fresh = AsyncMock()
        r = client.get(f"/callback?code=c&state={self._state()}", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/"
        self.adapter.exchange_code_fresh.assert_not_awaited()


class TestLoginRuecksprung:
    """0.18.3: Der Login führt auf Wunsch zurück — „Kurz neu anmelden" am Token-Formular."""

    @pytest.fixture
    def app_(self, mock_redirect_adapter, mock_db):
        from app.auth.base import LoginChallenge

        app = FastAPI()
        app.include_router(auth_router)

        async def get_mock_adapter():
            return mock_redirect_adapter

        async def get_mock_db():
            yield mock_db

        mock_redirect_adapter.get_login_challenge = AsyncMock(side_effect=lambda: LoginChallenge(
            type="redirect", redirect_url="https://idp/auth", state="st", code_verifier="cv"))
        app.dependency_overrides[get_auth_adapter] = get_mock_adapter
        app.dependency_overrides[get_db] = get_mock_db
        app.dependency_overrides[get_jwt_service] = _make_jwt_service
        return app

    def test_challenge_legt_ziel_ins_bindungs_cookie(self, app_):
        c = TestClient(app_)
        c.get("/login-challenge?return_to=/profile")
        assert c.cookies.get("oauth_login").strip('"') == "st|cv|/profile"

    @pytest.mark.parametrize("fremd", ["https://evil.example", "//evil.example", "/\\evil.example"])
    def test_fremdes_ziel_wird_zur_startseite(self, app_, fremd):
        c = TestClient(app_)
        c.get("/login-challenge", params={"return_to": fremd})
        assert c.cookies.get("oauth_login").strip('"') == "st|cv|/welcome"

    def _callback(self, app_, mock_redirect_adapter, test_identity, cookie):
        mock_redirect_adapter.exchange_code = AsyncMock(return_value=test_identity)
        with patch("app.auth.router.upsert_pseudonym_audit", AsyncMock(return_value=("student", 10))), \
             patch("app.auth.router.ensure_litellm_user", AsyncMock()), \
             patch("app.auth.router.ensure_litellm_team_membership", AsyncMock()), \
             patch("app.auth.router.load_auth_config") as cfg, \
             patch("app.auth.router.sync_groups", AsyncMock()):
            cfg.return_value = MagicMock(sso=SsoConfig(groups=SsoGroupPatterns()))
            c = TestClient(app_, raise_server_exceptions=False)
            c.cookies.set("oauth_login", cookie)
            return c.get("/callback?code=x&state=st", follow_redirects=False)

    def test_callback_fuehrt_zum_ziel(self, app_, mock_redirect_adapter, test_identity):
        r = self._callback(app_, mock_redirect_adapter, test_identity, "st|cv|/profile")
        assert r.status_code == 303 and r.headers["location"] == "/profile"

    def test_altes_cookie_ohne_ziel(self, app_, mock_redirect_adapter, test_identity):
        r = self._callback(app_, mock_redirect_adapter, test_identity, "st|cv")
        assert r.headers["location"] == "/welcome"

    def test_untergeschobenes_ziel_im_cookie(self, app_, mock_redirect_adapter, test_identity):
        r = self._callback(app_, mock_redirect_adapter, test_identity, "st|cv|//evil.example")
        assert r.headers["location"] == "/welcome"


@pytest.mark.parametrize("ziel,erwartet", [
    ("/profile?x=1", "/profile?x=1"),
    ("profile", "/welcome"),
    ("//evil", "/welcome"),
    ("/\\evil", "/welcome"),
    ("/a\r\nSet-Cookie: x", "/welcome"),
])
def test_safe_return_to(ziel, erwartet):
    from app.auth.router import _safe_return_to

    assert _safe_return_to(ziel) == erwartet
