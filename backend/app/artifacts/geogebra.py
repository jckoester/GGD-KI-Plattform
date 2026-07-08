"""Plot-Spec → GeoGebra-Datei (`.ggb`) — Export für Funktionsgraphen (Phase 18, Schritt 4).

Ein ```plot-Block liefert damit zwei Ausgaben: SVG zum Anschauen/Drucken (Phase 17) und
`.ggb` zum Weiterbearbeiten im Werkzeug, das Lehrkräfte ohnehin beherrschen. Umfang bewusst
schmal (Plan §4/Schritt 4): **Funktionen, Punkte, Wertebereich** (+ Gitter/Asymptoten als
Zugabe) — kein Anspruch auf volle GeoGebra-Abdeckung.

Eine `.ggb`-Datei ist ein ZIP mit `geogebra.xml`. Die Ausdruckssyntax der Plot-Spec (``^``,
explizites ``*``, Funktions-Whitelist) ist weitgehend GeoGebra-kompatibel; nur wenige
Funktionsnamen werden übersetzt (`log`→`ln`, `log10`/`lg`→`lg`, `sign`→`sgn`).
"""
from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import escape

from app.render.plot import PlotSpec, _split_label_expr, parse_plot_spec

# Eindeutige, kollisionsfreie Labels (kein `e`/`x`/`y`) für bis zu MAX_FUNCTIONS Funktionen.
_FUNC_LABELS = ["f", "g", "h", "k", "m", "n", "p", "q", "r", "s", "t", "u"]
# Kurven-Farbpalette (RGB), zyklisch.
_COLORS = [
    (21, 101, 192), (211, 47, 47), (56, 142, 60), (123, 31, 162),
    (245, 124, 0), (0, 131, 143),
]
_VIEW_W = 800
_VIEW_H = 600


def _attr(value) -> str:
    """XML-Attributwert escapen (inkl. Anführungszeichen)."""
    return escape(str(value), {'"': "&quot;"})


def _to_ggb_expr(expr: str) -> str:
    """Plot-Ausdruck → GeoGebra-Ausdruck (Potenz `**`→`^`, abweichende Funktionsnamen)."""
    e = expr.replace("**", "^")
    e = re.sub(r"\blog10\s*\(", "lg(", e)   # log10 → lg (vor log!)
    e = re.sub(r"\blog\s*\(", "ln(", e)     # Plot-`log` ist der natürliche Logarithmus
    e = re.sub(r"\bsign\s*\(", "sgn(", e)   # sign → sgn
    return e


def _func_label(i: int) -> str:
    return _FUNC_LABELS[i] if i < len(_FUNC_LABELS) else f"f{i}"


def _point_label(i: int) -> str:
    return chr(ord("A") + i) if i < 26 else f"P{i}"


def _coord_system(spec: PlotSpec) -> str:
    """EuclidianView-Fenster aus Wertebereich (Domain=x, Range=y falls gesetzt)."""
    dmin, dmax = spec.domain
    scale = _VIEW_W / (dmax - dmin)
    x_zero = -dmin * scale
    if spec.range is not None:
        rmin, rmax = spec.range
        yscale = _VIEW_H / (rmax - rmin)
        y_zero = rmax * yscale
    else:
        yscale = scale
        y_zero = _VIEW_H / 2
    return (
        f'<coordSystem xZero="{x_zero:.4f}" yZero="{y_zero:.4f}" '
        f'scale="{scale:.4f}" yscale="{yscale:.4f}"/>'
    )


def plot_spec_to_ggb_xml(spec: PlotSpec) -> str:
    """Baut das `geogebra.xml` einer Plot-Spec (Funktionen, Punkte, Fenster, Gitter)."""
    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="utf-8"?>')
    parts.append('<geogebra format="5.0" version="5.0.0.0" app="classic">')

    # Ansicht
    grid = "true" if spec.grid else "false"
    parts.append("<gui><window width=\"%d\" height=\"%d\"/></gui>" % (_VIEW_W, _VIEW_H))
    parts.append("<euclidianView>")
    parts.append(f'<size width="{_VIEW_W}" height="{_VIEW_H}"/>')
    parts.append(_coord_system(spec))
    parts.append(f'<evSettings axes="true" grid="{grid}" pointCapturing="3"/>')
    parts.append('<bgColor r="255" g="255" b="255"/>')
    parts.append('<axis id="0" show="true" label="x" tickStyle="1" showNumbers="true"/>')
    parts.append('<axis id="1" show="true" label="y" tickStyle="1" showNumbers="true"/>')
    parts.append("</euclidianView>")
    parts.append('<kernel><decimals val="2"/></kernel>')

    # Konstruktion
    parts.append('<construction title="" author="" date="">')

    for i, func_str in enumerate(spec.functions):
        _, expr = _split_label_expr(func_str)
        label = _func_label(i)
        exp = f"{label}(x)={_to_ggb_expr(expr)}"
        r, g, b = _COLORS[i % len(_COLORS)]
        parts.append(f'<expression label="{_attr(label)}" exp="{_attr(exp)}"/>')
        parts.append(f'<element type="function" label="{_attr(label)}">')
        parts.append('<show object="true" label="true"/>')
        parts.append(f'<objColor r="{r}" g="{g}" b="{b}" alpha="0"/>')
        parts.append('<lineStyle thickness="5" type="0"/>')
        parts.append("</element>")

    for i, pt in enumerate(spec.points):
        x0, y0 = float(pt[0]), float(pt[1])
        label = _point_label(i)
        caption = str(pt[2]) if len(pt) > 2 and pt[2] else None
        parts.append(f'<element type="point" label="{_attr(label)}">')
        # labelMode 3 = Beschriftung (Caption) anzeigen, sonst Name.
        parts.append(f'<show object="true" label="true" labelMode="{3 if caption else 0}"/>')
        if caption:
            parts.append(f'<caption val="{_attr(caption)}"/>')
        parts.append(f'<coords x="{x0:.6g}" y="{y0:.6g}" z="1"/>')
        parts.append('<pointSize val="4"/>')
        parts.append('<objColor r="0" g="0" b="0" alpha="0"/>')
        parts.append("</element>")

    for i, a in enumerate(spec.asymptotes):
        label = f"v_{{{i + 1}}}"
        parts.append(f'<expression label="{_attr(label)}" exp="{_attr(f"x={float(a):.6g}")}"/>')
        parts.append(f'<element type="line" label="{_attr(label)}">')
        parts.append('<show object="true" label="false"/>')
        parts.append('<objColor r="128" g="128" b="128" alpha="0"/>')
        parts.append('<lineStyle thickness="3" type="10"/>')  # type 10 = gestrichelt
        parts.append("</element>")

    parts.append("</construction>")
    parts.append("</geogebra>")
    return "\n".join(parts)


def ggb_bytes_from_spec(spec: PlotSpec) -> bytes:
    """PlotSpec → `.ggb`-ZIP (enthält `geogebra.xml`)."""
    xml = plot_spec_to_ggb_xml(spec)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("geogebra.xml", xml)
    return buf.getvalue()


def ggb_bytes_from_source(source: str) -> bytes:
    """Rohe Plot-Spec (YAML) → `.ggb`-ZIP. Wirft `RenderError`/`PlotError` bei ungültiger Spec."""
    spec = parse_plot_spec(source)
    return ggb_bytes_from_spec(spec)
