"""Render-Service: Registry + Cache-Orchestrierung (Phase 17, §3.2).

Ein Renderer-Registry statt Einzel-Endpunkt: `circuit` läuft über den Node-Sidecar;
`plot` (matplotlib, in-process) kommt in Schritt 5 dazu. Ablauf je Render:
Hash → Cache-Treffer? → sonst Renderer → Erfolg cachen. Fehler/Timeout ergeben einen
**Fehler-Platzhalter-SVG** (nie eine gesprengte Antwort); Fehler werden **nicht** gecacht.
"""
import logging
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.render import cache
from app.render.sidecar import RenderError, render_circuit
from app.render.plot import render_plot

logger = logging.getLogger(__name__)

# Statischer, sicherer Fehler-Platzhalter (kein Nutzerinhalt eingebettet → kein Escaping-Risiko).
ERROR_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="260" height="60" viewBox="0 0 260 60" '
    'role="img" aria-label="Render-Fehler">'
    '<rect x="1" y="1" width="258" height="58" fill="none" stroke="#b91c1c" '
    'stroke-dasharray="4 3"/>'
    '<text x="130" y="35" text-anchor="middle" font-family="sans-serif" font-size="13" '
    'fill="#b91c1c">Diagramm konnte nicht gerendert werden</text></svg>'
)

# name → async renderer(source) -> svg.
RENDERERS: dict[str, Callable[[str], Awaitable[str]]] = {
    "circuit": render_circuit,   # CircuiTikZ → Node-Sidecar
    "plot": render_plot,         # Funktionsgraph → matplotlib in-process
}


async def render(db: AsyncSession, kind: str, source: str) -> dict:
    """Rendert `source` als `kind`. Gibt {svg, cached, error} zurück (wirft nie)."""
    renderer = RENDERERS.get(kind)
    if renderer is None:
        return {"svg": ERROR_SVG, "cached": False, "error": f"unbekannter Render-Typ: {kind}"}

    if not source or not source.strip():
        return {"svg": ERROR_SVG, "cached": False, "error": "leere Render-Quelle"}

    h = cache.svg_hash(kind, source)
    cached = await cache.get_cached_svg(db, h)
    if cached is not None:
        return {"svg": cached, "cached": True, "error": None}

    try:
        svg = await renderer(source)
    except RenderError as e:
        logger.warning("Render fehlgeschlagen (kind=%s): %s", kind, e)
        return {"svg": ERROR_SVG, "cached": False, "error": str(e)}

    await cache.set_cached_svg(db, h, svg)
    return {"svg": svg, "cached": False, "error": None}
