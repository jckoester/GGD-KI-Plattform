"""Unit-Tests: Tabellenlinien und Querformat in DOCX/ODT (0.39)."""
import io
import zipfile

import pytest

from app.export import nachbearbeitung as nb
from app.export import pandoc

_needs_pandoc = pytest.mark.skipif(not pandoc.pandoc_available(), reason="pandoc nicht installiert")


# ── XML (ohne Pandoc) ─────────────────────────────────────────────────────────

def test_docx_rahmen_an_der_richtigen_stelle():
    xml = ('<w:tblPr><w:tblStyle w:val="Table" /><w:tblW w:type="pct" w:w="5000" />'
           '<w:tblLayout w:type="fixed" /><w:tblLook w:val="0020" /></w:tblPr>')
    neu = nb._docx_linien(xml)
    # Schema: tblBorders hinter tblW, vor tblLayout
    assert neu.index("<w:tblW") < neu.index("<w:tblBorders>") < neu.index("<w:tblLayout")
    assert 'w:insideV w:val="single"' in neu
    assert nb._docx_linien(neu) == neu, "vorhandene Rahmen bleiben, nichts doppelt"


def test_docx_rahmen_ohne_weitere_eigenschaften():
    assert nb._docx_linien("<w:tblPr></w:tblPr>").startswith("<w:tblPr><w:tblBorders>")


def test_odt_rahmen_ersetzt_border_none():
    xml = ('<style:style style:name="TableRowCell" style:family="table-cell">'
           '<style:table-cell-properties fo:border="none" /></style:style>'
           '<style:style style:name="P1" style:family="paragraph"><style:paragraph-properties /></style:style>')
    neu = nb._odt_linien(xml)
    assert 'fo:border="none"' not in neu
    assert neu.count('fo:border="0.5pt solid #000000"') == 1
    assert "<style:paragraph-properties />" in neu, "andere Stile bleiben"


def test_docx_quer_dreht_das_vorhandene_format():
    neu = nb._docx_quer('<w:sectPr><w:pgSz w:w="11906" w:h="16838" /><w:pgMar w:top="1" /></w:sectPr>')
    assert '<w:pgSz w:w="16838" w:h="11906" w:orient="landscape" />' in neu


def test_docx_quer_ohne_format_setzt_a4_quer():
    neu = nb._docx_quer('<w:sectPr><w:footnotePr /></w:sectPr>')
    assert neu == '<w:sectPr><w:footnotePr /><w:pgSz w:w="16838" w:h="11906" w:orient="landscape" /></w:sectPr>'


def test_docx_ohne_format_wird_a4():
    """Schulvorlage ohne Seitenformat: A4 statt Words Voreinstellung."""
    xml = '<w:sectPr><w:footnotePr /><w:pgMar w:top="1134" /></w:sectPr>'
    assert nb._docx_seitenformat(xml) == (
        '<w:sectPr><w:footnotePr /><w:pgSz w:w="11906" w:h="16838" /><w:pgMar w:top="1134" /></w:sectPr>'
    )


def test_docx_eigenes_format_bleibt():
    xml = '<w:sectPr><w:pgSz w:w="12240" w:h="15840" /></w:sectPr>'
    assert nb._docx_seitenformat(xml) == xml


def test_odt_quer_tauscht_auch_bei_anderen_einheiten():
    tag = ('<style:page-layout-properties fo:page-width="8.5in" fo:page-height="11in" '
           'style:print-orientation="portrait" fo:margin-top="1in"/>')
    neu = nb._odt_quer(tag)
    assert 'fo:page-width="11in"' in neu and 'fo:page-height="8.5in"' in neu
    assert 'style:print-orientation="landscape"' in neu
    assert 'fo:margin-top="1in"' in neu


# ── Mit Pandoc: jeder Office-Export hat Linien ────────────────────────────────

@_needs_pandoc
@pytest.mark.parametrize("fmt", ["docx", "odt"])
def test_werkstatt_tabelle_hat_linien(fmt):
    data = pandoc.markdown_to_office_sync("| A | B |\n|---|---|\n| 1 | 2 |\n", fmt=fmt)
    z = zipfile.ZipFile(io.BytesIO(data))
    if fmt == "docx":
        assert "<w:tblBorders>" in z.read("word/document.xml").decode()
    else:
        inhalt = z.read("content.xml").decode()
        assert 'fo:border="none"' not in inhalt and "0.5pt solid" in inhalt
        assert z.infolist()[0].filename == "mimetype"


@_needs_pandoc
def test_werkstatt_bleibt_hochkant():
    data = pandoc.markdown_to_office_sync("Text", fmt="docx")
    assert 'w:orient="landscape"' not in zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode()
