r"""Office-Export (DOCX/ODT) über Pandoc — Material-Werkstatt (Phase 19, Schritt 1).

Ein nutzereditierbares Markdown-Dokument (`artifacts.kind='document'`) wird über **Pandoc**
als Subprozess in Office-Formate konvertiert. PDF läuft **nicht** hierüber, sondern über die
bestehende weasyprint-Pipeline (`app/render/export.py`, Phase 17) — beste Vorschau-Parität.

Sicherheit (nutzereditierbarer Inhalt!):
- **`--sandbox`** — Pandoc darf nur explizit auf der Kommandozeile genannte Dateien lesen,
  kein Netzwerk, keine `\input`/Include-Ausbrüche.
- Reader **`commonmark_x`** (kein `raw_tex`) → keine LaTeX-Injektionsfläche.
- **Timeout** + **Eingabegrößen-Limit** gegen Runaways.
- Fehlt das Binary, wird sauber `PandocUnavailable` geworfen (Feature-Flag), nie ein 500-Crash.

Mathe (`$…$`) konvertiert Pandoc nativ zu **OMML** (echte, editierbare Word-Formeln). Diagramme
(circuit/plot/mermaid) kann Pandoc nicht — die werden in Schritt 2 vorher zu Bildern prärendert.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# fmt → Dateiendung des Pandoc-Ausgabeformats.
OFFICE_FORMATS = {"docx": ".docx", "odt": ".odt"}

# Reader-Dialekt: CommonMark + Erweiterungen (Tabellen, Fußnoten, Task-Listen …), **ohne**
# raw_tex. Nah an dem, was markdown-it in der Vorschau rendert (Parität-Tests → Schritt 7).
_READER = "commonmark_x"


class PandocError(Exception):
    """Pandoc-Konvertierung fehlgeschlagen (ungültige Eingabe, Timeout, Format …)."""


class PandocUnavailable(PandocError):
    """Das Pandoc-Binary ist nicht installiert — Office-Export nicht verfügbar."""


def pandoc_available() -> bool:
    """Ob das Pandoc-Binary auffindbar ist (Feature-Flag für die UI/Endpunkte)."""
    return shutil.which(settings.pandoc_bin) is not None


def _pandoc_bin() -> str:
    path = shutil.which(settings.pandoc_bin)
    if path is None:
        raise PandocUnavailable("pandoc ist nicht installiert")
    return path


def markdown_to_office_sync(
    markdown: str, *, fmt: str, reference_doc: Optional[str] = None
) -> bytes:
    """Konvertiert Markdown → DOCX/ODT (synchron). Wirft `PandocError`/`PandocUnavailable`."""
    if fmt not in OFFICE_FORMATS:
        raise PandocError(f"nicht unterstütztes Format: {fmt!r}")
    if len(markdown) > settings.pandoc_max_input_chars:
        raise PandocError("Dokument zu groß für den Export")

    binary = _pandoc_bin()
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / f"out{OFFICE_FORMATS[fmt]}"
        cmd = [binary, "-f", _READER, "-t", fmt, "--sandbox", "-o", str(out_path)]
        if reference_doc:
            ref = Path(reference_doc)
            if ref.is_file():
                cmd.append(f"--reference-doc={ref}")
            else:
                logger.warning("reference-doc nicht gefunden, ignoriere: %s", reference_doc)

        try:
            proc = subprocess.run(
                cmd,
                input=markdown.encode("utf-8"),
                capture_output=True,
                timeout=settings.pandoc_timeout,
            )
        except subprocess.TimeoutExpired:
            raise PandocError("Pandoc-Zeitüberschreitung")
        except FileNotFoundError:
            raise PandocUnavailable("pandoc ist nicht installiert")

        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", "replace")[:300]
            raise PandocError(f"Pandoc-Konvertierung fehlgeschlagen: {detail}")

        return out_path.read_bytes()


async def markdown_to_office(
    markdown: str, *, fmt: str, reference_doc: Optional[str] = None
) -> bytes:
    """Async-Wrapper (Pandoc-Subprozess in einem Thread — blockiert die Event-Loop nicht)."""
    return await asyncio.to_thread(
        markdown_to_office_sync, markdown, fmt=fmt, reference_doc=reference_doc
    )
