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
