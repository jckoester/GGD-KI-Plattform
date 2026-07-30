import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import httpx

from app.render import service, cache, sidecar
from app.render.sidecar import RenderError


# ========== Service: Registry + Cache + Fehlerpfad ==========


@pytest.mark.asyncio
async def test_cache_hit_skips_renderer():
    """Cache-Treffer → kein Sidecar-Call, kein erneutes Cachen."""
    db = MagicMock()
    renderer = AsyncMock(return_value="<svg>fresh</svg>")
    with patch.dict(service.RENDERERS, {"circuit": renderer}), \
         patch("app.render.cache.get_cached_svg", new=AsyncMock(return_value="<svg>cached</svg>")), \
         patch("app.render.cache.set_cached_svg", new=AsyncMock()) as set_:
        res = await service.render(db, "circuit", "\\draw (0,0);")
    assert res == {"svg": "<svg>cached</svg>", "cached": True, "error": None}
    renderer.assert_not_awaited()
    set_.assert_not_awaited()


@pytest.mark.asyncio
async def test_success_caches_result():
    db = MagicMock()
    renderer = AsyncMock(return_value="<svg>ok</svg>")
    with patch.dict(service.RENDERERS, {"circuit": renderer}), \
         patch("app.render.cache.get_cached_svg", new=AsyncMock(return_value=None)), \
         patch("app.render.cache.set_cached_svg", new=AsyncMock()) as set_:
        res = await service.render(db, "circuit", "src")
    assert res["svg"] == "<svg>ok</svg>"
    assert res["cached"] is False and res["error"] is None
    set_.assert_awaited_once()


@pytest.mark.asyncio
async def test_render_error_returns_error_svg_and_does_not_cache():
    db = MagicMock()
    renderer = AsyncMock(side_effect=RenderError("kaputte Schaltung"))
    with patch.dict(service.RENDERERS, {"circuit": renderer}), \
         patch("app.render.cache.get_cached_svg", new=AsyncMock(return_value=None)), \
         patch("app.render.cache.set_cached_svg", new=AsyncMock()) as set_:
        res = await service.render(db, "circuit", "src")
    assert res["svg"] == service.ERROR_SVG
    assert res["error"] == "kaputte Schaltung"
    set_.assert_not_awaited()  # Fehler werden NICHT gecacht


@pytest.mark.asyncio
async def test_timeout_returns_error_svg():
    db = MagicMock()
    renderer = AsyncMock(side_effect=RenderError("Render-Timeout (Sidecar)"))
    with patch.dict(service.RENDERERS, {"circuit": renderer}), \
         patch("app.render.cache.get_cached_svg", new=AsyncMock(return_value=None)), \
         patch("app.render.cache.set_cached_svg", new=AsyncMock()):
        res = await service.render(db, "circuit", "src")
    assert res["svg"] == service.ERROR_SVG
    assert "Timeout" in res["error"]


@pytest.mark.asyncio
async def test_unknown_kind_returns_error_svg():
    res = await service.render(MagicMock(), "bogus", "src")
    assert res["svg"] == service.ERROR_SVG
    assert "unbekannt" in res["error"].lower()


@pytest.mark.asyncio
async def test_empty_source_skips_renderer():
    renderer = AsyncMock()
    with patch.dict(service.RENDERERS, {"circuit": renderer}):
        res = await service.render(MagicMock(), "circuit", "   ")
    assert res["svg"] == service.ERROR_SVG
    renderer.assert_not_awaited()


def test_svg_hash_stable_and_kind_sensitive():
    assert cache.svg_hash("circuit", "abc") == cache.svg_hash("circuit", "abc")
    assert cache.svg_hash("circuit", "abc") != cache.svg_hash("plot", "abc")
    assert cache.svg_hash("circuit", "abc") != cache.svg_hash("circuit", "abd")


# ========== Sidecar-Client ==========


def _resp(status, json_body=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_body if json_body is not None else {}
    r.text = text
    return r


@pytest.mark.asyncio
async def test_sidecar_render_circuit_ok():
    http = MagicMock()
    http.post = AsyncMock(return_value=_resp(200, {"svg": "<svg>x</svg>"}))
    with patch.object(sidecar, "_get_client", return_value=http):
        svg = await sidecar.render_circuit("src")
    assert svg == "<svg>x</svg>"


@pytest.mark.asyncio
async def test_sidecar_render_circuit_422_raises():
    http = MagicMock()
    http.post = AsyncMock(return_value=_resp(422, {"error": "kaputt"}, "kaputt"))
    with patch.object(sidecar, "_get_client", return_value=http):
        with pytest.raises(RenderError, match="kaputt"):
            await sidecar.render_circuit("src")


@pytest.mark.asyncio
async def test_sidecar_render_circuit_no_svg_raises():
    http = MagicMock()
    http.post = AsyncMock(return_value=_resp(200, {}))
    with patch.object(sidecar, "_get_client", return_value=http):
        with pytest.raises(RenderError):
            await sidecar.render_circuit("src")


@pytest.mark.asyncio
async def test_sidecar_timeout_raises_render_error():
    http = MagicMock()
    http.post = AsyncMock(side_effect=httpx.TimeoutException("t"))
    with patch.object(sidecar, "_get_client", return_value=http):
        with pytest.raises(RenderError, match="Timeout"):
            await sidecar.render_circuit("src")


@pytest.mark.asyncio
async def test_sidecar_unreachable_raises_render_error():
    http = MagicMock()
    http.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    with patch.object(sidecar, "_get_client", return_value=http):
        with pytest.raises(RenderError, match="erreichbar"):
            await sidecar.render_circuit("src")
