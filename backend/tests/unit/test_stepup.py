"""Unit-Tests für app.auth.stepup (Phase 12, Schritt 5).

Step-up-Token, signierter State und auth_time-Frische — reine Funktionen.
"""

from jose import jwt

from app.auth.stepup import (
    STEPUP_AUTH_TIME_MAX_AGE,
    auth_time_is_fresh,
    is_stepup_state,
    issue_stepup_token,
    parse_stepup_state,
    sign_stepup_state,
    verify_stepup_token,
)

SECRET = "test-jwt-secret"
SCHOOL = "test-school-secret"


class TestStepupToken:
    def test_roundtrip_valid(self):
        token = issue_stepup_token(SECRET, "pseudo-a")
        assert verify_stepup_token(token, SECRET, "pseudo-a") is True

    def test_wrong_sub_rejected(self):
        token = issue_stepup_token(SECRET, "pseudo-a")
        assert verify_stepup_token(token, SECRET, "pseudo-b") is False

    def test_wrong_secret_rejected(self):
        token = issue_stepup_token(SECRET, "pseudo-a")
        assert verify_stepup_token(token, "other-secret", "pseudo-a") is False

    def test_tampered_token_rejected(self):
        token = issue_stepup_token(SECRET, "pseudo-a")
        assert verify_stepup_token(token + "x", SECRET, "pseudo-a") is False

    def test_wrong_purpose_rejected(self):
        # Ein Token ohne purpose=stepup (z. B. ein normales Token) zählt nicht.
        bogus = jwt.encode({"sub": "pseudo-a", "purpose": "other"}, SECRET, algorithm="HS256")
        assert verify_stepup_token(bogus, SECRET, "pseudo-a") is False

    def test_expired_token_rejected(self):
        expired = jwt.encode(
            {"sub": "pseudo-a", "purpose": "stepup", "exp": 1_000_000_000},
            SECRET,
            algorithm="HS256",
        )
        assert verify_stepup_token(expired, SECRET, "pseudo-a") is False


class TestStepupState:
    def test_roundtrip(self):
        state = sign_stepup_state(SCHOOL, "pseudo-a", "/welcome", "nonce123")
        assert is_stepup_state(state)
        parsed = parse_stepup_state(SCHOOL, state)
        assert parsed == ("pseudo-a", "/welcome")

    def test_roundtrip_with_path(self):
        state = sign_stepup_state(SCHOOL, "pseudo-a", "/settings/flags?x=1", "n")
        assert parse_stepup_state(SCHOOL, state) == ("pseudo-a", "/settings/flags?x=1")

    def test_tampered_signature_rejected(self):
        state = sign_stepup_state(SCHOOL, "pseudo-a", "/welcome", "nonce123")
        tampered = state[:-2] + ("00" if not state.endswith("00") else "11")
        assert parse_stepup_state(SCHOOL, tampered) is None

    def test_wrong_secret_rejected(self):
        state = sign_stepup_state(SCHOOL, "pseudo-a", "/welcome", "nonce123")
        assert parse_stepup_state("other-secret", state) is None

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
