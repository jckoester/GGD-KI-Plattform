"""Diagramm-Prärender für den Office-Export (Phase 19, Schritt 2).

Pandoc kennt weder CircuiTikZ noch unsere ```plot-Spec. Vor der Pandoc-Konvertierung werden
darum ```circuitikz- und ```plot-Fences über die **Phase-17-Render-Pipeline** zu SVG gerendert
und als **Bild-Daten-URI** ins Markdown eingebettet.

Warum Daten-URI (statt Bilddatei): Pandoc läuft mit `--sandbox` und darf **keine lokalen Dateien**
lesen (Sicherheit bei nutzereditierbarem Inhalt) — eine `data:`-URI umgeht das und wird trotzdem
eingebettet (empirisch bestätigt, DOCX/ODT). SVG genügt (moderne Word/LibreOffice rendern es);
eine optionale SVG→PNG-Stufe für ältere Office-Versionen steht in der Todo.md.

Mathe (`$…$`) wird **nicht** prärendert — Pandoc konvertiert sie nativ zu OMML. Mermaid bleibt v1
ein Codeblock (kein serverseitiger Mermaid-Renderer; Todo).
"""
from __future__ import annotations

import base64
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.render import service

# ```circuitikz / ```plot-Fence (gleiche Backtick-Zahl öffnend/schließend, Sprache
# case-insensitiv — wie die Chat-Normalisierung in markdown.js).
_FENCE_RE = re.compile(
    r"(?msi)^(?P<fence>`{3,})[ \t]*(?P<lang>circuitikz|plot)[ \t]*\r?\n"
    r"(?P<body>.*?)\r?\n(?P=fence)[ \t]*$"
)
_LANG_KIND = {"circuitikz": "circuit", "plot": "plot"}


def _svg_data_uri(svg: str) -> str:
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


async def prerender_diagrams(db: AsyncSession, markdown: str) -> str:
    """Ersetzt ```circuitikz/```plot-Fences durch eingebettete SVG-Bilder (Daten-URI).

    Render-Fehler lassen den Fence unverändert (er erscheint dann als Codeblock im Export —
    nie ein Absturz). Andere Fences (mermaid, Code) und Mathe bleiben unberührt.
    """
    matches = list(_FENCE_RE.finditer(markdown))
    if not matches:
        return markdown

    out: list[str] = []
    last = 0
    for m in matches:
        out.append(markdown[last:m.start()])
        kind = _LANG_KIND[m.group("lang").lower()]
        result = await service.render(db, kind, m.group("body"))
        if result.get("error"):
            out.append(m.group(0))  # Render-Fehler → Fence als Codeblock belassen
        else:
            out.append(f"![Diagramm]({_svg_data_uri(result['svg'])})")
        last = m.end()
    out.append(markdown[last:])
    return "".join(out)
