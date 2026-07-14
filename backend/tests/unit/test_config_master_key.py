"""Unit-Tests: starker LiteLLM-Master-Key in Produktion (Sicherheits-Audit #9)."""
import os

import pytest
from pydantic import ValidationError

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.config import Settings


def _settings(**over):
    base = dict(
        database_url="postgresql+asyncpg://t:t@localhost/t",
        school_secret="s" * 32,
        jwt_secret="j" * 32,
        _env_file=None,  # reale ../.env ignorieren → isolierter Test
    )
    base.update(over)
    return Settings(**base)


def test_prod_empty_master_key_rejected():
    with pytest.raises(ValidationError):
        _settings(environment="production", litellm_master_key="")


def test_prod_placeholder_master_key_rejected():
    with pytest.raises(ValidationError):
        _settings(environment="production", litellm_master_key="sk-1234")


def test_prod_short_master_key_rejected():
    with pytest.raises(ValidationError):
        _settings(environment="production", litellm_master_key="sk-tooshort")


def test_prod_strong_master_key_ok():
    s = _settings(environment="production", litellm_master_key="sk-" + "a1B2c3D4" * 5)
    assert s.environment == "production"


def test_dev_weak_master_key_allowed():
    # Lokaler Dev-Proxy darf den schwachen Key behalten.
    s = _settings(environment="development", litellm_master_key="sk-1234")
    assert s.litellm_master_key == "sk-1234"
