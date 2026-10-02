"""Dialekt-Parität der Export-Pfade (Phase 19, Schritt 7).

Die Editor-Vorschau nutzt `marked` (GFM). Die zwei Export-Pfade müssen dieselben Kern-Features
tragen, sonst sieht die Lehrkraft etwas, das im Export verschwindet:
- **PDF** über markdown-it-py (`render.export.render_markdown_for_pdf`) — Tabellen/Strikethrough
  wurden für Phase 19 aktiviert.
- **DOCX/ODT** über Pandoc `commonmark_x+hard_line_breaks`.

Bewusst dokumentierte Abweichung (siehe docs/dev/material-werkstatt.md): Task-Listen zeigt die
Vorschau als Checkbox, beide Exporte als `[ ]/[x]`. Fußnoten können seit 0.12 alle drei — bis
dahin prüfte dieser Satz sie nur für DOCX, und das PDF zeigte unbemerkt `[^1]` als Rohtext.
"""
import io
import os
import zipfile

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.export import pandoc
from app.render.export import render_markdown_for_pdf

_HAVE_PANDOC = pandoc.pandoc_available()
_needs_pandoc = pytest.mark.skipif(not _HAVE_PANDOC, reason="pandoc nicht installiert")

_TABLE = "| A | B |\n|---|---|\n| 1 | 2 |\n"


# ── PDF-Pfad (markdown-it-py) ─────────────────────────────────────────────────

async def test_pdf_renders_table():
    html = await render_markdown_for_pdf(_TABLE)
    assert "<table>" in html and "<td>" in html


async def test_pdf_renders_strikethrough():
    html = await render_markdown_for_pdf("~~weg~~")
    assert "<s>" in html


async def test_pdf_renders_footnote():
    html = await render_markdown_for_pdf("Text[^1]\n\n[^1]: Fußnote.")
    assert "[^1]" not in html
    assert '<sup class="footnote-ref"><a href="#fn1" id="fnref1">1</a></sup>' in html
    assert '<section class="footnotes">' in html and "Fußnote." in html


async def test_pdf_footnote_ohne_ruecksprungpfeil():
    # Auf Papier führt er nirgendwohin, und „↩︎" fehlt in den Schriften der Vorlage.
    assert "↩" not in await render_markdown_for_pdf("Text[^1]\n\n[^1]: Fußnote.")


# ── DOCX-Pfad (Pandoc) ────────────────────────────────────────────────────────

def _docx(md: str) -> str:
    data = pandoc.markdown_to_office_sync(md, fmt="docx")
    return zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")


@_needs_pandoc
def test_docx_table():
    assert "w:tbl" in _docx(_TABLE)


@_needs_pandoc
def test_docx_strikethrough():
    assert "w:strike" in _docx("~~weg~~")


@_needs_pandoc
def test_docx_hard_line_break():
    # Einzelner Zeilenumbruch → echter Umbruch (wie die Vorschau mit breaks:true).
    assert "<w:br" in _docx("Zeile1\nZeile2")


@_needs_pandoc
def test_docx_footnote_survives():
    data = pandoc.markdown_to_office_sync("Text[^1]\n\n[^1]: Fußnote.", fmt="docx")
    assert "word/footnotes.xml" in zipfile.ZipFile(io.BytesIO(data)).namelist()


@_needs_pandoc
def test_docx_task_list_text_survives():
    # Task-Text darf nicht verloren gehen (Checkbox-Optik weicht bewusst ab: [ ]/[x]).
    doc = _docx("- [ ] offen\n- [x] erledigt\n")
    assert "offen" in doc and "erledigt" in doc
