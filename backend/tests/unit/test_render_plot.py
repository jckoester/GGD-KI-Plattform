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
