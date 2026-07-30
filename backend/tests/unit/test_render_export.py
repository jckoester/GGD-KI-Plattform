import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.render import export
from app.render.errors import RenderError

_MATH_SVG = '<svg style="vertical-align: -0.5ex" width="2ex"><path style="fill: #000" d="M0 0"/></svg>'


# ── _svg_style_to_attrs (weasyprint-Kompatibilität) ──────────────────────────

def test_svg_style_to_attrs_moves_presentation_props():
    svg = ('<svg style="vertical-align: -0.5ex">'
           '<path style="fill: none; stroke: #b0b0b0; stroke-width: 0.4" d="M0"/></svg>')
    out = export._svg_style_to_attrs(svg)
    assert 'fill="none"' in out
    assert 'stroke="#b0b0b0"' in out
    assert 'stroke-width="0.4"' in out
    # nicht-Präsentations-Property bleibt im style
    assert 'style="vertical-align: -0.5ex"' in out
    # keine fill/stroke mehr im style
    assert 'style="fill' not in out


# ── render_markdown_for_pdf ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_inline_math_embedded_as_svg():
    with patch("app.render.sidecar.render_math", new=AsyncMock(return_value=_MATH_SVG)):
        html = await export.render_markdown_for_pdf("Die Lösung ist $x^2 - 2$ hier.")
    assert "<svg" in html
    assert "vertical-align" in html
    assert 'fill="#000"' in html          # style→attr angewandt
    assert "$x^2 - 2$" not in html         # kein Roh-Mathe mehr


@pytest.mark.asyncio
async def test_circuit_and_plot_blocks_rendered():
    with patch("app.render.sidecar.render_circuit", new=AsyncMock(return_value='<svg><path d="M0"/></svg>')), \
         patch("app.render.export.render_plot", new=AsyncMock(return_value='<svg><path d="M1"/></svg>')):
        md = "```circuitikz\n\\draw (0,0);\n```\n\n```plot\nfunctions:\n  - x\ndomain: [-1, 1]\n```"
        html = await export.render_markdown_for_pdf(md)
    assert html.count("<svg") == 2
    assert "render-block" in html          # Diagramme im zentrierten Block


@pytest.mark.asyncio
async def test_math_not_rendered_inside_code():
    with patch("app.render.sidecar.render_math", new=AsyncMock(return_value=_MATH_SVG)) as m:
        html = await export.render_markdown_for_pdf(
            "Inline-Code `$y$` und ein Block:\n\n```python\nx = '$z$'\n```"
        )
    m.assert_not_awaited()                  # $ in Code ist KEIN Mathe
    assert "$y$" in html and "$z$" in html


@pytest.mark.asyncio
async def test_render_error_falls_back_to_source():
    with patch("app.render.sidecar.render_math", new=AsyncMock(side_effect=RenderError("boom"))):
        html = await export.render_markdown_for_pdf("Formel $x^2$ Ende.")
    assert "x^2" in html                    # Quelltext im Fallback
    assert "render-error" in html


@pytest.mark.asyncio
async def test_plain_markdown_still_renders():
    html = await export.render_markdown_for_pdf("**Fett** und *kursiv*.")
    assert "<strong>Fett</strong>" in html
    assert "<em>kursiv</em>" in html


# ── render_markdown_inline_for_pdf ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_inline_variant_has_no_paragraph_wrapper():
    with patch("app.render.sidecar.render_math", new=AsyncMock(return_value='<svg id="m"><path d="M0"/></svg>')):
        html = await export.render_markdown_inline_for_pdf("Wert $x$ hier")
    assert "<p>" not in html                # inline, kein Block-Wrapper
    assert '<svg id="m"' in html
    assert "Wert" in html and "hier" in html


# ── Round-Trip: Curriculum-PDF (async-Verdrahtung + weasyprint) ──────────────

@pytest.mark.asyncio
async def test_curriculum_pdf_roundtrip():
    from app.context.curriculum_export import render_curriculum_pdf
    tree = {
        "title": "T", "metadata": {},
        "kapitel": [{"metadata": {}, "lernsequenzen": [
            {"metadata": {"eintraege": [
                {"konkretisierung": "$x$", "ik": [], "pk": [], "hinweise": "", "material": ""}
            ]}, "ik_refs": [], "pk_refs": [], "title": "L"}
        ]}],
    }
    with patch(
        "app.render.export.render_markdown_for_pdf",
        new=AsyncMock(return_value='<svg id="konk"><path d="M0"/></svg>'),
    ):
        pdf = await render_curriculum_pdf(None, tree)
    assert pdf[:4] == b"%PDF"
