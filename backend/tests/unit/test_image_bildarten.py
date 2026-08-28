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


# ── Werkzeug-Schema je Assistent (Schritt 3) ────────────────────────────────────────


def _assistent(tool_groups=("image_generation",), image_kinds=None):
    return SimpleNamespace(tool_groups=list(tool_groups), image_kinds=image_kinds)


def _schema(assistant, erlaubte_modelle=None):
    from app.chat import router
    from app.chat.tools import SchemaContext

    ctx = SchemaContext(assistant=assistant, erlaubte_modelle=erlaubte_modelle)
    return router._generate_image_definition(ctx)["function"]["parameters"]["properties"]


def test_mehrere_bildarten_erzeugen_ein_enum(bildarten):
    props = _schema(_assistent())

    assert props["bildart"]["enum"] == ["standard", "formatwahl"]
    assert "Mit Formatwahl" in props["bildart"]["description"]


def test_eine_einzige_bildart_erzeugt_keinen_parameter(bildarten):
    """Der Regelfall: nichts zu wählen, also auch nichts falsch zu wählen."""
    props = _schema(_assistent(image_kinds=["formatwahl"]))

    assert "bildart" not in props
    assert props["format"]["enum"] == ["quadratisch", "hoch", "quer"]
    assert "Standard: quer" in props["format"]["description"]


def test_formate_sind_die_vereinigung_nicht_der_schnitt(bildarten):
    """Sonst verlöre ein Assistent genau die Formate, wegen derer die zweite Bildart da ist."""
    props = _schema(_assistent())

    assert props["format"]["enum"] == ["quadratisch", "hoch", "quer"]
    assert "nächstliegende" in props["format"]["description"]


def test_assistent_beschraenkt_die_auswahl(bildarten):
    props = _schema(_assistent(image_kinds=["standard"]))

    assert "bildart" not in props
    assert props["format"]["enum"] == ["quadratisch"]


def test_unbekannte_auswahl_faellt_auf_alle_zurueck(bildarten):
    """Eine verwaiste ID (Bildart umbenannt) darf den Assistenten nicht stumm schalten."""
    props = _schema(_assistent(image_kinds=["gibt-es-nicht-mehr"]))

    assert props["bildart"]["enum"] == ["standard", "formatwahl"]


def test_ohne_assistent_gelten_alle_bildarten(bildarten):
    assert _schema(None)["bildart"]["enum"] == ["standard", "formatwahl"]


# ── Durchsetzung im Handler ─────────────────────────────────────────────────────────


async def test_nicht_freigegebene_bildart_wird_nicht_genutzt(bildarten):
    """Das Schema bietet sie nicht an — ein Modell kann sie trotzdem nennen.

    Ohne diese Prüfung ließe sich die Auswahl des Admins samt Kostenrahmen umgehen.
    """
    from app.chat import router

    instance = MagicMock()
    instance.generate_image = AsyncMock(
        return_value=ImageGenerationResult(image_bytes=b"PNG", cost_usd=0.02)
    )
    instance.close = AsyncMock()
    ctx = ToolContext(
        db=MagicMock(), user=SimpleNamespace(sub="p"), group_id=None,
        conversation_id=uuid4(), litellm_key="k",
        assistant=_assistent(image_kinds=["standard"]),
    )
    with patch.object(router, "LiteLLMClient", return_value=instance), \
         patch.object(router, "save_generated_image", new=AsyncMock(return_value=uuid4())):
        result = await router._exec_generate_image(
            {"prompt": "x", "bildart": "formatwahl"}, ctx
        )

    assert instance.generate_image.await_args.kwargs["model"] == "bild-standard"
    assert result["bildart"] == "Standard (quadratisch)"


async def test_freigegebene_bildart_wird_genutzt(bildarten):
    from app.chat import router

    instance = MagicMock()
    instance.generate_image = AsyncMock(
        return_value=ImageGenerationResult(image_bytes=b"PNG", cost_usd=0.02)
    )
    instance.close = AsyncMock()
    ctx = ToolContext(
        db=MagicMock(), user=SimpleNamespace(sub="p"), group_id=None,
        conversation_id=uuid4(), litellm_key="k",
        assistant=_assistent(image_kinds=["standard", "formatwahl"]),
    )
    with patch.object(router, "LiteLLMClient", return_value=instance), \
         patch.object(router, "save_generated_image", new=AsyncMock(return_value=uuid4())):
        await router._exec_generate_image({"prompt": "x", "bildart": "formatwahl"}, ctx)

    assert instance.generate_image.await_args.kwargs["model"] == "bild-flux2"


def test_standard_unter_faellt_auf_die_erste_zurueck(bildarten):
    """Führt ein Assistent die globale Standard-Bildart nicht, gilt seine erste."""
    from app.chat.image_models import alle_bildarten, standard_unter

    nur_formatwahl = [b for b in alle_bildarten() if b.id == "formatwahl"]
    assert standard_unter(nur_formatwahl).id == "formatwahl"
    assert standard_unter(alle_bildarten()).id == "standard"


# ── Auflösung des Schema-Callables in tools_for ─────────────────────────────────────


def test_tools_for_liefert_fertige_dicts(bildarten):
    """Alles hinter tools_for sieht nur noch Dicts — kein Aufrufer muss das wissen."""
    from app.chat.tools import tools_for

    tools = tools_for(_assistent(), group_id=None, is_group_teacher=False)
    bild = [t for t in tools if t.name == "generate_image"]

    assert len(bild) == 1
    assert isinstance(bild[0].definition, dict)
    assert bild[0].definition["function"]["name"] == "generate_image"


# ── Team-Filter zur Laufzeit (Schritt 5) ────────────────────────────────────────────


def test_nicht_freigeschaltete_bildart_erscheint_nicht_im_schema(bildarten):
    """Was der Proxy mit 403 abwiese, soll das Chat-Modell gar nicht erst sehen."""
    props = _schema(_assistent(), erlaubte_modelle={"bild-standard", "chat-standard"})

    assert "bildart" not in props, "Nur eine übrig → kein Auswahlparameter"
    assert props["format"]["enum"] == ["quadratisch"]


def test_beide_freigeschaltet_ergibt_die_volle_auswahl(bildarten):
    props = _schema(_assistent(), erlaubte_modelle={"bild-standard", "bild-flux2"})

    assert props["bildart"]["enum"] == ["standard", "formatwahl"]


def test_unbekannte_freigabe_filtert_nicht(bildarten):
    """None heißt „Proxy nicht erreichbar" — nicht „nichts erlaubt".

    Der wichtigste Fall des ganzen Schritts: Ein Filter, der bei einer Störung alles
    wegnimmt, machte aus einem Anzeigeproblem einen Totalausfall.
    """
    props = _schema(_assistent(), erlaubte_modelle=None)

    assert props["bildart"]["enum"] == ["standard", "formatwahl"]


def test_leere_freigabe_filtert_ebenfalls_nicht(bildarten):
    """Bliebe nichts übrig, wäre ein Werkzeug ohne Auswahl die schlechtere Auskunft.

    Dann soll der Proxy antworten — seine Ablehnung wird in einen lesbaren Satz übersetzt.
    """
    props = _schema(_assistent(), erlaubte_modelle=set())

    assert props["bildart"]["enum"] == ["standard", "formatwahl"]


async def test_handler_nutzt_keine_gesperrte_bildart(bildarten):
    """Was das Schema verbirgt, muss der Handler auch ablehnen."""
    from app.chat import router

    instance = MagicMock()
    instance.generate_image = AsyncMock(
        return_value=ImageGenerationResult(image_bytes=b"PNG", cost_usd=0.02)
    )
    instance.close = AsyncMock()
    ctx = ToolContext(
        db=MagicMock(), user=SimpleNamespace(sub="p"), group_id=None,
        conversation_id=uuid4(), litellm_key="k", assistant=_assistent(),
        erlaubte_modelle={"bild-standard"},
    )
    with patch.object(router, "LiteLLMClient", return_value=instance), \
         patch.object(router, "save_generated_image", new=AsyncMock(return_value=uuid4())):
        await router._exec_generate_image({"prompt": "x", "bildart": "formatwahl"}, ctx)

    assert instance.generate_image.await_args.kwargs["model"] == "bild-standard"


# ── Lesbare Fehlermeldungen statt 403 ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "status, erwartet",
    [
        (403, "nicht freigeschaltet"),
        (401, "nicht freigeschaltet"),
        (429, "Budget"),
        (500, "fehlgeschlagen"),
        (None, "fehlgeschlagen"),
    ],
)
async def test_ablehnung_wird_uebersetzt(bildarten, status, erwartet):
    """Ein durchgereichtes „HTTP 403" wäre für eine Schülerin wertlos."""
    from app.chat import router
    from app.litellm.client import ImageGenerationError

    instance = MagicMock()
    instance.generate_image = AsyncMock(
        side_effect=ImageGenerationError("abgelehnt", status_code=status)
    )
    instance.close = AsyncMock()
    ctx = ToolContext(
        db=MagicMock(), user=SimpleNamespace(sub="p"), group_id=None,
        conversation_id=uuid4(), litellm_key="k", assistant=_assistent(),
    )
    with patch.object(router, "LiteLLMClient", return_value=instance):
        result = await router._exec_generate_image({"prompt": "x"}, ctx)

    assert result["status"] == "error"
    assert erwartet in result["error"]
    instance.close.assert_awaited_once()


async def test_fehlertext_nennt_die_bildart(bildarten):
    """Damit das Chat-Modell sagen kann, *was* gesperrt ist — nicht nur „ging nicht"."""
    from app.chat import router
    from app.litellm.client import ImageGenerationError

    instance = MagicMock()
    instance.generate_image = AsyncMock(
        side_effect=ImageGenerationError("nope", status_code=403)
    )
    instance.close = AsyncMock()
    ctx = ToolContext(
        db=MagicMock(), user=SimpleNamespace(sub="p"), group_id=None,
        conversation_id=uuid4(), litellm_key="k",
        assistant=_assistent(image_kinds=["formatwahl"]),
    )
    with patch.object(router, "LiteLLMClient", return_value=instance):
        result = await router._exec_generate_image({"prompt": "x"}, ctx)

    assert "Mit Formatwahl" in result["error"]


def test_tools_for_veraendert_die_registry_nicht(bildarten):
    """Sonst hinge das Schema am letzten Chat, der zufällig durchlief."""
    from app.chat.tools import TOOL_REGISTRY, tools_for

    tools_for(_assistent(image_kinds=["standard"]), group_id=None, is_group_teacher=False)

    assert callable(TOOL_REGISTRY["generate_image"].definition)

    props = tools_for(_assistent(), group_id=None, is_group_teacher=False)
    bild = [t for t in props if t.name == "generate_image"][0]
    assert bild.definition["function"]["parameters"]["properties"]["bildart"]["enum"] == [
        "standard", "formatwahl",
    ]
