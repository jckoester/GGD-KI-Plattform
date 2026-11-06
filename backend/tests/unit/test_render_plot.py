import math
import os

import numpy as np
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.render.plot import compile_expr, parse_plot_spec, render_plot, PlotError
from app.render.errors import RenderError
from app.render import service


# ── Ausdrucks-Parser (lark + numpy, eval-frei) ───────────────────────────────

def test_compile_basic_arithmetic():
    f = compile_expr("x^2 - 2")
    assert np.allclose(f(np.array([0.0, 1.0, 3.0])), [-2, -1, 7])


def test_compile_functions_and_consts():
    assert np.allclose(compile_expr("sin(x) + pi")(np.array([0.0])), [math.pi])
    assert np.allclose(compile_expr("sqrt(x)")(np.array([4.0, 9.0])), [2, 3])
    assert np.allclose(compile_expr("2*x + 1")(np.array([3.0])), [7])


def test_precedence_power_binds_tighter_than_unary():
    # -x^2 = -(x^2) = -4 bei x=2 (nicht (-x)^2)
    assert np.allclose(compile_expr("-x^2")(np.array([2.0])), [-4])


def test_power_right_associative():
    # 2^3^2 = 2^(3^2) = 2^9 = 512
    assert np.allclose(compile_expr("2^3^2")(np.array([0.0])), [512])


def test_accepts_python_double_star_power():
    # LLMs schreiben Potenzen oft als ** (Python) → wie ^ behandelt
    assert np.allclose(compile_expr("2 ** 3")(np.array([0.0])), [8])
    assert np.allclose(compile_expr("x**2")(np.array([3.0])), [9])


@pytest.mark.parametrize("expr", [
    "__import__('os')",           # kein Aufruf beliebiger Builtins
    "os.system('rm')",            # '.' nicht in der Grammatik
    "().__class__.__bases__",     # Sandbox-Escape-Versuch
    "foo(x)",                     # unbekannte Funktion
    "y",                          # unbekannte Variable (nur x erlaubt)
    "2x",                         # implizite Multiplikation verboten (explizites *)
    "x +",                        # Syntaxfehler
    "",                           # leer
])
def test_compile_rejects_disallowed(expr):
    with pytest.raises(PlotError):
        compile_expr(expr)


def test_division_by_zero_is_nan_not_crash():
    f = compile_expr("1 / x")
    with np.errstate(all="ignore"):
        y = f(np.array([0.0, 2.0]))
    assert np.isinf(y[0]) or np.isnan(y[0])
    assert np.isclose(y[1], 0.5)


# ── Plot-Spec (YAML + Pydantic) ──────────────────────────────────────────────

def test_parse_spec_valid():
    spec = parse_plot_spec("functions:\n  - f(x) = x^2\ndomain: [-3, 3]\ngrid: true")
    assert spec.functions == ["f(x) = x^2"]
    assert spec.domain == (-3.0, 3.0)
    assert spec.grid is True


def test_parse_spec_points_only():
    spec = parse_plot_spec('points:\n  - [1, 2, "P"]')
    assert spec.points and spec.points[0][2] == "P"


@pytest.mark.parametrize("src", [
    "functions: [x^2]\ndomain: [3, -3]",   # domain umgekehrt
    "grid: true",                          # weder Funktion noch Punkt
    "- 1\n- 2",                            # kein YAML-Objekt
    "functions: [x]\ndomain: [1, 2, 3]",   # domain falsche Länge
    "functions: [unterminated",            # kaputtes YAML
])
def test_parse_spec_invalid_raises(src):
    with pytest.raises(PlotError):
        parse_plot_spec(src)


# ── Render (matplotlib → SVG) ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_render_plot_produces_svg():
    src = (
        "functions:\n  - f(x) = x^2 - 2\n  - g(x) = sin(x)\n"
        "domain: [-4, 4]\npoints:\n  - [1, -1, \"P\"]\ngrid: true"
    )
    svg = await render_plot(src)
    assert svg.lstrip().startswith("<svg")
    assert "<path" in svg


@pytest.mark.asyncio
async def test_render_plot_bad_expr_raises_render_error():
    with pytest.raises(RenderError):
        await render_plot("functions: [foo(x)]\ndomain: [-1, 1]")


@pytest.mark.asyncio
async def test_render_plot_bad_spec_raises_render_error():
    with pytest.raises(RenderError):
        await render_plot("domain: [1, 0]")


# ── Registry ─────────────────────────────────────────────────────────────────

def test_plot_registered():
    assert "plot" in service.RENDERERS


# ── Achsen-Standards (0.36, Plan F7): geprüft an Achsenwerten, nicht an Pixeln ──────────────

def _figur(quelle: str):
    from app.render.plot import _zeichne, parse_plot_spec
    fig = _zeichne(parse_plot_spec(quelle))
    return fig, fig.axes[0]


def test_stil_ist_ein_buendel_mit_vorgaben():
    from app.render.plot import STANDARD, PlotStil
    assert isinstance(STANDARD, PlotStil)
    assert STANDARD.farben[0] == "#205ea6"   # Flexoki-Blau, wie die Plattform


def test_polstelle_sprengt_den_y_bereich_nicht():
    """1/x: Ohne Kappung reichte die y-Achse bis ±200, die Kurve war ein Strich."""
    _, ax = _figur("functions: ['f(x) = 1/x']\ndomain: [-5, 5]")
    unten, oben = ax.get_ylim()
    assert -20 < unten < 0 < oben < 20


def test_vorgegebener_bereich_bleibt():
    _, ax = _figur("functions: ['f(x) = 1/x']\ndomain: [-5, 5]\nrange: [-100, 100]")
    assert ax.get_ylim() == (-100, 100)


def test_gewoehnliche_funktion_wird_nicht_gekappt():
    _, ax = _figur("functions: ['f(x) = x^2']\ndomain: [-3, 3]")
    assert ax.get_ylim()[1] >= 9


def test_gleiche_skalierung_nur_bei_vergleichbaren_spannen():
    _, parabel = _figur("functions: ['f(x) = x^2 - 2']\ndomain: [-3, 3]")
    _, sinus = _figur("functions: ['f(x) = sin(x)']\ndomain: [-6.3, 6.3]")
    assert parabel.get_aspect() == 1.0
    assert sinus.get_aspect() == "auto"


def test_schoene_teilstriche():
    import math
    _, ax = _figur("functions: ['f(x) = 0.37*x + 1.3']\ndomain: [-7.3, 13.9]")
    for achse in (ax.xaxis, ax.yaxis):
        werte = achse.get_majorticklocs()
        schritt = werte[1] - werte[0]
        mantisse = schritt / 10 ** math.floor(math.log10(schritt))
        assert any(abs(mantisse - m) < 1e-9 for m in (1, 2, 2.5, 5)), schritt


def test_achsen_durch_den_ursprung_sonst_am_rand():
    _, mitte = _figur("functions: ['f(x) = x']\ndomain: [-3, 3]")
    _, rechts = _figur("functions: ['f(x) = 0.5*x + 1']\ndomain: [2, 20]")
    assert mitte.spines["left"].get_position() == ("data", 0)
    assert mitte.spines["bottom"].get_position() == ("data", 0)
    assert rechts.spines["left"].get_position() == ("axes", 0)
    assert not mitte.spines["top"].get_visible() and not mitte.spines["right"].get_visible()


def test_legende_erst_ab_zwei_funktionen():
    _, eine = _figur("functions: ['f(x) = x']\ndomain: [-3, 3]")
    _, zwei = _figur("functions: ['f(x) = x', 'g(x) = -x']\ndomain: [-3, 3]")
    assert eine.get_legend() is None
    assert zwei.get_legend() is not None


def test_farben_aus_der_palette():
    from app.render.plot import STANDARD
    _, ax = _figur("functions: ['f(x) = x', 'g(x) = -x']\ndomain: [-3, 3]")
    farben = [linie.get_color() for linie in ax.get_lines()[:2]]
    assert farben == list(STANDARD.farben[:2])
