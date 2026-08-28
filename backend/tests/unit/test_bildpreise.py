"""Bildpreise für LiteLLMs Kostentabelle.

Die Datei liegt in `infra/guardrails/` (dort, wo der Proxy läuft) und ist kein Python-Paket
— daher der Import über importlib, wie bei `moderation_core` (CLAUDE.md).

**Warum es dieses Modul gibt:** Für Chat und Embedding greift der Preis aus `model_info` der
LiteLLM-Config. Für Bilder nicht — LiteLLMs Bild-Kostenrechner liest nur seine eingebaute
Tabelle. Selbst eingetragene Bildmodelle kosten dadurch 0,00 $ und laufen am EUR-Budget
vorbei, ohne dass irgendetwas fehlschlägt.

Getestet wird hier das Lesen der Konfiguration, nicht `litellm.register_model` selbst —
litellm lebt nur in der Proxy-venv.
"""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_MODUL = (
    Path(__file__).resolve().parents[3] / "infra" / "guardrails" / "bildpreise.py"
)


@pytest.fixture
def bildpreise(monkeypatch):
    """Lädt das Modul mit einem Attrappen-litellm (die echte Bibliothek fehlt hier)."""
    litellm_attrappe = MagicMock()
    litellm_attrappe.integrations.custom_logger.CustomLogger = type("CustomLogger", (), {})
    monkeypatch.setitem(sys.modules, "litellm", litellm_attrappe)
    monkeypatch.setitem(sys.modules, "litellm.integrations", litellm_attrappe.integrations)
    monkeypatch.setitem(
        sys.modules,
        "litellm.integrations.custom_logger",
        litellm_attrappe.integrations.custom_logger,
    )
    # Beim Import legt das Modul `registrierung` an und registriert dabei bereits einmal.
    # Läuft vorher ein Integrationstest, hat dessen conftest per `load_dotenv()` die echte
    # .env nach os.environ geschoben — inklusive IMAGE_PRICES. Der Import zählte dann als
    # Aufruf mit, und `assert_called_once` schlüge reihenfolgeabhängig fehl.
    monkeypatch.delenv("IMAGE_PRICES", raising=False)
    spec = importlib.util.spec_from_file_location("bildpreise_test", _MODUL)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    litellm_attrappe.reset_mock()
    modul._litellm_attrappe = litellm_attrappe
    return modul


def test_ohne_konfiguration_wird_nichts_registriert(bildpreise, monkeypatch):
    """Und der Betreiber bekommt eine Warnung — sonst kostet jedes Bild still 0,00 $."""
    monkeypatch.delenv("IMAGE_PRICES", raising=False)

    assert bildpreise.registriere_bildpreise() == {}


def test_preise_werden_gelesen(bildpreise, monkeypatch):
    monkeypatch.setenv(
        "IMAGE_PRICES",
        '{"black-forest-labs/FLUX.1-schnell": 0.032, "andere/modell": 0.01}',
    )

    assert bildpreise.registriere_bildpreise() == {
        "black-forest-labs/FLUX.1-schnell": 0.032,
        "andere/modell": 0.01,
    }


def test_registriert_mit_dem_schluessel_den_litellm_sucht(bildpreise, monkeypatch):
    """`input_cost_per_image` + `mode` — beides erwartet der Bild-Kostenrechner."""
    monkeypatch.setenv("IMAGE_PRICES", '{"m": 0.032}')

    bildpreise.registriere_bildpreise()

    bildpreise._litellm_attrappe.register_model.assert_called_once_with(
        {"m": {"input_cost_per_image": 0.032, "mode": "image_generation"}}
    )


def test_kaputtes_json_bricht_den_proxy_nicht(bildpreise, monkeypatch):
    """Ein Tippfehler in der .env darf den Start nicht verhindern — er wird geloggt."""
    monkeypatch.setenv("IMAGE_PRICES", "{kein json")

    assert bildpreise.registriere_bildpreise() == {}


def test_liste_statt_objekt_wird_abgelehnt(bildpreise, monkeypatch):
    monkeypatch.setenv("IMAGE_PRICES", '["a", "b"]')

    assert bildpreise.registriere_bildpreise() == {}


def test_unbrauchbarer_preis_ueberspringt_nur_diesen_eintrag(bildpreise, monkeypatch):
    """Ein fehlerhafter Eintrag darf die übrigen nicht mitreißen."""
    monkeypatch.setenv("IMAGE_PRICES", '{"gut": 0.032, "schlecht": "teuer"}')

    assert bildpreise.registriere_bildpreise() == {"gut": 0.032}


def test_ganze_zahl_wird_akzeptiert(bildpreise, monkeypatch):
    """JSON kennt keinen Float-Zwang — `1` muss als 1.0 durchgehen."""
    monkeypatch.setenv("IMAGE_PRICES", '{"m": 1}')

    assert bildpreise.registriere_bildpreise() == {"m": 1.0}
