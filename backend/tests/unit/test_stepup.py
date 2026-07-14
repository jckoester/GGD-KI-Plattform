"""Unit-Tests für app.auth.stepup (Phase 12 / Sicherheits-Audit #3).

Step-up-Token (an Aktion+Ressource+jti gebunden), signierter State und auth_time-Frische.
"""

from jose import jwt

from app.auth.stepup import (
    STEPUP_AUTH_TIME_MAX_AGE,
    auth_time_is_fresh,
    decode_stepup_token,
    is_stepup_state,
    issue_stepup_token,
    parse_stepup_state,
    sign_stepup_state,
)

SECRET = "test-jwt-secret"
SCHOOL = "test-school-secret"


class TestStepupToken:
    def test_roundtrip_valid(self):
        token = issue_stepup_token(SECRET, "pseudo-a", "approve", "rid-1")
        claims = decode_stepup_token(token, SECRET)
        assert claims is not None
        assert claims["sub"] == "pseudo-a"
        assert claims["action"] == "approve"
        assert claims["resource_id"] == "rid-1"
        assert claims["jti"]  # eindeutige jti für Einmalverwendung

    def test_wrong_secret_rejected(self):
        token = issue_stepup_token(SECRET, "pseudo-a", "approve", "rid-1")
        assert decode_stepup_token(token, "other-secret") is None

    def test_tampered_token_rejected(self):
        token = issue_stepup_token(SECRET, "pseudo-a", "approve", "rid-1")
        assert decode_stepup_token(token + "x", SECRET) is None

    def test_wrong_purpose_rejected(self):
        bogus = jwt.encode({"sub": "pseudo-a", "purpose": "other"}, SECRET, algorithm="HS256")
        assert decode_stepup_token(bogus, SECRET) is None

    def test_expired_token_rejected(self):
        expired = jwt.encode(
            {"sub": "pseudo-a", "purpose": "stepup", "exp": 1_000_000_000},
            SECRET, algorithm="HS256",
        )
        assert decode_stepup_token(expired, SECRET) is None

    def test_unique_jti_per_token(self):
        c1 = decode_stepup_token(issue_stepup_token(SECRET, "a", "approve", "r"), SECRET)
        c2 = decode_stepup_token(issue_stepup_token(SECRET, "a", "approve", "r"), SECRET)
        assert c1["jti"] != c2["jti"]


class TestStepupState:
    def test_roundtrip(self):
        state = sign_stepup_state(SCHOOL, "pseudo-a", "/welcome", "nonce123", "approve", "rid-9")
        assert is_stepup_state(state)
        assert parse_stepup_state(SCHOOL, state) == ("pseudo-a", "/welcome", "approve", "rid-9")

    def test_roundtrip_with_path(self):
        state = sign_stepup_state(SCHOOL, "pseudo-a", "/review?x=1", "n", "deny", "rid-2")
        assert parse_stepup_state(SCHOOL, state) == ("pseudo-a", "/review?x=1", "deny", "rid-2")

    def test_tampered_signature_rejected(self):
        state = sign_stepup_state(SCHOOL, "pseudo-a", "/welcome", "nonce123", "approve", "rid")
        tampered = state[:-2] + ("00" if not state.endswith("00") else "11")
        assert parse_stepup_state(SCHOOL, tampered) is None

    def test_wrong_secret_rejected(self):
        state = sign_stepup_state(SCHOOL, "pseudo-a", "/welcome", "nonce123", "approve", "rid")
        assert parse_stepup_state("other-secret", state) is None

    def test_action_binding_survives_roundtrip(self):
        # Aktion/Ressource sind mitsigniert → Manipulation an ihnen bricht die Signatur.
        state = sign_stepup_state(SCHOOL, "p", "/welcome", "n", "read", "rid-x")
        parts = state.split(".")
        parts[4] = "approve"   # action fälschen
        assert parse_stepup_state(SCHOOL, ".".join(parts)) is None

    def test_non_stepup_state_rejected(self):
        assert is_stepup_state("nonce.signature") is False
        assert parse_stepup_state(SCHOOL, "nonce.signature") is None

    def test_none_state(self):
        assert is_stepup_state(None) is False


class TestAuthTimeFreshness:
    def test_fresh(self):
        now = 1_000_000
        assert auth_time_is_fresh(now - 30, now) is True

    def test_at_boundary(self):
        now = 1_000_000
        assert auth_time_is_fresh(now - STEPUP_AUTH_TIME_MAX_AGE, now) is True

    def test_stale(self):
        now = 1_000_000
        assert auth_time_is_fresh(now - STEPUP_AUTH_TIME_MAX_AGE - 1, now) is False

    def test_none(self):
        assert auth_time_is_fresh(None, 1_000_000) is False

    def test_future_rejected(self):
        now = 1_000_000
        assert auth_time_is_fresh(now + 60, now) is False
