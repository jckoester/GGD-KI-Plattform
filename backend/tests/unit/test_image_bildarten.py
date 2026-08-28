"""Unit-Tests für die Auflösungskette Bildart → Modell/Format (Mehrmodell-Plan, Schritt 2).

Der Handler löst nicht mehr gegen globale `IMAGE_*`-Werte auf, sondern gegen die gewählte
Bildart. Geprüft wird vor allem, dass dabei **nie eine unkonfigurierte Größe** und **nie ein
unbeabsichtigtes Modell** beim Anbieter landet — beides kostet Geld und umgeht die
Freigabematrix.
"""

import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.chat import image_models
from app.chat.image_models import Bildart
from app.chat.tools import ToolContext
from app.config import settings
from app.litellm.client import ImageGenerationResult

# `standard` kann nur quadratisch (wie FLUX.1-schnell), `formatwahl` alles (wie FLUX.2).
BILDARTEN = """\
bildarten:
  - id: standard
    label: "Standard (quadratisch)"
    modell: bild-standard
    formate:
      quadratisch: "1024x1024"
    standardformat: quadratisch
    response_format: ""
  - id: formatwahl
    label: "Mit Formatwahl (hoch/quer)"
    modell: bild-flux2
    formate:
      quadratisch: "1024x1024"
      hoch: "768x1344"
      quer: "1344x768"
    standardformat: quer
    response_format: "b64_json"
standard_bildart: standard
"""


@pytest.fixture
def bildarten(tmp_path, monkeypatch):
    """Installiert die obige Konfiguration (überschreibt die conftest-Vorgabe)."""
    pfad = tmp_path / "image_models.yaml"
    pfad.write_text(textwrap.dedent(BILDARTEN), encoding="utf-8")
    monkeypatch.setattr(settings, "image_models_path", str(pfad))
    image_models.invalidate_image_models_cache()
    yield
    image_models.invalidate_image_models_cache()


@pytest.fixture
def exec_image(bildarten):
    """Ruft _exec_generate_image mit gemocktem Client; liefert (result, call, save_call)."""

    async def _run(args):
        from app.chat import router

        instance = MagicMock()
        instance.generate_image = AsyncMock(
            return_value=ImageGenerationResult(image_bytes=b"PNG", cost_usd=0.02)
        )
        instance.close = AsyncMock()
        ctx = ToolContext(
            db=MagicMock(), user=SimpleNamespace(sub="pseudo-1"),
            group_id=None, conversation_id=uuid4(), litellm_key="sk-user",
        )
        with patch.object(router, "LiteLLMClient", return_value=instance), \
             patch.object(
                 router, "save_generated_image", new=AsyncMock(return_value=uuid4())
             ) as save:
            result = await router._exec_generate_image(args, ctx)
        return result, instance.generate_image.await_args.kwargs, save.await_args

    return _run


# ── Bildart → Modell ────────────────────────────────────────────────────────────────


async def test_bildart_bestimmt_modell_und_response_format(exec_image):
    result, call, _ = await exec_image({"prompt": "x", "bildart": "formatwahl"})

    assert call["model"] == "bild-flux2"
    assert call["response_format"] == "b64_json"
    assert result["bildart"] == "Mit Formatwahl (hoch/quer)"


async def test_leeres_response_format_laesst_den_parameter_weg(exec_image):
    """Für Modelle, die ihn ablehnen und ohnehin Base64 liefern (FLUX.1, gpt-image-1)."""
    _, call, _ = await exec_image({"prompt": "x", "bildart": "standard"})

    assert call["response_format"] is None


async def test_ohne_bildart_greift_die_standard_bildart(exec_image):
    """Solange das Werkzeug-Schema keine Bildart anbietet (bis Schritt 3), ist das der Normalfall."""
    _, call, _ = await exec_image({"prompt": "x"})

    assert call["model"] == "bild-standard"


async def test_unbekannte_bildart_faellt_auf_den_standard_zurueck(exec_image):
    """Eine erfundene ID darf die Anfrage nicht verlieren — und nie ein fremdes Modell rufen."""
    _, call, _ = await exec_image({"prompt": "x", "bildart": "comic-deluxe"})

    assert call["model"] == "bild-standard"


async def test_persistenz_speichert_das_tatsaechlich_genutzte_modell(exec_image):
    """Nicht den globalen Default: Sonst wäre nicht mehr rekonstruierbar, womit ein Bild entstand."""
    _, _, save_call = await exec_image({"prompt": "x", "bildart": "formatwahl"})

    assert save_call.kwargs["model"] == "bild-flux2"
    assert save_call.kwargs["size"] == "1344x768"


# ── Formatauflösung innerhalb der Bildart ───────────────────────────────────────────


async def test_bekanntes_format_wird_exakt_genommen(exec_image):
    result, call, _ = await exec_image(
        {"prompt": "x", "bildart": "formatwahl", "format": "hoch"}
    )

    assert call["size"] == "768x1344"
    assert result["format"] == "hoch"
    assert "nicht möglich" not in result["note"]


async def test_standardformat_der_bildart_gilt_ohne_angabe(exec_image):
    """`formatwahl` hat `quer` als Standard — nicht das global konfigurierte Format."""
    result, call, _ = await exec_image({"prompt": "x", "bildart": "formatwahl"})

    assert result["format"] == "quer"
    assert call["size"] == "1344x768"


async def test_unmoegliches_format_wird_genaehert_statt_abgelehnt(exec_image):
    """„hoch" bei einem Modell, das nur quadratisch kann → quadratisch, nicht „quer"."""
    result, call, _ = await exec_image(
        {"prompt": "x", "bildart": "standard", "format": "hoch"}
    )

    assert result["format"] == "quadratisch"
    assert call["size"] == "1024x1024"


async def test_naeherung_wird_dem_chat_modell_mitgeteilt(exec_image):
    """Sonst bekäme die Nutzerin stillschweigend etwas anderes, als sie wollte."""
    result, _, _ = await exec_image(
        {"prompt": "x", "bildart": "standard", "format": "quer"}
    )

    assert "„quer“" in result["note"]
    assert "nicht möglich" in result["note"]
    assert "„quadratisch“" in result["note"]


async def test_erfundenes_format_faellt_still_auf_den_standard(exec_image):
    """Ohne erkennbare Absicht gibt es nichts zu nähern — und nichts zu erklären."""
    result, call, _ = await exec_image(
        {"prompt": "x", "bildart": "formatwahl", "format": "briefmarke"}
    )

    assert result["format"] == "quer"
    assert call["size"] == "1344x768"
    assert result["note"] == "Bild wurde erzeugt und gespeichert."


async def test_rohe_pixelangabe_wird_nicht_durchgereicht(exec_image):
    """Spend-Schutz: An den Anbieter geht ausschließlich eine konfigurierte Größe."""
    result, call, _ = await exec_image(
        {"prompt": "x", "bildart": "formatwahl", "size": "4096x4096"}
    )

    assert call["size"] == "1344x768"
    assert result["format"] == "quer"


# ── Näherung als reine Funktion ─────────────────────────────────────────────────────


def _bildart(formate: dict[str, str], standard: str) -> Bildart:
    return Bildart(
        id="x", label="X", modell="m", formate=formate, standardformat=standard
    )


@pytest.mark.parametrize(
    "ziel, erwartet",
    [
        (768 / 1344, "quadratisch"),   # Hochformat → quadratisch, nicht quer
        (1344 / 768, "quer"),          # Querformat → quer
        (1.0, "quadratisch"),          # exakt
        (1.05, "quadratisch"),         # fast quadratisch
    ],
)
def test_naechstes_format_waehlt_die_nahe_orientierung(ziel, erwartet):
    b = _bildart({"quadratisch": "1024x1024", "quer": "1344x768"}, "quadratisch")

    assert b.naechstes_format(ziel) == erwartet


def test_naechstes_format_misst_logarithmisch():
    """Der Grund, warum nicht linear verglichen wird.

    768x1344 (0,571) und 1344x768 (1,75) sind Kehrwerte — von 1:1 aus anschaulich gleich
    weit entfernt. Im Log-Maß sind sie das auch, der Gleichstand fällt ans Standardformat.
    Linear gemessen wäre der Abstand 0,43 gegen 0,75, und das Hochformat gewänne allein
    deshalb, weil Hochformate zwischen 0 und 1 gedrängt liegen.
    """
    b = _bildart({"hoch": "768x1344", "quer": "1344x768"}, "quer")

    assert b.naechstes_format(1.0) == "quer"

    b_andersherum = _bildart({"hoch": "768x1344", "quer": "1344x768"}, "hoch")
    assert b_andersherum.naechstes_format(1.0) == "hoch"


def test_bekanntes_seitenverhaeltnis_sucht_ueber_alle_bildarten(bildarten):
    """Erst diese Auskunft macht die Näherung möglich: „hoch" heißt hochkant."""
    assert image_models.bekanntes_seitenverhaeltnis("hoch") == pytest.approx(768 / 1344)
    assert image_models.bekanntes_seitenverhaeltnis("quadratisch") == pytest.approx(1.0)


@pytest.mark.parametrize("wert", [None, "", "briefmarke", "1024x1024"])
def test_bekanntes_seitenverhaeltnis_kennt_keine_pixelangaben(bildarten, wert):
    """Eine rohe Größe ist kein Formatname — sonst gäbe es zwei Schnittstellen zum Modell."""
    assert image_models.bekanntes_seitenverhaeltnis(wert) is None
