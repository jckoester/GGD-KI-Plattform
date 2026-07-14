"""Unit-Tests: starke Krypto-Geheimnisse in Produktion (Sicherheits-Audit #7).

`SCHOOL_SECRET` (HMAC-Pseudonymisierung) und `JWT_SECRET` (Auth-Cookie-Signatur)
müssen in Produktion ≥ 32 Zeichen lang und kein Platzhalter sein; in `development`
bleiben kurze Test-Werte erlaubt.
"""
import os

import pytest
from pydantic import ValidationError

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.config import Settings

# Starker Master-Key, damit der #9-Validator die Prod-Tests nicht vorher blockiert.
_STRONG_MASTER_KEY = "sk-" + "a1B2c3D4" * 5


def _settings(**over):
    base = dict(
        database_url="postgresql+asyncpg://t:t@localhost/t",
        school_secret="s" * 32,
        jwt_secret="j" * 32,
        litellm_master_key=_STRONG_MASTER_KEY,
        _env_file=None,  # reale ../.env ignorieren → isolierter Test
    )
    base.update(over)
    return Settings(**base)


def test_prod_short_school_secret_rejected():
    with pytest.raises(ValidationError):
        _settings(environment="production", school_secret="short")


def test_prod_short_jwt_secret_rejected():
    with pytest.raises(ValidationError):
        _settings(environment="production", jwt_secret="short")


def test_prod_empty_school_secret_rejected():
    with pytest.raises(ValidationError):
        _settings(environment="production", school_secret="")


def test_prod_placeholder_secret_rejected():
    with pytest.raises(ValidationError):
        _settings(environment="production", jwt_secret="changeme")


def test_prod_test_value_rejected():
    # Der Default-Testwert aus .env darf in Prod nicht durchrutschen.
    with pytest.raises(ValidationError):
        _settings(environment="production", school_secret="test-school-secret")


def test_prod_strong_secrets_ok():
    s = _settings(
        environment="production",
        school_secret="A" + "b3C4d5E6" * 5,
        jwt_secret="Z" + "y9X8w7V6" * 5,
    )
    assert s.environment == "production"


def test_prod_exactly_min_length_ok():
    # Genau _MIN_SECRET_LEN (32) Zeichen ist gültig.
    s = _settings(environment="production", school_secret="x" * 32, jwt_secret="y" * 32)
    assert len(s.school_secret) == 32


def test_dev_weak_secrets_allowed():
    # Lokale Dev/Test-Umgebung darf kurze Geheimnisse behalten.
    s = _settings(environment="development", school_secret="dev", jwt_secret="dev")
    assert s.school_secret == "dev"
