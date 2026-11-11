"""Unit-Tests: Office-Export via Pandoc (Phase 19, Schritt 1).

Konvertierungs-Tests laufen nur, wenn Pandoc installiert ist (`skipif`) — im Container ist es
das (Dockerfile), lokal via `brew install pandoc`. Die Verfügbarkeits-/Fehlerpfade sind ohne
Pandoc testbar (gemockt).
"""
import io
import os
import zipfile

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.export import pandoc

_HAVE_PANDOC = pandoc.pandoc_available()
_needs_pandoc = pytest.mark.skipif(not _HAVE_PANDOC, reason="pandoc nicht installiert")


# ── Verfügbarkeit / Fehlerpfade (ohne Pandoc testbar) ─────────────────────────

def test_unsupported_format_raises():
    with pytest.raises(pandoc.PandocError):
        pandoc.markdown_to_office_sync("# Titel", fmt="pdf")   # PDF läuft NICHT über Pandoc


def test_input_too_large_raises(monkeypatch):
    monkeypatch.setattr(pandoc.settings, "pandoc_max_input_chars", 10)
    with pytest.raises(pandoc.PandocError):
        pandoc.markdown_to_office_sync("x" * 11, fmt="docx")


def test_unavailable_binary(monkeypatch):
    monkeypatch.setattr(pandoc.settings, "pandoc_bin", "definitiv-kein-pandoc-xyz")
    assert pandoc.pandoc_available() is False
    with pytest.raises(pandoc.PandocUnavailable):
        pandoc.markdown_to_office_sync("# Titel", fmt="docx")


# ── Echte Konvertierung (nur mit Pandoc) ──────────────────────────────────────

@_needs_pandoc
def test_docx_is_valid_zip():
    data = pandoc.markdown_to_office_sync("# Titel\n\nEin Absatz.", fmt="docx")
    assert data[:2] == b"PK"                       # DOCX = ZIP
    zf = zipfile.ZipFile(io.BytesIO(data))
    assert "word/document.xml" in zf.namelist()


@_needs_pandoc
def test_odt_is_valid_zip():
    data = pandoc.markdown_to_office_sync("# Titel", fmt="odt")
    assert data[:2] == b"PK"
    zf = zipfile.ZipFile(io.BytesIO(data))
    assert "content.xml" in zf.namelist()


@_needs_pandoc
def test_math_becomes_omml_in_docx():
    # Kern-Nutzen von Pandoc für DOCX: $…$ → echte Word-Formel (OMML), kein Bild-Fallback.
    data = pandoc.markdown_to_office_sync("Formel: $x^2 + 1$", fmt="docx")
    doc = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    assert "oMath" in doc


@_needs_pandoc
def test_raw_tex_is_not_executed():
    # commonmark_x + --sandbox: rohes LaTeX (\input) darf NICHT als TeX ausgeführt werden.
    data = pandoc.markdown_to_office_sync("Text \\input{/etc/passwd} Ende", fmt="docx")
    assert data[:2] == b"PK"   # kein Absturz, keine Datei-Einbindung


@_needs_pandoc
async def test_async_wrapper():
    data = await pandoc.markdown_to_office("# Async", fmt="docx")
    assert data[:2] == b"PK"


# ── Keine Bildunterschrift aus dem Alternativtext (0.34) ────────────────────────

_PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def test_reader_schaltet_abbildungen_ausdruecklich_ab():
    """Unabhängig davon, was die Pandoc-Fassung voreinstellt (3.11 auf Prod, 3.13 lokal)."""
    assert "-implicit_figures" in pandoc._READER


@_needs_pandoc
def test_alleinstehendes_bild_ohne_unterschrift():
    """Befund 03.11.2026: „Strukturformel“ stand als Unterschrift unter jedem Diagramm."""
    md = f"Vor dem Bild.\n\n![Strukturformel]({_PNG})\n\nNach dem Bild.\n"
    data = pandoc.markdown_to_office_sync(md, fmt="docx")
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    assert "<w:t>Strukturformel</w:t>" not in xml, "kein sichtbarer Text aus dem Alternativtext"
    assert "Caption" not in xml
    assert 'descr="Strukturformel"' in xml, "der Alternativtext selbst bleibt"


# ── Klammer-Mathe `\(…\)` / `\[…\]` (0.39) ─────────────────────────────────────

@pytest.mark.parametrize("quelle, erwartet", [
    ("a \\(x^2\\) b", "a $x^2$ b"),
    ("\\[ \\frac{1}{2} \\]", "$$\\frac{1}{2}$$"),
    ("Zeile\n\\[\ny = 2x\n\\]\nweiter", "Zeile\n$$y = 2x$$\nweiter"),
    ("`\\(x\\)` und \\(z\\)", "`\\(x\\)` und $z$"),                  # Code-Span bleibt
    ("```\n\\(c\\)\n```\n\\(d\\)", "```\n\\(c\\)\n```\n$d$"),        # Codeblock bleibt
    ("~~~~\n\\(c\\)\n~~~\n\\(e\\)\n~~~~", "~~~~\n\\(c\\)\n~~~\n\\(e\\)\n~~~~"),  # kürzerer Zaun schließt nicht
    ("a \\\\(x\\)", "a \\\\(x\\)"),                                   # `\\(` ist kein Begrenzer
    ("5 \\( kein Ende", "5 \\( kein Ende"),                           # unabgeschlossen
    ("\\(a$b\\)", "\\(a$b\\)"),                                       # `$` darin → unverändert
    ("\\(  \\)", "\\(  \\)"),                                         # leer
    ("ohne Formel", "ohne Formel"),
])
def test_klammer_mathe_zu_dollar(quelle, erwartet):
    assert pandoc.klammer_mathe_zu_dollar(quelle) == erwartet


@_needs_pandoc
def test_klammer_mathe_wird_word_formel():
    """Befund 10.11.2026: Aus `\\[y\\]` wurde im DOCX der Text „[y]“."""
    data = pandoc.markdown_to_office_sync("Inline \\(x^2\\).\n\n\\[y = 2x\\]\n", fmt="docx")
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    assert xml.count("<m:oMath>") == 2
    assert "[y" not in xml and "(x^2)" not in xml


# ── Rohes HTML (0.39, Plan F5) ──────────────────────────────────────────────────

@_needs_pandoc
def test_br_sub_sup_wirken_andere_tags_fallen_weg():
    d = pandoc.markdown_zu_json_sync("a<br>b H<sub>2</sub>O x<sup>2</sup> <u>unter</u>")
    inlines = d["blocks"][0]["c"]
    arten = [i["t"] for i in inlines]
    assert "LineBreak" in arten and "Subscript" in arten and "Superscript" in arten
    assert "RawInline" not in arten
    assert {"t": "Str", "c": "unter"} in inlines, "der Text eines anderen Tags bleibt"


@_needs_pandoc
def test_br_in_tabellenzelle():
    """Der häufigste Fall (37 von 707 Antworten auf dev): `<br>` in einer Zelle."""
    data = pandoc.markdown_to_office_sync("| A |\n|---|\n| x<br>y |\n", fmt="docx")
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    assert "<w:br />" in xml


@_needs_pandoc
def test_tag_allein_auf_der_zeile():
    d = pandoc.markdown_zu_json_sync("vorher\n\n<div>\n\nnachher")
    assert [b["t"] for b in d["blocks"]] == ["Para", "Para"]


def test_offenes_sub_ohne_ende_faellt_weg():
    k = [{"t": "Str", "c": "H"}, {"t": "RawInline", "c": ["html", "<sub>"]}, {"t": "Str", "c": "2"}]
    assert pandoc.roh_html_umsetzen(k) == [{"t": "Str", "c": "H"}, {"t": "Str", "c": "2"}]
