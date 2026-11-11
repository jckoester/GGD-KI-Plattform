"""Unit-Tests: Office-Export aus Pandoc-Bausteinen (0.39, Päckchen K, Schritt 2).

Konvertierungen nur mit installiertem Pandoc (`skipif`), wie in `test_pandoc_export.py`.
"""
import io
import os
import zipfile

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.export import office, pandoc

_needs_pandoc = pytest.mark.skipif(not pandoc.pandoc_available(), reason="pandoc nicht installiert")


def _docx_xml(data: bytes) -> str:
    return zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")


# ── Bausteine (ohne Pandoc) ───────────────────────────────────────────────────

def test_text_zerlegt_in_woerter_und_umbrueche():
    assert office.text("a b\nc") == [
        {"t": "Str", "c": "a"}, {"t": "Space"}, {"t": "Str", "c": "b"},
        {"t": "LineBreak"}, {"t": "Str", "c": "c"},
    ]
    assert office.text("") == []


def test_durchstreichen_greift_auch_in_listen():
    bloecke = [office.absatz(office.text("a")),
               office.aufzaehlung([[office.schlicht(office.text("b"))]])]
    neu = office.durchstreichen(bloecke)
    assert neu[0]["c"][0]["t"] == "Strikeout"
    assert neu[1]["c"][0][0]["c"][0]["t"] == "Strikeout"


def test_tabelle_hat_kopf_und_breiten():
    t = office.tabelle(["A", "B"], [[[office.schlicht(office.text("x"))], []]], [0.3, 0.7])
    assert t["t"] == "Table"
    assert [s[1]["c"] for s in t["c"][2]] == [0.3, 0.7]
    assert len(t["c"][3][1]) == 1          # eine Kopfzeile
    assert len(t["c"][4][0][3]) == 1       # eine Datenzeile


# ── Mit Pandoc ────────────────────────────────────────────────────────────────

@_needs_pandoc
def test_bloecke_in_einem_aufruf_je_teil():
    bloecke, api = office._bloecke_sync({
        "a": "Erster **Teil** mit $x^2$",
        "b": "- eins\n- zwei",
        "leer": "",
    })
    assert isinstance(api, list) and api
    assert bloecke["a"][0]["t"] == "Para"
    assert any(i.get("t") == "Math" for i in bloecke["a"][0]["c"])
    assert bloecke["b"][0]["t"] == "BulletList"
    assert bloecke["leer"] == []


@_needs_pandoc
def test_doppelpunkt_zeile_bricht_die_abschnitte_nicht_auf():
    """Eine Zeile `:::` im Text schlösse den gemeinsamen Abschnitt — der Teil wird einzeln gelesen."""
    bloecke, _ = office._bloecke_sync({"a": "vorher\n\n:::\n\nnachher", "b": "zweiter"})
    assert "nachher" in str(bloecke["a"])
    assert "nachher" not in str(bloecke["b"])
    assert "zweiter" in str(bloecke["b"])


@_needs_pandoc
def test_klammer_mathe_wird_formel():
    bloecke, _ = office._bloecke_sync({"a": "Wert \\(x^2\\)"})
    assert any(i.get("t") == "Math" for i in bloecke["a"][0]["c"])


@_needs_pandoc
@pytest.mark.parametrize("fmt", ["docx", "odt"])
async def test_formeln_in_tabellenzellen(fmt):
    bloecke, api = office._bloecke_sync({"z1": "Einstieg mit $x^2$", "z2": "- Punkt $\\frac{1}{2}$"})
    dok = [
        office.ueberschrift(1, office.text("Stunde")),
        office.tabelle(["Zeit", "Phase"], [
            [[office.schlicht(office.text("0–10′"))], bloecke["z1"]],
            [[office.schlicht(office.text("10–20′"))], bloecke["z2"]],
        ], [0.2, 0.8]),
    ]
    data = await office.dokument_zu_office(dok, api_version=api, fmt=fmt)
    assert data[:2] == b"PK"
    if fmt == "docx":
        xml = _docx_xml(data)
        assert xml.count("<m:oMath>") == 2, "Formeln in Zellen als Word-Formel"
        assert "<w:tbl>" in xml
    else:
        inhalt = zipfile.ZipFile(io.BytesIO(data)).read("content.xml").decode("utf-8")
        assert inhalt.count("draw:object") >= 2


@_needs_pandoc
async def test_kein_titel_vor_dem_dokument():
    bloecke, api = office._bloecke_sync({"a": "x"})
    data = await office.dokument_zu_office(bloecke["a"], api_version=api, fmt="docx")
    assert 'w:val="Title"' not in _docx_xml(data)
