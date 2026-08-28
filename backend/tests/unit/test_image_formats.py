"""Unit-Tests: Bildformate und `response_format` sind konfigurierbar.

Zwei Dinge waren vorher hartcodiert und provider-spezifisch:

* `response_format=None` — passt zu gpt-image-1 (lehnt den Parameter ab, liefert immer
  Base64), bricht aber bei FLUX/SDXL: die liefern dann eine URL, und die verarbeitet der
  Client bewusst nicht (Datenschutzgrenze).
* Drei gpt-image-1-Pixelgrößen im Tool-Schema und in der Validierung. SDXL und FLUX kennen
  andere Größen; eine nicht abgerechnete Größe bedeutet Spend = 0 und damit wirkungslose
  Budgets.

Jetzt wählt das Modell einen **Formatnamen** aus `IMAGE_SIZES`; die Pixelgröße kommt aus der
Konfiguration.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.chat.tools import ToolContext
from app.config import settings
from app.litellm.client import ImageGenerationResult

CUSTOM_SIZES = {
    "quadratisch": "1024x1024",
    "panorama": "1344x768",
    "poster": "896x1152",
}


@pytest.fixture
def exec_image(monkeypatch):
    """Ruft _exec_generate_image mit gemocktem Client auf; liefert (result, call_kwargs)."""

    async def _run(args, **settings_overrides):
        from app.chat import router

        for key, value in settings_overrides.items():
            monkeypatch.setattr(settings, key, value)

        instance = MagicMock()
        instance.generate_image = AsyncMock(
            return_value=ImageGenerationResult(image_bytes=b"PNG", cost_usd=0.01)
        )
        instance.close = AsyncMock()
        ctx = ToolContext(
            db=MagicMock(), user=SimpleNamespace(sub="pseudo-1"),
            group_id=None, conversation_id=uuid4(), litellm_key="sk-user",
        )
        with patch.object(router, "LiteLLMClient", return_value=instance), \
             patch.object(router, "save_generated_image", new=AsyncMock(return_value=uuid4())):
            result = await router._exec_generate_image(args, ctx)
        return result, instance.generate_image.await_args.kwargs

    return _run


# ── response_format ──────────────────────────────────────────────────────────

async def test_response_format_from_settings(exec_image):
    """`b64_json` wird durchgereicht — nötig für Modelle, die sonst eine URL liefern."""
    _, call = await exec_image({"prompt": "x"}, image_response_format="b64_json")
    assert call["response_format"] == "b64_json"


async def test_empty_response_format_omits_the_parameter(exec_image):
    """Leerer Wert → None, damit der Client den Parameter weglässt (gpt-image-1)."""
    _, call = await exec_image({"prompt": "x"}, image_response_format="")
    assert call["response_format"] is None


# ── Formatauflösung ──────────────────────────────────────────────────────────

async def test_named_format_resolves_to_configured_pixels(exec_image):
    result, call = await exec_image(
        {"prompt": "x", "format": "panorama"},
        image_sizes=CUSTOM_SIZES, image_default_format="quadratisch",
    )
    assert call["size"] == "1344x768"
    assert result["format"] == "panorama"
    assert result["size"] == "1344x768"


async def test_unknown_format_falls_back_to_default(exec_image):
    """Ein erfundener Name darf die Anfrage nicht verlieren — Standardformat greift."""
    result, call = await exec_image(
        {"prompt": "x", "format": "briefmarke"},
        image_sizes=CUSTOM_SIZES, image_default_format="poster",
    )
    assert call["size"] == "896x1152"
    assert result["format"] == "poster"


async def test_missing_format_uses_default(exec_image):
    result, call = await exec_image(
        {"prompt": "x"}, image_sizes=CUSTOM_SIZES, image_default_format="panorama"
    )
    assert call["size"] == "1344x768"


async def test_legacy_pixel_value_is_not_passed_through(exec_image):
    """Liefert ein Modell noch eine Pixelgröße, greift der Default — nie ein ungeprüfter Wert.

    Entscheidend für den Spend-Schutz: An den Provider geht ausschließlich eine Größe aus
    IMAGE_SIZES, für die also ein Preis hinterlegt sein kann.
    """
    result, call = await exec_image(
        {"prompt": "x", "size": "4096x4096"},
        image_sizes=CUSTOM_SIZES, image_default_format="quadratisch",
    )
    assert call["size"] == "1024x1024"
    assert result["format"] == "quadratisch"


async def test_legacy_pixel_value_matching_a_format_name_is_ignored(exec_image):
    """Auch eine *gültige* Pixelgröße im alten Feld wird auf den Default abgebildet.

    Das Vokabular ist bewusst nur der Name — sonst gäbe es zwei Schnittstellen.
    """
    result, _ = await exec_image(
        {"prompt": "x", "size": "1344x768"},
        image_sizes=CUSTOM_SIZES, image_default_format="quadratisch",
    )
    assert result["format"] == "quadratisch"


# ── Tool-Schema ──────────────────────────────────────────────────────────────

def _schema_aus_settings(monkeypatch, sizes, default_format):
    """Schema für die aus `settings` synthetisierte Bildart.

    Ohne `config/image_models.yaml` (so laufen die Unit-Tests, siehe conftest) entsteht
    genau eine Bildart aus den `IMAGE_*`-Werten — der Zustand einer Installation, die die
    Bildarten-Datei noch nicht angelegt hat.
    """
    from app.chat import image_models, router

    monkeypatch.setattr(settings, "image_sizes", sizes)
    monkeypatch.setattr(settings, "image_default_format", default_format)
    image_models.invalidate_image_models_cache()
    return router._build_generate_image_tool(image_models.alle_bildarten())


def test_tool_schema_enum_lists_configured_format_names(monkeypatch):
    params = _schema_aus_settings(monkeypatch, CUSTOM_SIZES, "panorama")[
        "function"
    ]["parameters"]["properties"]

    assert params["format"]["enum"] == ["quadratisch", "panorama", "poster"]
    assert "size" not in params, "Pixelgrößen gehören nicht mehr ins Modell-Vokabular"
    assert "bildart" not in params, "Eine einzige Bildart → nichts zu wählen"


def test_tool_schema_description_names_sizes_and_default(monkeypatch):
    """Das Modell soll die Zuordnung sehen, um passend zum Zweck zu wählen."""
    description = _schema_aus_settings(monkeypatch, CUSTOM_SIZES, "poster")[
        "function"
    ]["parameters"]["properties"]["format"]["description"]

    assert "panorama (1344x768, quer 7:4)" in description
    assert "Standard: poster" in description


# ── Seitenverhältnis-Hinweis ─────────────────────────────────────────────────

@pytest.mark.parametrize("pixels,expected", [
    ("1024x1024", "1024x1024, 1:1"),
    ("1024x1536", "1024x1536, hochkant 2:3"),
    ("1536x1024", "1536x1024, quer 3:2"),
    ("1344x768", "1344x768, quer 7:4"),
    ("1920x1080", "1920x1080, quer 16:9"),
    ("1152x896", "1152x896, quer 9:7"),
])
def test_format_hint_derives_orientation_and_ratio(pixels, expected):
    """Ohne diesen Zusatz müsste das Modell die Orientierung aus nackten Zahlen erraten."""
    from app.chat.router import _format_hint

    assert _format_hint(pixels) == expected


def test_format_hint_omits_unreadable_ratios():
    """Teilerfremde Kanten → nur Orientierung; '1000:619' hilft niemandem."""
    from app.chat.router import _format_hint

    assert _format_hint("1000x619") == "1000x619, quer"


@pytest.mark.parametrize("value", ["auto", "", "1024", "axb", "0x100", "-5x10"])
def test_format_hint_passes_through_unparseable_values(value):
    """Nicht deutbare Werte dürfen die Schema-Erzeugung nicht sprengen."""
    from app.chat.router import _format_hint

    assert _format_hint(value) == value


def test_format_hint_makes_arbitrary_names_self_describing(monkeypatch):
    """Auch bei einem nichtssagenden Formatnamen steht die Orientierung in der Beschreibung."""
    description = _schema_aus_settings(
        monkeypatch, {"A4": "896x1152", "breitbild": "1920x1080"}, "A4"
    )["function"]["parameters"]["properties"]["format"]["description"]

    assert "A4 (896x1152, hochkant 7:9)" in description
    assert "breitbild (1920x1080, quer 16:9)" in description


def test_tool_schema_follows_a_provider_switch(monkeypatch):
    """Andere Pixelgrößen, gleiches Vokabular — der Kern des benannten Formats."""
    schema = _schema_aus_settings(
        monkeypatch, {"quadratisch": "512x512", "quer": "768x512"}, "quadratisch"
    )
    format_prop = schema["function"]["parameters"]["properties"]["format"]

    assert format_prop["enum"] == ["quadratisch", "quer"]
    assert "512x512" in format_prop["description"]
