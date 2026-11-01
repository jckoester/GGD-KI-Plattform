# Empty conftest to prevent parent conftest from being loaded
# Unit tests in this directory should not require DB or testcontainers

import pytest


@pytest.fixture(autouse=True)
def _bildarten_ohne_lokale_datei(monkeypatch):
    """Unit-Tests laufen so, als gäbe es keine `config/image_models.yaml`.

    Die Datei ist gitignored und liegt nur auf Entwicklungsrechnern. Ohne diese Fixture
    hinge das Ergebnis vieler Bild-Tests davon ab, ob sie zufällig vorhanden ist und was
    gerade darin steht — auf dem einen Rechner grün, im frischen Checkout rot.

    Ohne Datei greift die Synthese aus den `IMAGE_*`-Variablen: genau ein Bildart-Eintrag
    `standard`, gespeist aus `settings`. Das ist zugleich der Zustand einer bestehenden
    Installation nach dem Update, also der Pfad, der ohnehin getestet gehört.

    Tests, die echte Bildarten brauchen, setzen `settings.image_models_path` selbst — das
    geschieht im Test und damit nach dieser Fixture, gewinnt also.
    """
    from app.chat import image_models
    from app.config import settings

    monkeypatch.setattr(
        settings, "image_models_path", "config/__im_test_absichtlich_nicht_vorhanden__.yaml"
    )
    image_models.invalidate_image_models_cache()
    yield
    image_models.invalidate_image_models_cache()


@pytest.fixture(autouse=True)
def _ohne_begriffsvorschlag(monkeypatch):
    """Unit-Tests laufen ohne `BEGRIFFE_MODEL` (0.18) — steht es in der lokalen `.env`, löste
    jedes `update_lesson_phases` sonst einen echten Modellaufruf im Hintergrund aus. Tests,
    die den Vorschlag brauchen, setzen das Modell selbst."""
    from app.config import settings

    monkeypatch.setattr(settings, "begriffe_model", "")


@pytest.fixture(autouse=True)
def _modellfreigaben_unbekannt(monkeypatch):
    """Tests laufen so, als wären die Modell-Freigaben je Team nicht zu erfahren (0.27).

    Sonst fragte jede Sichtbarkeitsprüfung und jeder Chat den lokalen LiteLLM-Proxy nach den
    Teams — das Ergebnis hinge davon ab, ob er läuft und was auf diesem Rechner freigeschaltet
    ist. ``None`` heißt „unbekannt": nicht filtern. Tests, die Freigaben brauchen, setzen
    `Zugang.modelle` selbst oder patchen `get_team_info` im Test (das gewinnt).
    """
    from unittest.mock import AsyncMock

    from app.litellm import team_models

    team_models.invalidate_team_models_cache()
    monkeypatch.setattr(team_models._client, "get_team_info", AsyncMock(return_value=None))
    yield
    team_models.invalidate_team_models_cache()


@pytest.fixture(autouse=True)
def _audit_ohne_datenbank(monkeypatch):
    """Unit-Tests haben keine Datenbank — `audit_getrennt` prüft den Eintrag, schreibt ihn aber
    nicht. Ohne diese Fixture schrieb es in die Datenbank aus der lokalen `.env`, also die der
    Entwicklungsinstanz (0.28, 01.11.2026)."""
    from app.core import audit

    monkeypatch.setattr(audit, "SCHREIBEN", False)
