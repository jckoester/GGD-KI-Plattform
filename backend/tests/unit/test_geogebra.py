"""Unit-Tests: Plot-Spec → GeoGebra `.ggb` (Phase 18, Schritt 4).

Prüft die XML-Erzeugung (Funktionen/Punkte/Fenster/Namensübersetzung) und die ZIP-Verpackung.
Das tatsächliche Öffnen in GeoGebra Classic ist ein manueller Check (Plan §4/Schritt 4).
"""
import io
import os
import zipfile
from xml.dom.minidom import parseString

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.artifacts import geogebra
from app.render.errors import RenderError
from app.render.plot import parse_plot_spec


def _xml(source: str) -> str:
    spec = parse_plot_spec(source)
    xml = geogebra.plot_spec_to_ggb_xml(spec)
    parseString(xml)  # wirft bei nicht wohlgeformtem XML
    return xml


def test_functions_become_labeled_expressions():
    xml = _xml("functions:\n  - f(x) = x^2\n  - y = 2*x\n")
    assert 'label="f" exp="f(x)=x^2"' in xml
    assert 'label="g" exp="g(x)=2*x"' in xml   # zweite Funktion → Label g
    assert xml.count('type="function"') == 2


def test_function_name_translation():
    xml = _xml("functions:\n  - log(x)\n")
    assert "ln(x)" in xml            # Plot-log = natürlicher Log → GeoGebra ln
    assert "log(x)" not in xml


def test_log10_and_sign_translation():
    xml = _xml("functions:\n  - log10(x)\n  - sign(x)\n")
    assert "lg(x)" in xml
    assert "sgn(x)" in xml


def test_power_starstar_normalized():
    xml = _xml("functions:\n  - x**3\n")
    assert "x^3" in xml
    assert "x**3" not in xml


def test_points_with_and_without_caption():
    xml = _xml("functions:\n  - x\npoints:\n  - [1, 2, 'Scheitel']\n  - [3, 4]\n")
    assert xml.count('type="point"') == 2
    assert 'val="Scheitel"' in xml          # Caption des ersten Punkts
    assert 'x="1" y="2" z="1"' in xml


def test_coord_system_from_domain_range():
    # domain [-10,10] (Breite 20) über 800 px → scale 40; range [-5,15] (Höhe 20) → yscale 30.
    xml = _xml("functions:\n  - x\ndomain: [-10, 10]\nrange: [-5, 15]\n")
    assert 'scale="40.0000"' in xml
    assert 'yscale="30.0000"' in xml


def test_grid_flag():
    assert 'grid="true"' in _xml("functions:\n  - x\ngrid: true\n")
    assert 'grid="false"' in _xml("functions:\n  - x\n")


def test_special_chars_escaped_in_caption():
    xml = _xml("functions:\n  - x\npoints:\n  - [0, 0, 'A & B <x>']\n")
    assert "&amp;" in xml and "&lt;" in xml
    parseString(xml)  # bleibt wohlgeformt


def test_ggb_bytes_is_valid_zip_with_geogebra_xml():
    data = geogebra.ggb_bytes_from_source("functions:\n  - x^2\n")
    zf = zipfile.ZipFile(io.BytesIO(data))
    assert zf.namelist() == ["geogebra.xml"]
    parseString(zf.read("geogebra.xml").decode("utf-8"))


def test_invalid_spec_raises_render_error():
    with pytest.raises(RenderError):
        geogebra.ggb_bytes_from_source("nur ein string")
    with pytest.raises(RenderError):
        geogebra.ggb_bytes_from_source("domain: [1, 2]\n")  # weder Funktion noch Punkt
