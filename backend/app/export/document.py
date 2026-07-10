"""Dokument-Export der Material-Werkstatt (Phase 19, Schritt 4).

Ein Markdown-Dokument (`artifacts.kind='document'`) wird in ein Ausgabeformat konvertiert:

- **PDF** über die bestehende weasyprint-Pipeline (`render.export.render_markdown_for_pdf` →
  HTML+CSS-Template → PDF). Beste Vorschau-Parität (Editor/Chat rendern dasselbe markdown-it),
  Mathe/Diagramme sind dort schon als SVG prärendert.
- **DOCX/ODT** über Pandoc (`export.pandoc`), davor circuit/plot-Diagramme via
  `export.prerender.prerender_diagrams` zu eingebetteten Bildern (Pandoc kennt die Fences nicht).
  Mathe konvertiert Pandoc nativ zu OMML.
"""
from __future__ import annotations

import os
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.ext.asyncio import AsyncSession

from app.export import pandoc
from app.export.prerender import prerender_diagrams

# fmt → MIME-Typ des Ausgabeformats.
EXPORT_MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "odt": "application/vnd.oasis.opendocument.text",
}
EXPORT_FORMATS = tuple(EXPORT_MIME)

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
_jinja = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)


async def _to_pdf(markdown: str, *, title: str, extra_css: str = "") -> bytes:
    """Markdown → PDF über weasyprint (Body via render_markdown_for_pdf, eigenes Template)."""
    import weasyprint  # lazy: Import kostet ~1 s
    from app.render.export import render_markdown_for_pdf

    body_html = await render_markdown_for_pdf(markdown)
    html_str = _jinja.get_template("document_pdf.html").render(
        title=title, body_html=body_html, extra_css=extra_css,
    )
    return weasyprint.HTML(string=html_str, base_url=_TEMPLATES_DIR).write_pdf()


async def export_document(
    db: AsyncSession,
    *,
    markdown: str,
    title: str,
    fmt: str,
    reference_doc: Optional[str] = None,
    extra_css: str = "",
) -> tuple[bytes, str]:
    """Exportiert ein Dokument. Gibt (Bytes, MIME) zurück.

    Wirft `ValueError` bei unbekanntem Format, `pandoc.PandocUnavailable` wenn Office ohne
    Pandoc angefragt wird, sonst `pandoc.PandocError` bei Konvertierungsfehlern.
    """
    if fmt not in EXPORT_MIME:
        raise ValueError(f"unbekanntes Exportformat: {fmt!r}")

    if fmt == "pdf":
        data = await _to_pdf(markdown, title=title, extra_css=extra_css)
    else:
        prepared = await prerender_diagrams(db, markdown)
        data = await pandoc.markdown_to_office(prepared, fmt=fmt, reference_doc=reference_doc)

    return data, EXPORT_MIME[fmt]
