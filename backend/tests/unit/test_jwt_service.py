import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from jose import JWTError

from app.auth.jwt import JwtPayload, JwtService


@pytest.fixture
def jwt_service():
    return JwtService(secret="test-secret-123", algorithm="HS256", ttl_days=30)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()  # db.add() is synchronous in SQLAlchemy
    return db


class TestJwtServiceIssue:
    def test_issue_returns_token_and_jti(self, jwt_service):
        token, jti = jwt_service.issue("test_pseudo", ["student"], "10")
        assert isinstance(token, str)
        assert len(token) > 0
        assert len(jti) == 36  # UUID4 string length

    def test_issue_with_none_grade(self, jwt_service):
        token, jti = jwt_service.issue("test_pseudo", ["teacher"], None)
        assert isinstance(token, str)
        assert len(jti) == 36


class TestJwtServiceVerify:
    def test_verify_decodes_correctly(self, jwt_service):
        token, jti = jwt_service.issue("test_pseudo", ["student"], "10")
        payload = jwt_service.verify(token)
        assert payload.sub == "test_pseudo"
        assert payload.roles == ["student"]
        assert payload.grade == "10"
        assert payload.jti == jti
        assert payload.iat > 0
        assert payload.exp > payload.iat

    def test_verify_rejects_expired_token(self, jwt_service):
        # Create a service with very short TTL to test expiration
        short_service = JwtService(secret="test-secret-123", algorithm="HS256", ttl_days=0)
        # Force expiration by setting exp to a timestamp in the past
        from jose import jwt as jose_jwt
        import time
        expired_token = jose_jwt.encode(
            {
                "sub": "test_pseudo",
                "roles": ["student"],
                "grade": "10",
                "jti": "test-jti",
                "iat": int(time.time()) - 100,  # 100 seconds ago
                "exp": int(time.time()) - 50,   # expired 50 seconds ago
            },
            "test-secret-123",
            algorithm="HS256"
        )
        with pytest.raises(JWTError):
            short_service.verify(expired_token)

    def test_verify_rejects_wrong_signature(self, jwt_service):
        wrong_service = JwtService(secret="wrong-secret-456", algorithm="HS256")
        wrong_token = wrong_service.issue("test_pseudo", ["student"], "10")[0]
        with pytest.raises(JWTError):
            jwt_service.verify(wrong_token)

    def test_verify_rejects_tampered_payload(self, jwt_service):
        token, _ = jwt_service.issue("test_pseudo", ["student"], "10")
        # Tamper with the token by changing a character
        tampered_token = token[:-5] + "xxxxx"
        with pytest.raises(JWTError):
            jwt_service.verify(tampered_token)


class TestJwtServiceRevoke:
    @pytest.mark.asyncio
    async def test_revoke_writes_to_db(self, jwt_service, mock_db):
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        # Make commit async
        mock_db.commit = AsyncMock()
        await jwt_service.revoke(mock_db, "test-jti", "test_pseudo", expires_at, "test_reason")
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()


class TestJwtServiceIsRevoked:
    @pytest.mark.asyncio
    async def test_is_revoked_true_for_known_jti(self, jwt_service, mock_db):
        token, jti = jwt_service.issue("test_pseudo", ["student"], "10")
        payload = jwt_service.verify(token)
        
        # Mock db.get to return a revocation record
        mock_revocation = MagicMock()
        mock_db.get.return_value = mock_revocation
        
        result = await jwt_service.is_revoked(mock_db, payload)
        mock_db.get.assert_called_once()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_revoked_false_for_unknown_jti(self, jwt_service, mock_db):
        token, _ = jwt_service.issue("test_pseudo", ["student"], "10")
        payload = jwt_service.verify(token)
        
        # Mock db.get to return None for both lookups
        mock_db.get.side_effect = [None, MagicMock(revoked_all_before=None)]
        
        result = await jwt_service.is_revoked(mock_db, payload)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_revoked_true_for_mass_revocation(self, jwt_service, mock_db):
        token, _ = jwt_service.issue("test_pseudo", ["student"], "10")
        payload = jwt_service.verify(token)
        
        # Create an iat that is before the revoked_all_before timestamp
        early_iat = datetime.now(timezone.utc) - timedelta(days=10)
        payload.iat = int(early_iat.timestamp())
        
        # Mock db.get to return None for jti, but a PseudonymAudit with revoked_all_before
        mock_audit = MagicMock()
        mock_audit.revoked_all_before = datetime.now(timezone.utc) - timedelta(days=5)
        mock_db.get.side_effect = [None, mock_audit]
        
        result = await jwt_service.is_revoked(mock_db, payload)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_revoked_false_after_revoked_all_before(self, jwt_service, mock_db):
        token, _ = jwt_service.issue("test_pseudo", ["student"], "10")
        payload = jwt_service.verify(token)
        
        # Create an iat that is after the revoked_all_before timestamp
        recent_iat = datetime.now(timezone.utc) - timedelta(days=1)
        payload.iat = int(recent_iat.timestamp())
        
        # Mock db.get to return None for jti, but a PseudonymAudit with revoked_all_before
        mock_audit = MagicMock()
        mock_audit.revoked_all_before = datetime.now(timezone.utc) - timedelta(days=5)
        mock_db.get.side_effect = [None, mock_audit]
        
        result = await jwt_service.is_revoked(mock_db, payload)
        assert result is False
