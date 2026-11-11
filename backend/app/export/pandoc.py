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
import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# fmt → Dateiendung des Pandoc-Ausgabeformats.
OFFICE_FORMATS = {"docx": ".docx", "odt": ".odt"}

# Reader-Dialekt: CommonMark + Erweiterungen (Tabellen, Fußnoten, Task-Listen, Strikethrough …),
# **ohne** raw_tex. `hard_line_breaks` spiegelt das `breaks: true` der Vorschau (marked) — ein
# einzelner Zeilenumbruch wird zum Umbruch, nicht zum Leerzeichen (Parität, Schritt 7).
#
# `-implicit_figures` (0.34): Ein Bild allein im Absatz wird sonst eine Abbildung, und der
# Alternativtext steht als **Unterschrift** darunter — „Strukturformel“, „Schaltplan“,
# „Funktionsgraph“ unter jedem vorgerenderten Diagramm (Befund 03.11.2026, 0.30). Ob die
# Erweiterung bei `commonmark_x` voreingestellt ist, hängt an der Pandoc-Fassung (3.13: aus);
# ausdrücklich abgeschaltet gilt es für jede. Der Alternativtext bleibt erhalten (`descr`).
# Der PDF-Weg (markdown-it, weasyprint) kannte nie Unterschriften — jetzt gleich.
_READER = "commonmark_x+hard_line_breaks-implicit_figures"


# ── TeX-Klammer-Notation `\(…\)` / `\[…\]` → `$…$` / `$$…$$` ──────────────────
#
# ⚠️ `commonmark_x` kennt nur Dollar-Begrenzer; `tex_math_single_backslash` gibt es für diesen
# Leser nicht. Ohne Umschreibung frisst die Escape-Regel den Backslash: Aus `\[y\]` wurde im DOCX
# der Text „[y]“, aus `\(x^2\)` „(x^2)“ (Befund 10.11.2026). Betroffen war jede abgesetzte Formel
# aus dem Chat — `pedagogy.yaml` lässt die Modelle `\[…\]` schreiben, der Formel-Editor (0.38)
# setzt `\(…\)` ein, Bildungsplan-Titel tragen `\(…\)`. Der PDF-Weg hat dafür eine eigene
# markdown-it-Regel (`app.render.export._klammer_mathe_regel`); Vorschau: `markdown.js`.

_ZAUN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _klammern_im_text(text: str) -> str:
    """Schreibt Klammer-Mathe in einem Textstück ohne Codeblöcke um; Code-Spans bleiben."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "`":
            j = i
            while j < n and text[j] == "`":
                j += 1
            lauf = text[i:j]
            ende = re.compile(r"(?<!`)" + lauf + r"(?!`)").search(text, j)
            if ende is None:
                out.append(lauf)
                i = j
            else:
                out.append(text[i:ende.end()])
                i = ende.end()
            continue
        if c == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if nxt in "([":
                zu = "\\)" if nxt == "(" else "\\]"
                ende = text.find(zu, i + 2)
                inhalt = text[i + 2:ende] if ende >= 0 else ""
                # Leer, unabgeschlossen oder mit `$` darin → so lassen, wie es ist.
                if ende >= 0 and inhalt.strip() and "$" not in inhalt:
                    zeichen = "$" if nxt == "(" else "$$"
                    out.append(f"{zeichen}{inhalt.strip()}{zeichen}")
                    i = ende + 2
                    continue
            # Jedes andere Escape (auch `\\`) als Paar übernehmen — `\\(` bleibt Text.
            out.append(text[i:i + 2])
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def klammer_mathe_zu_dollar(markdown: str) -> str:
    """`\\(…\\)` → `$…$`, `\\[…\\]` → `$$…$$` — außerhalb von Codeblöcken und Code-Spans.

    Eingerückte Codeblöcke (vier Leerzeichen) werden nicht erkannt: In Listen ist eine solche
    Einrückung gewöhnlicher Text, und Dokumente der Werkstatt nutzen Zäune.
    """
    if "\\(" not in markdown and "\\[" not in markdown:
        return markdown
    zeilen = markdown.split("\n")
    out: list[str] = []
    text: list[str] = []
    zaun: str | None = None
    for zeile in zeilen:
        m = _ZAUN_RE.match(zeile)
        if zaun is None:
            if m:
                if text:
                    out.append(_klammern_im_text("\n".join(text)))
                    text = []
                zaun = m.group(1)
                out.append(zeile)
            else:
                text.append(zeile)
        else:
            out.append(zeile)
            if m and m.group(1)[0] == zaun[0] and len(m.group(1)) >= len(zaun) \
                    and not zeile.strip().lstrip(zaun[0]):
                zaun = None
    if text:
        out.append(_klammern_im_text("\n".join(text)))
    return "\n".join(out)


# ── Rohes HTML (0.39, Plan F5) ────────────────────────────────────────────────
# Pandoc liest `<br>` als `RawInline html`, und der DOCX-Writer verwirft es: Aus „a<br>b“ wurde
# „ab“. Gleiche Regel wie im PDF (`app.render.export.EXPORT_TAGS`) und in der Werkstatt-Vorschau:
# `<br>` → Zeilenumbruch, `<sub>…</sub>`/`<sup>…</sup>` → tief/hoch, jedes andere Tag fällt weg.

_TAG_RE = re.compile(r"^<(/?)([A-Za-z][A-Za-z0-9-]*)(?:\s[^<>]*)?/?>$")


def _tag(knoten) -> Optional[tuple[bool, str]]:
    """(schließend, Name) für ein rohes HTML-Tag, sonst None."""
    if isinstance(knoten, dict) and knoten.get("t") in ("RawInline", "RawBlock"):
        fmt, inhalt = knoten["c"]
        m = _TAG_RE.match(inhalt.strip()) if fmt == "html" else None
        if m:
            return m.group(1) == "/", m.group(2).lower()
    return None


def _inlines_umsetzen(liste: list) -> list:
    out: list = []
    i = 0
    while i < len(liste):
        k = liste[i]
        tag = _tag(k)
        if tag is None:
            out.append(roh_html_umsetzen(k))
            i += 1
            continue
        zu, name = tag
        if k["t"] == "RawBlock":
            i += 1  # ein Tag allein auf seiner Zeile: weg, ohne Ersatz
            continue
        if name == "br":
            out.append({"t": "LineBreak"})
        elif name in ("sub", "sup") and not zu:
            ende = next((j for j in range(i + 1, len(liste)) if _tag(liste[j]) == (True, name)), None)
            if ende is not None:
                art = "Subscript" if name == "sub" else "Superscript"
                out.append({"t": art, "c": _inlines_umsetzen(liste[i + 1:ende])})
                i = ende + 1
                continue
        # Jedes andere Tag (und ein offenes sub/sup ohne Gegenstück) fällt weg.
        i += 1
    return out


def roh_html_umsetzen(knoten):
    """Geht durch das Pandoc-Dokument und setzt rohe HTML-Tags um (siehe oben)."""
    if isinstance(knoten, list):
        if any(isinstance(k, dict) and "t" in k for k in knoten):
            if all(isinstance(k, dict) and "t" in k for k in knoten):
                if any(_tag(k) for k in knoten):
                    return _inlines_umsetzen(knoten)
            return [roh_html_umsetzen(k) for k in knoten]
        return [roh_html_umsetzen(k) for k in knoten]
    if isinstance(knoten, dict):
        return {k: roh_html_umsetzen(v) for k, v in knoten.items()}
    return knoten


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


def _ausfuehren(cmd: list[str], eingabe: bytes) -> bytes:
    """Startet Pandoc, gibt stdout zurück. Wirft `PandocError`/`PandocUnavailable`."""
    try:
        proc = subprocess.run(
            cmd, input=eingabe, capture_output=True, timeout=settings.pandoc_timeout,
        )
    except subprocess.TimeoutExpired:
        raise PandocError("Pandoc-Zeitüberschreitung")
    except FileNotFoundError:
        raise PandocUnavailable("pandoc ist nicht installiert")
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace")[:300]
        raise PandocError(f"Pandoc-Konvertierung fehlgeschlagen: {detail}")
    return proc.stdout


def _office_schreiben(
    eingabe: bytes, *, von: str, fmt: str, reference_doc: Optional[str]
) -> bytes:
    """Eingabe im Format `von` → DOCX/ODT. Office-Formate brauchen eine Ausgabedatei."""
    if fmt not in OFFICE_FORMATS:
        raise PandocError(f"nicht unterstütztes Format: {fmt!r}")
    binary = _pandoc_bin()
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / f"out{OFFICE_FORMATS[fmt]}"
        cmd = [binary, "-f", von, "-t", fmt, "--sandbox", "-o", str(out_path)]
        if reference_doc:
            ref = Path(reference_doc)
            if ref.is_file():
                cmd.append(f"--reference-doc={ref}")
            else:
                logger.warning("reference-doc nicht gefunden, ignoriere: %s", reference_doc)
        _ausfuehren(cmd, eingabe)
        return out_path.read_bytes()


def markdown_to_office_sync(
    markdown: str, *, fmt: str, reference_doc: Optional[str] = None
) -> bytes:
    """Konvertiert Markdown → DOCX/ODT (synchron). Wirft `PandocError`/`PandocUnavailable`.

    Seit 0.39 über das JSON-Dokument (zwei Aufrufe statt einem): Nur dort lassen sich rohe
    `<br>`/`<sub>`/`<sup>` umsetzen, die der DOCX-Writer sonst verwirft.
    """
    if fmt not in OFFICE_FORMATS:
        raise PandocError(f"nicht unterstütztes Format: {fmt!r}")
    return json_zu_office_sync(markdown_zu_json_sync(markdown), fmt=fmt, reference_doc=reference_doc)


async def markdown_to_office(
    markdown: str, *, fmt: str, reference_doc: Optional[str] = None
) -> bytes:
    """Async-Wrapper (Pandoc-Subprozess in einem Thread — blockiert die Event-Loop nicht)."""
    return await asyncio.to_thread(
        markdown_to_office_sync, markdown, fmt=fmt, reference_doc=reference_doc
    )


# ── Pandoc-AST (0.39, Päckchen K) ─────────────────────────────────────────────
# Für Exporte mit Tabellen, in deren Zellen Markdown steht (Stundenentwurf, Curriculum). Eine
# Markdown-Pipe-Tabelle kann keine Absätze oder Listen in Zellen, und Pandocs HTML-Leser erkennt
# `$…$` in Zellen nicht (Versuch 10.11.2026). Deshalb: Markdown → JSON lesen, die Tabelle in
# Python bauen (`app.export.office`), JSON → DOCX/ODT schreiben.

def markdown_zu_json_sync(markdown: str) -> dict:
    """Liest Markdown im Werkstatt-Dialekt als Pandoc-JSON (Dokument mit `blocks`)."""
    if len(markdown) > settings.pandoc_max_input_chars:
        raise PandocError("Dokument zu groß für den Export")
    markdown = klammer_mathe_zu_dollar(markdown)
    roh = _ausfuehren(
        [_pandoc_bin(), "-f", _READER, "-t", "json", "--sandbox"], markdown.encode("utf-8"),
    )
    dokument = json.loads(roh)
    dokument["blocks"] = roh_html_umsetzen(dokument["blocks"])
    return dokument


def json_zu_office_sync(
    dokument: dict, *, fmt: str, reference_doc: Optional[str] = None
) -> bytes:
    """Schreibt ein Pandoc-JSON-Dokument als DOCX/ODT.

    `dokument["pandoc-api-version"]` muss zum installierten Pandoc passen — sie stammt deshalb
    immer aus einem vorherigen `markdown_zu_json_sync` (Prod 3.11, lokal 3.13).
    """
    return _office_schreiben(
        json.dumps(dokument).encode("utf-8"), von="json", fmt=fmt, reference_doc=reference_doc,
    )
