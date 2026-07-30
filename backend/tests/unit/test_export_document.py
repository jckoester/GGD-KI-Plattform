"""Unit-Tests: Dokument-Export PDF/DOCX/ODT (Phase 19, Schritt 4).

PDF läuft über weasyprint (installiert). Office-Formate über Pandoc (`skipif`, wie
test_pandoc_export). Plain-Markdown ohne Diagramme → kein Sidecar nötig.
"""
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.export import document, pandoc

_HAVE_PANDOC = pandoc.pandoc_available()
_needs_pandoc = pytest.mark.skipif(not _HAVE_PANDOC, reason="pandoc nicht installiert")

_MD = "# Arbeitsblatt\n\nEin Absatz mit **fett**.\n\n- Punkt 1\n- Punkt 2\n"


async def test_export_pdf():
    data, mime = await document.export_document(
        MagicMock(), markdown=_MD, title="Arbeitsblatt", fmt="pdf"
    )
    assert mime == "application/pdf"
    assert data[:5] == b"%PDF-"


@_needs_pandoc
async def test_export_docx():
    data, mime = await document.export_document(
        MagicMock(), markdown=_MD, title="Arbeitsblatt", fmt="docx"
    )
    assert mime.endswith("wordprocessingml.document")
    assert data[:2] == b"PK"


@_needs_pandoc
async def test_export_odt():
    data, mime = await document.export_document(
        MagicMock(), markdown=_MD, title="Arbeitsblatt", fmt="odt"
    )
    assert mime == "application/vnd.oasis.opendocument.text"
    assert data[:2] == b"PK"


async def test_export_unknown_format_raises():
    with pytest.raises(ValueError):
        await document.export_document(MagicMock(), markdown=_MD, title="x", fmt="txt")


async def test_office_prerenders_before_pandoc(monkeypatch):
    # Der Office-Pfad muss prerender_diagrams durchlaufen (Diagramme→Bild), dann Pandoc.
    pre = AsyncMock(return_value="# ok")
    to_office = AsyncMock(return_value=b"PKfake")
    monkeypatch.setattr(document, "prerender_diagrams", pre)
    monkeypatch.setattr(document.pandoc, "markdown_to_office", to_office)
    data, mime = await document.export_document(MagicMock(), markdown="# x", title="x", fmt="docx")
    pre.assert_awaited_once()
    to_office.assert_awaited_once()
    assert data == b"PKfake"


async def test_office_unavailable_propagates(monkeypatch):
    monkeypatch.setattr(document, "prerender_diagrams", AsyncMock(return_value="# x"))
    monkeypatch.setattr(
        document.pandoc, "markdown_to_office",
        AsyncMock(side_effect=pandoc.PandocUnavailable("weg")),
    )
    with pytest.raises(pandoc.PandocUnavailable):
        await document.export_document(MagicMock(), markdown="# x", title="x", fmt="docx")
