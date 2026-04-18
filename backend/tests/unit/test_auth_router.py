import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

from app.auth.dependencies import get_jwt_service
from app.auth.jwt import JwtPayload, JwtService
from app.auth.router import router as auth_router
from app.db.session import get_db

os.environ["JWT_SECRET"] = "test-secret-123"
os.environ["JWT_ALGORITHM"] = "HS256"

_TEST_SECRET = "test-secret-123"


def _make_jwt_service() -> JwtService:
    return JwtService(secret=_TEST_SECRET, algorithm="HS256")


def _no_revocation_db():
    async def override():
        db = AsyncMock()
        db.add = MagicMock()
        db.get.return_value = None
        yield db
    return override


@pytest.fixture
def jwt_service():
    return _make_jwt_service()


@pytest.fixture
def valid_token(jwt_service):
    token, _ = jwt_service.issue("test_pseudo", "student", "10")
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
            "role": "student",
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
        assert data["role"] == "student"
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
