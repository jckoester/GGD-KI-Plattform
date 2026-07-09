"""Unit-Tests: Diagramm-Prärender für den Office-Export (Phase 19, Schritt 2)."""
import base64
import io
import os
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.export import pandoc, prerender

_HAVE_PANDOC = pandoc.pandoc_available()


def _decode_data_uri(md: str) -> str:
    # extrahiert das erste eingebettete SVG aus ![...](data:image/svg+xml;base64,XXX)
    start = md.index("base64,") + len("base64,")
    end = md.index(")", start)
    return base64.b64decode(md[start:end]).decode("utf-8")


async def test_plot_fence_becomes_embedded_svg(monkeypatch):
    monkeypatch.setattr(
        prerender.service, "render",
        AsyncMock(return_value={"svg": "<svg>plot</svg>", "error": None}),
    )
    md = "Vorher\n\n```plot\nfunctions:\n  - x^2\n```\n\nNachher"
    out = await prerender.prerender_diagrams(MagicMock(), md)
    assert "```plot" not in out
    assert "![Diagramm](data:image/svg+xml;base64," in out
    assert _decode_data_uri(out) == "<svg>plot</svg>"
    assert out.startswith("Vorher") and out.rstrip().endswith("Nachher")


async def test_circuit_fence_prerendered(monkeypatch):
    render = AsyncMock(return_value={"svg": "<svg>circuit</svg>", "error": None})
    monkeypatch.setattr(prerender.service, "render", render)
    md = "```circuitikz\n\\draw (0,0) to[R] (2,0);\n```"
    out = await prerender.prerender_diagrams(MagicMock(), md)
    assert "data:image/svg+xml;base64," in out
    # kind-Übersetzung circuitikz → circuit
    assert render.await_args.args[1] == "circuit"


async def test_render_error_leaves_fence(monkeypatch):
    monkeypatch.setattr(
        prerender.service, "render",
        AsyncMock(return_value={"svg": prerender.service.ERROR_SVG, "error": "TeX kaputt"}),
    )
    md = "```circuitikz\nkaputt\n```"
    out = await prerender.prerender_diagrams(MagicMock(), md)
    assert out == md   # Fence unverändert (erscheint als Codeblock)


async def test_mermaid_and_math_untouched(monkeypatch):
    monkeypatch.setattr(prerender.service, "render", AsyncMock())
    md = "Formel $x^2$\n\n```mermaid\ngraph TD; A-->B\n```"
    out = await prerender.prerender_diagrams(MagicMock(), md)
    assert out == md
    prerender.service.render.assert_not_called()


async def test_multiple_fences(monkeypatch):
    monkeypatch.setattr(
        prerender.service, "render",
        AsyncMock(return_value={"svg": "<svg/>", "error": None}),
    )
    md = "```plot\na\n```\n\ntext\n\n```plot\nb\n```"
    out = await prerender.prerender_diagrams(MagicMock(), md)
    assert out.count("data:image/svg+xml;base64,") == 2
    assert "```plot" not in out


async def test_real_plot_through_service(monkeypatch):
    # Echter matplotlib-Plot (in-process) durch service.render — Cache per Monkeypatch umgangen.
    from app.render import cache
    monkeypatch.setattr(cache, "get_cached_svg", AsyncMock(return_value=None))
    monkeypatch.setattr(cache, "set_cached_svg", AsyncMock(return_value=None))
    md = "```plot\nfunctions:\n  - f(x) = x^2\ndomain: [-3, 3]\n```"
    out = await prerender.prerender_diagrams(MagicMock(), md)
    svg = _decode_data_uri(out)
    assert svg.lstrip().startswith("<svg")


@pytest.mark.skipif(not _HAVE_PANDOC, reason="pandoc nicht installiert")
async def test_prerendered_svg_embeds_into_docx(monkeypatch):
    # End-to-End: Prärender → Pandoc → DOCX enthält das eingebettete SVG als Medium.
    monkeypatch.setattr(
        prerender.service, "render",
        AsyncMock(return_value={
            "svg": '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>',
            "error": None,
        }),
    )
    md = await prerender.prerender_diagrams(MagicMock(), "# T\n\n```plot\nx\n```")
    data = pandoc.markdown_to_office_sync(md, fmt="docx")
    media = [n for n in zipfile.ZipFile(io.BytesIO(data)).namelist() if n.startswith("word/media")]
    assert media   # mindestens ein eingebettetes Medium
