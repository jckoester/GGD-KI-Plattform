"""Markdown → HTML mit server-gerenderten Formeln/Diagrammen für den PDF-Export (Phase 17, D5).

weasyprint führt kein JavaScript aus → das browserseitige KaTeX/`renderServerBlocks` greift
im PDF nicht. Diese Funktion **prä-rendert** vor weasyprint:
  - `$…$` / `$$…$$`  → MathJax-SVG (Sidecar, self-contained; inkl. mhchem)
  - ```circuitikz    → node-tikzjax-SVG (Sidecar)
  - ```plot          → matplotlib-SVG (in-process)
…und bettet das SVG in die HTML ein, die weasyprint dann zu PDF macht.

Token-basiert (markdown-it-py + `dollarmath`): Mathe wird nur außerhalb von Code erkannt.
Keine Sanitisierung nötig — weasyprint führt kein JS aus, und die SVGs stammen aus den
eigenen Renderern.
"""
from __future__ import annotations

import asyncio
import html as _html
import logging
import re

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin

from app.render import sidecar
from app.render.errors import RenderError
from app.render.plot import render_plot

logger = logging.getLogger(__name__)

# Fence-Info → Render-„kind". Varianten wie bei markdown.js (Frontend).
_FENCE_KINDS = {
    "circuitikz": "circuit", "circuittikz": "circuit", "circuit": "circuit",
    "plot": "plot",
}
_MATH_INLINE = {"math_inline", "math_inline_double"}


def _iter_tokens(tokens):
    for t in tokens:
        yield t
        if t.children:
            yield from _iter_tokens(t.children)


# weasyprint parst SVG-`style="fill:…;stroke:…"` als CSS und kennt diese Properties nicht
# ("unknown property") → Styling ginge verloren (Plots schwarz gefüllt statt gestrichelt).
# Deshalb: SVG-Präsentations-Properties aus `style` in echte Attribute umschreiben; alles
# andere (v. a. `vertical-align` am Wurzel-<svg> für die Inline-Baseline) bleibt im style.
_PRESENTATION_PROPS = {
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity",
    "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "stroke-miterlimit",
    "opacity", "color", "font-family", "font-size", "font-weight", "font-style",
    "text-anchor", "dominant-baseline",
}
_STYLE_ATTR_RE = re.compile(r'style="([^"]*)"')


def _svg_style_to_attrs(svg: str) -> str:
    def _repl(m: re.Match) -> str:
        attrs, keep = [], []
        for decl in m.group(1).split(";"):
            decl = decl.strip()
            if not decl or ":" not in decl:
                if decl:
                    keep.append(decl)
                continue
            key, val = decl.split(":", 1)
            key, val = key.strip(), val.strip()
            if key in _PRESENTATION_PROPS:
                attrs.append(f'{key}="{val}"')
            else:
                keep.append(f"{key}: {val}")
        out = " ".join(attrs)
        if keep:
            out += (" " if out else "") + f'style="{"; ".join(keep)}"'
        return out
    return _STYLE_ATTR_RE.sub(_repl, svg)


def _wrap(kind: str, svg: str, display: bool) -> str:
    svg = _svg_style_to_attrs(svg)
    if kind == "math" and not display:
        return svg  # inline (SVG trägt vertical-align + ex-Sizing selbst)
    # Display-Mathe / Diagramme: zentrierter Block.
    return f'<div class="render-block" style="text-align:center;margin:0.6em 0">{svg}</div>'


def _fallback(kind: str, content: str, err: str) -> str:
    esc = _html.escape(content)
    if kind == "math":
        return f'<code class="render-error" title="{_html.escape(err)}">{esc}</code>'
    return (
        f'<pre class="render-error" title="{_html.escape(err)}">'
        f'<code>{esc}</code></pre>'
    )


async def _render_one(kind: str, content: str, display: bool) -> str:
    if kind == "math":
        return await sidecar.render_math(content, display)
    if kind == "circuit":
        return await sidecar.render_circuit(content)
    if kind == "plot":
        return await render_plot(content)
    raise RenderError(f"unbekannter Render-Typ: {kind}")


# ── markdown-it mit dollarmath + Render-Regeln, die aus env['_render_map'] lesen ──
def _build_md() -> MarkdownIt:
    # commonmark + GFM-Tabellen/Strikethrough — nähert den PDF-Export an die Vorschau (marked,
    # GFM) an (Phase-19-Parität). Zusätzlich von curriculum-/lesson-PDF genutzt (additiv, sicher).
    md = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
    md.use(dollarmath_plugin, double_inline=True)

    def _from_map(self, tokens, idx, options, env):
        return env.get("_render_map", {}).get(id(tokens[idx]), "")

    def _fence_rule(self, tokens, idx, options, env):
        info = (tokens[idx].info or "").strip().lower()
        if info in _FENCE_KINDS:
            return env.get("_render_map", {}).get(id(tokens[idx]), "")
        return self.fence(tokens, idx, options, env)  # normale Code-Darstellung

    md.add_render_rule("math_inline", _from_map)
    md.add_render_rule("math_inline_double", _from_map)
    md.add_render_rule("math_block", _from_map)
    md.add_render_rule("fence", _fence_rule)
    return md


_MD = _build_md()


async def _collect_and_render(tokens_iter) -> dict:
    """Sammelt Mathe-/Diagramm-Tokens, rendert sie parallel zu SVG-Fragmenten (id→html).

    Fehler → Fallback (Quelltext), nie ein Absturz.
    """
    jobs = []  # (token, kind, content, display)
    for t in tokens_iter:
        if t.type in _MATH_INLINE:
            jobs.append((t, "math", t.content, t.type == "math_inline_double"))
        elif t.type == "math_block":
            jobs.append((t, "math", t.content, True))
        elif t.type == "fence":
            k = _FENCE_KINDS.get((t.info or "").strip().lower())
            if k:
                jobs.append((t, k, t.content, False))

    if not jobs:
        return {}

    async def _run(job):
        tok, kind, content, display = job
        try:
            svg = await _render_one(kind, content, display)
            return id(tok), _wrap(kind, svg, display)
        except RenderError as e:
            logger.warning("PDF-Prärender (%s) fehlgeschlagen: %s", kind, e)
            return id(tok), _fallback(kind, content, str(e))

    return dict(await asyncio.gather(*[_run(j) for j in jobs]))


async def render_markdown_for_pdf(text: str) -> str:
    """Markdown → HTML (Block) mit eingebetteten Mathe-/Diagramm-SVGs."""
    if not text:
        return ""
    tokens = _MD.parse(text)
    svg_map = await _collect_and_render(_iter_tokens(tokens))
    return _MD.renderer.render(tokens, _MD.options, {"_render_map": svg_map})


async def render_markdown_inline_for_pdf(text: str) -> str:
    """Markdown → Inline-HTML (ohne <p>-Wrapper) mit eingebetteten Inline-Mathe-SVGs.

    Für kompakte Kontexte (Tabellenzellen, Stundenziel). Block-Elemente (Listen,
    ```-Diagramme) erscheinen hier bewusst nicht — die gehören nicht in eine Zelle.
    """
    if not text:
        return ""
    tokens = _MD.parseInline(text, {})
    children = tokens[0].children if tokens and tokens[0].children else []
    svg_map = await _collect_and_render(iter(children))
    return _MD.renderer.renderInline(children, _MD.options, {"_render_map": svg_map})
