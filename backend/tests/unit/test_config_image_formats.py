"""Unit-Tests: Selbstkonsistenz von IMAGE_SIZES / IMAGE_DEFAULT_FORMAT.

Bewusst ein harter Startfehler statt einer stillen Korrektur: Eine Größe, für die in der
LiteLLM-Config kein Preis hinterlegt ist, wird beim Provider unter Umständen erzeugt, aber
nicht abgerechnet (Spend = 0). Das fällt sonst erst auf, wenn die Budget-Statistik nicht mehr
stimmt — also spät und schwer zuzuordnen.
"""
import os

import pytest
from pydantic import ValidationError

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.config import Settings


@pytest.fixture(autouse=True)
def ohne_image_env(monkeypatch):
    """Entfernt IMAGE_*-Variablen aus der Umgebung.

    `_env_file=None` genügt hier NICHT: Läuft vorher ein Integrationstest, hat dessen
    conftest per `load_dotenv()` die reale `.env` nach `os.environ` geschoben — und für
    **Dict-Felder** mischt pydantic-settings den Umgebungswert in den explizit
    übergebenen, statt ihn zu ersetzen. Ein `IMAGE_SIZES` in der Betreiber-`.env` machte
    aus `image_sizes={}` dann ein nicht-leeres Dict, und die Tests scheiterten mit
    „DID NOT RAISE" — abhängig von der Testreihenfolge und damit schwer zu finden.
    """
    monkeypatch.delenv("IMAGE_SIZES", raising=False)
    monkeypatch.delenv("IMAGE_DEFAULT_FORMAT", raising=False)


def _settings(**over):
    base = dict(
        database_url="postgresql+asyncpg://t:t@localhost/t",
        school_secret="s" * 32,
        jwt_secret="j" * 32,
        _env_file=None,  # reale ../.env ignorieren (reicht allein nicht, s. ohne_image_env)
    )
    base.update(over)
    return Settings(**base)


def test_defaults_are_self_consistent():
    """Die ausgelieferten Defaults müssen zusammenpassen."""
    s = _settings()
    assert s.image_default_format in s.image_sizes


def test_custom_formats_accepted():
    s = _settings(
        image_sizes={"panorama": "1344x768", "poster": "896x1152"},
        image_default_format="poster",
    )
    assert s.image_sizes["panorama"] == "1344x768"


def test_default_format_outside_image_sizes_rejected():
    with pytest.raises(ValidationError) as exc:
        _settings(
            image_sizes={"panorama": "1344x768"},
            image_default_format="quadratisch",
        )
    message = str(exc.value)
    assert "IMAGE_DEFAULT_FORMAT" in message
    # Die Meldung muss die gültigen Werte nennen, sonst rät der Betreiber.
    assert "panorama" in message


def test_empty_image_sizes_rejected():
    with pytest.raises(ValidationError) as exc:
        _settings(image_sizes={})
    assert "IMAGE_SIZES" in str(exc.value)


def test_single_format_is_enough():
    """Ein Anbieter, der nur eine Größe kann, muss konfigurierbar bleiben."""
    s = _settings(
        image_sizes={"quadratisch": "1024x1024"}, image_default_format="quadratisch"
    )
    assert list(s.image_sizes) == ["quadratisch"]
