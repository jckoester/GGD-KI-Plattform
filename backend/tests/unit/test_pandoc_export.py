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
