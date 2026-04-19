import hashlib
import hmac

import pytest

from app.auth.pseudonym import pseudonymize


class TestPseudonymize:
    def test_pseudonymize_deterministic(self):
        external_id = "user123"
        secret = "my-secret"
        result1 = pseudonymize(external_id, secret)
        result2 = pseudonymize(external_id, secret)
        assert result1 == result2

    def test_pseudonymize_different_external_ids(self):
        secret = "my-secret"
        result1 = pseudonymize("user1", secret)
        result2 = pseudonymize("user2", secret)
        assert result1 != result2

    def test_pseudonymize_different_secrets(self):
        external_id = "user123"
        result1 = pseudonymize(external_id, "secret1")
        result2 = pseudonymize(external_id, "secret2")
        assert result1 != result2

    def test_pseudonymize_returns_hex_string(self):
        result = pseudonymize("user123", "my-secret")
        assert len(result) == 64  # SHA-256 hex digest length
        int(result, 16)  # Verify it's a valid hex string

    def test_pseudonymize_matches_hmac_sha256(self):
        external_id = "test_user"
        secret = "test_secret"
        expected = hmac.new(
            secret.encode(), external_id.encode(), hashlib.sha256
        ).hexdigest()
        result = pseudonymize(external_id, secret)
        assert result == expected
