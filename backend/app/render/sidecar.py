"""Client zum Node-Render-Sidecar (Phase 17).

Der Sidecar (`render-sidecar/`) rendert CircuiTikZ→SVG (node-tikzjax) und KaTeX-Mathe.
Reines Rendering — kein LLM, kein Provider. Dieser Client spricht ihn intern an
(localhost/compose-Netz). Fehler/Timeout → `RenderError` (der Service macht daraus einen
Fehler-Platzhalter, statt die Antwort zu sprengen).
"""
import logging
from typing import Optional

import httpx

from app.config import settings
from app.render.errors import RenderError  # re-exportiert (Rückwärtskompat.)

logger = logging.getLogger(__name__)


_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=settings.render_timeout)
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def render_circuit(source: str) -> str:
    """POST /render/circuit → SVG (str). Wirft RenderError bei Fehler/Timeout."""
    url = f"{settings.render_sidecar_url.rstrip('/')}/render/circuit"
    try:
        resp = await _get_client().post(url, json={"source": source})
    except httpx.TimeoutException as e:
        raise RenderError("Render-Timeout (Sidecar)") from e
    except httpx.HTTPError as e:
        raise RenderError(f"Sidecar nicht erreichbar: {e}") from e

    if resp.status_code == 200:
        svg = resp.json().get("svg")
        if not svg or not isinstance(svg, str):
            raise RenderError("Sidecar lieferte kein SVG")
        return svg

    # 422 = Render-Fehler mit Nachricht (kaputte Quelle / Timeout im Sidecar).
    try:
        msg = resp.json().get("error") or resp.text[:200]
    except Exception:
        msg = resp.text[:200]
    raise RenderError(msg or f"Sidecar-Status {resp.status_code}")
