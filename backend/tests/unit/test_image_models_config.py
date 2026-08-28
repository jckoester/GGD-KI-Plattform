"""Unit-Tests für app.chat.image_models (Mehrmodell-Plan, Schritt 1).

Geprüft wird vor allem das **Fail-closed-Verhalten**: Jeder Fehler in der YAML, der
sonst dazu führen könnte, dass ein anderes als das gemeinte Bildmodell gerufen wird,
muss den Start abbrechen — nicht in einen stillen Fallback laufen.
"""

import os
import textwrap

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.config import settings
from app.chat.image_models import (
    Bildart,
    ImageModelsConfig,
    alle_bildarten,
    default_bildart,
    get_bildart,
    invalidate_image_models_cache,
    load_image_models,
    referenzierte_modelle,
)

GUELTIG = """\
bildarten:
  - id: illustration
    label: "Illustration"
    beschreibung: "Skizzen fürs Arbeitsblatt."
    modell: bild-standard
    formate:
      quadratisch: "1024x1024"
    standardformat: quadratisch
    response_format: ""
  - id: comic
    label: "Comic"
    modell: bild-comic
    formate:
      quadratisch: "1024x1024"
      hoch: "768x1344"
      quer: "1344x768"
    standardformat: quer
    response_format: "b64_json"
standard_bildart: illustration
"""


@pytest.fixture(autouse=True)
def _fresh_cache():
    invalidate_image_models_cache()
    yield
    invalidate_image_models_cache()


@pytest.fixture
def yaml_datei(tmp_path, monkeypatch):
    """Schreibt eine image_models.yaml und richtet settings darauf aus."""

    def _schreiben(inhalt: str):
        pfad = tmp_path / "image_models.yaml"
        pfad.write_text(textwrap.dedent(inhalt), encoding="utf-8")
        monkeypatch.setattr(settings, "image_models_path", str(pfad))
        return pfad

    return _schreiben


# ── Laden ───────────────────────────────────────────────────────────────────────────


def test_gueltige_datei_wird_geladen(yaml_datei):
    yaml_datei(GUELTIG)
    cfg = load_image_models()

    assert [b.id for b in cfg.bildarten] == ["illustration", "comic"]
    assert cfg.standard.id == "illustration"
    assert cfg.get("comic").modell == "bild-comic"
    assert cfg.get("gibtsnicht") is None


def test_zugriffshelfer(yaml_datei):
    yaml_datei(GUELTIG)

    assert get_bildart("comic").label == "Comic"
    assert get_bildart(None) is None
    assert default_bildart().id == "illustration"
    assert [b.id for b in alle_bildarten()] == ["illustration", "comic"]


def test_referenzierte_modelle_ohne_dubletten(yaml_datei):
    """Grundlage der Konfigurationsprüfung: Jedes Modell braucht einen Preis."""
    yaml_datei(
        GUELTIG.replace("modell: bild-comic", "modell: bild-standard")
    )
    assert referenzierte_modelle() == ["bild-standard"]


def test_pixel_zerlegt_die_groesse(yaml_datei):
    yaml_datei(GUELTIG)
    assert get_bildart("comic").pixel("quer") == (1344, 768)
    assert get_bildart("comic").pixel("hoch") == (768, 1344)


def test_cache_wird_genutzt_und_invalidiert(yaml_datei):
    pfad = yaml_datei(GUELTIG)
    assert len(load_image_models().bildarten) == 2

    pfad.write_text(
        textwrap.dedent(
            """\
            bildarten:
              - id: nur-eine
                label: "Nur eine"
                modell: bild-standard
                formate: {quadratisch: "1024x1024"}
                standardformat: quadratisch
            standard_bildart: nur-eine
            """
        ),
        encoding="utf-8",
    )
    # Ohne Invalidierung bleibt der alte Stand sichtbar …
    assert len(load_image_models().bildarten) == 2
    invalidate_image_models_cache()
    # … danach der neue.
    assert [b.id for b in load_image_models().bildarten] == ["nur-eine"]


# ── Aufwärtspfad: fehlende Datei ────────────────────────────────────────────────────


def test_fehlende_datei_synthetisiert_aus_den_alten_variablen(tmp_path, monkeypatch):
    """Ein Update ohne neue Datei darf das Verhalten NICHT ändern."""
    monkeypatch.setattr(settings, "image_models_path", str(tmp_path / "fehlt.yaml"))
    monkeypatch.setattr(settings, "image_default_model", "bild-alt")
    monkeypatch.setattr(
        settings, "image_sizes", {"quadratisch": "1024x1024", "quer": "1536x1024"}
    )
    monkeypatch.setattr(settings, "image_default_format", "quer")
    monkeypatch.setattr(settings, "image_response_format", "b64_json")

    cfg = load_image_models()

    assert [b.id for b in cfg.bildarten] == ["standard"]
    einzige = cfg.standard
    assert einzige.modell == "bild-alt"
    assert einzige.formate == {"quadratisch": "1024x1024", "quer": "1536x1024"}
    assert einzige.standardformat == "quer"
    assert einzige.response_format == "b64_json"


def test_synthese_haengt_nicht_am_settings_objekt(tmp_path, monkeypatch):
    """Die Formate werden kopiert — sonst veränderte ein Aufrufer settings.image_sizes."""
    monkeypatch.setattr(settings, "image_models_path", str(tmp_path / "fehlt.yaml"))
    monkeypatch.setattr(settings, "image_sizes", {"quadratisch": "1024x1024"})

    cfg = load_image_models()
    cfg.standard.formate["geschmuggelt"] = "1x1"

    assert "geschmuggelt" not in settings.image_sizes


# ── Fail-closed ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "inhalt, erwartet",
    [
        # Doppelte ID: sonst entschiede die Reihenfolge in der Datei über das Modell.
        (
            """\
            bildarten:
              - {id: a, label: A, modell: m1, formate: {q: "1024x1024"}, standardformat: q}
              - {id: a, label: B, modell: m2, formate: {q: "1024x1024"}, standardformat: q}
            standard_bildart: a
            """,
            "Doppelte Bildart-IDs",
        ),
        # standard_bildart zeigt ins Leere.
        (
            """\
            bildarten:
              - {id: a, label: A, modell: m1, formate: {q: "1024x1024"}, standardformat: q}
            standard_bildart: b
            """,
            "standard_bildart 'b' ist keine konfigurierte Bildart",
        ),
        # standardformat ist kein Schlüssel aus formate.
        (
            """\
            bildarten:
              - {id: a, label: A, modell: m1, formate: {q: "1024x1024"}, standardformat: hoch}
            standard_bildart: a
            """,
            "standardformat 'hoch' ist kein Schlüssel aus formate",
        ),
        # Keine Formate.
        (
            """\
            bildarten:
              - {id: a, label: A, modell: m1, formate: {}, standardformat: q}
            standard_bildart: a
            """,
            "Mindestens ein Format angeben",
        ),
        # Pixelgröße ist keine.
        (
            """\
            bildarten:
              - {id: a, label: A, modell: m1, formate: {q: "gross"}, standardformat: q}
            standard_bildart: a
            """,
            "ist keine Pixelgröße",
        ),
        # Null-Kantenlänge.
        (
            """\
            bildarten:
              - {id: a, label: A, modell: m1, formate: {q: "0x1024"}, standardformat: q}
            standard_bildart: a
            """,
            "ist keine Pixelgröße",
        ),
        # ID mit Großbuchstaben/Leerzeichen — sie landet im Werkzeug-Schema.
        (
            """\
            bildarten:
              - {id: "Mein Comic", label: A, modell: m1, formate: {q: "1024x1024"}, standardformat: q}
            standard_bildart: "Mein Comic"
            """,
            "ist unzulässig",
        ),
        # Leeres Modell.
        (
            """\
            bildarten:
              - {id: a, label: A, modell: "  ", formate: {q: "1024x1024"}, standardformat: q}
            standard_bildart: a
            """,
            "darf nicht leer sein",
        ),
        # Gar keine Bildart.
        (
            """\
            bildarten: []
            standard_bildart: a
            """,
            "Mindestens eine Bildart",
        ),
    ],
)
def test_fehlerhafte_datei_bricht_ab(yaml_datei, inhalt, erwartet):
    yaml_datei(inhalt)
    with pytest.raises(ValueError) as exc:
        load_image_models()
    assert erwartet in str(exc.value)


def test_response_format_url_wird_abgewiesen(yaml_datei):
    """Datenschutzgrenze: Es werden ausschließlich Base64-Bilder verarbeitet.

    Mit `url` liefe jeder Aufruf dieser Bildart in einen RuntimeError im Client —
    besser beim Start abweisen als im Gespräch scheitern.
    """
    yaml_datei(
        """\
        bildarten:
          - id: a
            label: A
            modell: m1
            formate: {q: "1024x1024"}
            standardformat: q
            response_format: url
        standard_bildart: a
        """
    )
    with pytest.raises(ValueError) as exc:
        load_image_models()
    assert "response_format 'url' ist unzulässig" in str(exc.value)


def test_fehlermeldung_nennt_den_pfad(yaml_datei):
    """Wer den Startfehler liest, muss wissen, welche Datei gemeint ist."""
    pfad = yaml_datei("bildarten: []\nstandard_bildart: a\n")
    with pytest.raises(ValueError) as exc:
        load_image_models()
    assert str(pfad) in str(exc.value)


# ── Modell-Ebene (ohne Datei) ───────────────────────────────────────────────────────


def test_bildart_direkt_konstruierbar():
    b = Bildart(
        id="x", label="X", modell="m",
        formate={"quadratisch": "1024x1024"}, standardformat="quadratisch",
    )
    assert b.beschreibung == ""
    assert b.response_format == ""


def test_leerzeichen_werden_getrimmt():
    b = Bildart(
        id="x", label="  X  ", modell="  m  ",
        formate={"q": "1024x1024"}, standardformat="q",
    )
    assert b.label == "X"
    assert b.modell == "m"


def test_config_standard_zeigt_auf_die_bildart():
    cfg = ImageModelsConfig(
        bildarten=[
            Bildart(id="a", label="A", modell="m", formate={"q": "1x1"}, standardformat="q"),
            Bildart(id="b", label="B", modell="m", formate={"q": "1x1"}, standardformat="q"),
        ],
        standard_bildart="b",
    )
    assert cfg.standard.id == "b"
