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


async def test_mermaid_wird_im_pdf_gerendert():
    """0.36: ```mermaid über Pele im Sidecar — bis dahin stand im PDF der Quelltext."""
    with patch("app.render.sidecar.render_mermaid",
               new=AsyncMock(return_value='<svg viewBox="0 0 10 10" width="10" height="10"><text>A</text></svg>')) as m:
        html = await export.render_markdown_for_pdf("```mermaid\ngraph TD; A-->B\n```")
    m.assert_awaited_once()
    assert "<svg" in html and "render-block" in html
    assert "graph TD" not in html


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


def test_zu_breites_diagramm_wird_auf_den_satzspiegel_verkleinert():
    """0.30: Eine Reihe Strukturformeln lief rechts über den Seitenrand."""
    breit = '<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="200" viewBox="0 0 1240 200"></svg>'
    aus = export._hoechstens_seitenbreit(breit)
    assert 'width="620"' in aus and 'height="100"' in aus and 'viewBox="0 0 1240 200"' in aus
    schmal = '<svg width="300" height="100" viewBox="0 0 300 100"></svg>'
    assert export._hoechstens_seitenbreit(schmal) == schmal
    ohne_masse = '<svg viewBox="0 0 10 10"></svg>'
    assert export._hoechstens_seitenbreit(ohne_masse) == ohne_masse


def test_pele_css_groesse_fliegt_raus():
    """0.36: Pele schreibt max-width:100%;height:auto ans Wurzel-<svg>. weasyprint behielt damit die
    alte Höhe als leeren Rahmen — je eine halbe Seite Leerraum über und unter dem Diagramm."""
    svg = ('<svg viewBox="0 0 400 100" width="400" height="100" '
           'style="max-width:100%;height:auto;color:#100f0f;font-family:sans-serif"><g style="height:auto"/></svg>')
    html = export._wrap("mermaid", svg, False)
    wurzel = html[html.index("<svg"):html.index(">", html.index("<svg"))]
    assert "max-width" not in wurzel and "height:auto" not in wurzel and "height: auto" not in wurzel
    assert 'color="#100f0f"' in wurzel          # Präsentationsattribute bleiben (als Attribut)
    assert '<g style="height: auto"/>' in html  # nur das Wurzelelement wird angefasst
