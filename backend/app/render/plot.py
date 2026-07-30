"""Funktionsgraphen-Renderer (Phase 17, ```plot).

Deklarative Plot-Spec (YAML) → matplotlib-SVG, **in-process im Backend** (kein Sidecar).
Kern-Invariante: **kein Ausführen von Modell-Output.** Funktions-Terme werden über eine
`lark`-Whitelist-Grammatik geparst und der Baum **numerisch über numpy** ausgewertet —
**kein `eval`, kein sympy**. Nur `x`, Zahlen, die Konstanten pi/e, die Operatoren
`+ - * / ^` (explizites `*`) und eine feste Funktions-Whitelist sind zulässig.

v1-Umfang (Plan E9/C4): mehrere reelle Funktionen ``y=f(x)``, benannte Punkte, Wertebereich,
optionaler y-Bereich, Gitter, vertikale Asymptoten. Erweiterungen (Ableitungen, Ungleichungen,
Parameter-/implizite Kurven, Scatter) sind bewusst raus (Todo.md).
"""
from __future__ import annotations

import asyncio
import io
import logging
from typing import Callable, Optional

import numpy as np
import yaml
from lark import Lark, Transformer, v_args
from lark.exceptions import LarkError, VisitError
from pydantic import BaseModel, field_validator, model_validator

from app.config import settings
from app.render.errors import RenderError

logger = logging.getLogger(__name__)

# ── Grenzen (bounden Arbeit + DoS-Fläche) ────────────────────────────────────
SAMPLES = 1000
MAX_FUNCTIONS = 12
MAX_POINTS = 60
MAX_ASYMPTOTES = 20
MAX_EXPR_LEN = 500

# ── Ausdrucks-Whitelist (numpy-Vektorfunktionen) ─────────────────────────────
_FUNCS: dict[str, Callable] = {
    "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan,
    "sinh": np.sinh, "cosh": np.cosh, "tanh": np.tanh,
    "exp": np.exp, "ln": np.log, "log": np.log,   # log = natürlicher Logarithmus
    "log10": np.log10, "lg": np.log10,            # lg = Zehnerlogarithmus
    "sqrt": np.sqrt, "abs": np.abs, "sign": np.sign,
    "floor": np.floor, "ceil": np.ceil,
}
_CONSTS: dict[str, float] = {"pi": float(np.pi), "e": float(np.e)}


class PlotError(RenderError):
    """Ungültige Plot-Spec oder unzulässiger Ausdruck."""


# ── lark-Grammatik: Präzedenz ^ > unär- > * / > + - ; explizites * ; nur x ───
_GRAMMAR = r"""
?start: sum
?sum: product
    | sum "+" product   -> add
    | sum "-" product   -> sub
?product: unary
        | product "*" unary -> mul
        | product "/" unary -> div
?unary: power
      | "-" unary           -> neg
?power: atom
      | atom "^" unary      -> pow
?atom: NUMBER               -> number
     | NAME "(" sum ")"     -> func
     | NAME                 -> name
     | "(" sum ")"
NUMBER: /[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?/
NAME: /[a-zA-Z_][a-zA-Z0-9_]*/
%import common.WS
%ignore WS
"""

_PARSER = Lark(_GRAMMAR, parser="lalr")


@v_args(inline=True)
class _ToCallable(Transformer):
    """Baut aus dem Parse-Baum eine vektorisierte Funktion ``f(x)`` (numpy).

    Jede Regel liefert ein Callable ``x -> Wert``. Unbekannte Namen/Funktionen werfen
    PlotError (die Whitelist-Grenze). Rein numerisch — kein eval.
    """
    def number(self, tok):
        v = float(tok)
        return lambda x: v

    def name(self, tok):
        s = str(tok)
        if s == "x":
            return lambda x: x
        if s in _CONSTS:
            c = _CONSTS[s]
            return lambda x: c
        raise PlotError(f"unbekannter Name im Ausdruck: {s!r} (erlaubt: x, pi, e)")

    def func(self, name_tok, arg):
        fn = _FUNCS.get(str(name_tok))
        if fn is None:
            raise PlotError(f"unbekannte Funktion: {str(name_tok)!r}")
        return lambda x: fn(arg(x))

    def add(self, a, b): return lambda x: a(x) + b(x)
    def sub(self, a, b): return lambda x: a(x) - b(x)
    def mul(self, a, b): return lambda x: a(x) * b(x)
    def div(self, a, b): return lambda x: a(x) / b(x)
    def pow(self, a, b): return lambda x: np.power(a(x), b(x))
    def neg(self, a): return lambda x: -a(x)


def compile_expr(expr: str) -> Callable[[np.ndarray], np.ndarray]:
    """Parst einen Funktionsterm zu einer vektorisierten numpy-Funktion. Wirft PlotError."""
    if not expr or not expr.strip():
        raise PlotError("leerer Ausdruck")
    if len(expr) > MAX_EXPR_LEN:
        raise PlotError("Ausdruck zu lang")
    # LLMs schreiben Potenzen oft als `**` (Python) statt `^`. In Mathe-Termen meint `**`
    # eindeutig Potenzierung → sicher ersetzbar (kein anderer Sinn).
    expr = expr.replace("**", "^")
    try:
        tree = _PARSER.parse(expr)
    except LarkError:
        raise PlotError(f"Ausdruck nicht interpretierbar: {expr!r} (nur x, Zahlen, "
                        f"+ - * / ^, Klammern und erlaubte Funktionen; explizites *)")
    try:
        return _ToCallable().transform(tree)
    except VisitError as e:
        if isinstance(e.orig_exc, PlotError):
            raise e.orig_exc
        raise PlotError("Ausdruck nicht auswertbar")


def _split_label_expr(func_str: str) -> tuple[str, str]:
    """`f(x) = x^2` → ("f(x)", "x^2"); ohne `=` → ("y = <expr>", expr)."""
    if "=" in func_str:
        lhs, rhs = func_str.split("=", 1)
        return lhs.strip() or "f(x)", rhs.strip()
    e = func_str.strip()
    return f"y = {e}", e


# ── Pydantic-Spec ────────────────────────────────────────────────────────────
class PlotSpec(BaseModel):
    functions: list[str] = []
    domain: tuple[float, float] = (-10.0, 10.0)
    range: Optional[tuple[float, float]] = None
    points: list[list] = []
    grid: bool = False
    asymptotes: list[float] = []

    @field_validator("functions")
    @classmethod
    def _limit_functions(cls, v):
        if len(v) > MAX_FUNCTIONS:
            raise ValueError(f"zu viele Funktionen (max {MAX_FUNCTIONS})")
        return v

    @field_validator("domain")
    @classmethod
    def _domain_order(cls, v):
        if not (v[0] < v[1]):
            raise ValueError("domain: min muss < max sein")
        return v

    @field_validator("range")
    @classmethod
    def _range_order(cls, v):
        if v is not None and not (v[0] < v[1]):
            raise ValueError("range: min muss < max sein")
        return v

    @field_validator("points")
    @classmethod
    def _check_points(cls, v):
        if len(v) > MAX_POINTS:
            raise ValueError(f"zu viele Punkte (max {MAX_POINTS})")
        for p in v:
            if not isinstance(p, (list, tuple)) or len(p) < 2:
                raise ValueError("jeder Punkt braucht mindestens [x, y]")
        return v

    @field_validator("asymptotes")
    @classmethod
    def _limit_asymptotes(cls, v):
        if len(v) > MAX_ASYMPTOTES:
            raise ValueError(f"zu viele Asymptoten (max {MAX_ASYMPTOTES})")
        return v

    @model_validator(mode="after")
    def _need_content(self):
        if not self.functions and not self.points:
            raise ValueError("Plot braucht mindestens eine Funktion oder einen Punkt")
        return self


def parse_plot_spec(source: str) -> PlotSpec:
    """YAML-Quelle → validierte PlotSpec. Wirft PlotError bei ungültiger Eingabe."""
    try:
        data = yaml.safe_load(source)
    except yaml.YAMLError as e:
        raise PlotError(f"Plot-Spec ist kein gültiges YAML: {str(e)[:120]}")
    if not isinstance(data, dict):
        raise PlotError("Plot-Spec muss ein YAML-Objekt sein (functions, domain, …)")
    try:
        return PlotSpec.model_validate(data)
    except Exception as e:
        raise PlotError(f"ungültige Plot-Spec: {str(e)[:200]}")


def _render_sync(spec: PlotSpec) -> str:
    """Kompiliert die Terme und rendert matplotlib→SVG (synchron, in einem Thread)."""
    import matplotlib  # lazy: Import kostet ~1 s, nur bei Plot-Nutzung
    from matplotlib.figure import Figure

    # Text als Vektor-Pfade statt <use>/Glyph-Referenzen → self-contained SVG, das die
    # DOMPurify-Sanitisierung im Frontend unbeschadet übersteht (nur <path> + inline style).
    matplotlib.rcParams["svg.fonttype"] = "path"

    xs = np.linspace(spec.domain[0], spec.domain[1], SAMPLES)
    fig = Figure(figsize=(6.0, 4.0))
    ax = fig.subplots()

    has_legend = False
    with np.errstate(all="ignore"):  # div/0, log(neg) → nan/inf → matplotlib zeigt Lücken
        for func_str in spec.functions:
            label, expr = _split_label_expr(func_str)
            f = compile_expr(expr)
            ys = np.asarray(f(xs), dtype=float)
            if ys.ndim == 0:
                ys = np.full_like(xs, float(ys))
            ax.plot(xs, ys, label=label)
            has_legend = True

    for p in spec.points:
        x0, y0 = float(p[0]), float(p[1])
        ax.plot([x0], [y0], "o", color="black")
        if len(p) > 2 and p[2]:
            ax.annotate(str(p[2]), (x0, y0), textcoords="offset points", xytext=(6, 6))

    for a in spec.asymptotes:
        ax.axvline(float(a), linestyle="--", linewidth=0.8, color="gray")

    ax.set_xlim(spec.domain[0], spec.domain[1])
    if spec.range is not None:
        ax.set_ylim(spec.range[0], spec.range[1])
    ax.axhline(0, linewidth=0.6, color="black")
    ax.axvline(0, linewidth=0.6, color="black")
    if spec.grid:
        ax.grid(True, linewidth=0.4, alpha=0.6)
    if has_legend:
        ax.legend(fontsize="small")

    buf = io.StringIO()
    fig.savefig(buf, format="svg")
    svg = buf.getvalue()
    # Nur das <svg>-Element ausliefern (ohne XML-Deklaration/DOCTYPE) — analog zum
    # CircuiTikZ-SVG; das Frontend sanitisiert es zusätzlich (DOMPurify).
    idx = svg.find("<svg")
    return svg[idx:] if idx >= 0 else svg


async def render_plot(source: str) -> str:
    """Registry-Renderer für kind='plot': YAML-Spec → SVG. Wirft RenderError."""
    spec = parse_plot_spec(source)  # schnelle Validierung außerhalb des Threads
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_render_sync, spec),
            timeout=settings.plot_render_timeout,
        )
    except asyncio.TimeoutError:
        raise RenderError("Plot-Render-Timeout")
    except PlotError:
        raise
    except Exception as e:
        logger.exception("Plot-Render fehlgeschlagen")
        raise RenderError(f"Plot-Render fehlgeschlagen: {str(e)[:150]}")
