"""Office-Export aus Bausteinen: Pandoc-AST für Stundenentwurf und Curriculum (0.39, Päckchen K).

Werkstatt-Dokumente sind ganz Markdown und gehen direkt durch Pandoc (`app.export.pandoc`).
Stundenentwurf und Curriculum sind dagegen **Tabellen, in deren Zellen Markdown steht** — Absätze,
Listen, Formeln, Diagramme. Dafür:

1. :func:`markdown_zu_bloecken` liest das Markdown aller Zellen in **einem** Pandoc-Aufruf zu
   Pandoc-Blöcken — mit Diagramm-Prärender und Klammer-Mathe wie in der Werkstatt, also im
   selben Dialekt.
2. Die Exportfunktion setzt daraus mit den Helfern hier ein Dokument zusammen
   (:func:`tabelle`, :func:`ueberschrift` …).
3. :func:`dokument_zu_office` schreibt es als DOCX/ODT.

⚠️ **Warum kein Markdown mit Pipe-Tabelle und kein HTML:** Pipe-Tabellen kennen nur einzeilige
Zellen; Pandocs HTML-Leser erkennt `$…$` in Tabellenzellen nicht (Versuch 10.11.2026, Pandoc 3.13).
Über den AST wurden 2 von 2 Formeln in Zellen zu Word-Formeln (OMML).

Pandoc kann keine Zellfarben setzen; der Stundenentwurf zeigt die Priorität deshalb als Kürzel
(Jan, 11.11.2026, Plan F3).
"""
from __future__ import annotations

import asyncio
import re
from typing import Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.export import pandoc
from app.export.prerender import prerender_diagrams

Block = dict
Inline = dict

_KEIN_ATTR = ["", [], []]
# Eine Zeile aus Doppelpunkten schlösse den Abschnitt, in den der Teil eingepackt wird.
_DOPPELPUNKT_ZEILE = re.compile(r"(?m)^\s*:{3,}")
_ZAUN = ":" * 12


# ── Markdown → Blöcke ─────────────────────────────────────────────────────────

def _bloecke_sync(teile: dict[str, str]) -> tuple[dict[str, list[Block]], list]:
    """Synchroner Kern von :func:`markdown_zu_bloecken` (ohne Diagramm-Prärender)."""
    gemeinsam = {k: v for k, v in teile.items() if v.strip() and not _DOPPELPUNKT_ZEILE.search(v)}
    einzeln = {k: v for k, v in teile.items() if v.strip() and k not in gemeinsam}

    ergebnis: dict[str, list[Block]] = {k: [] for k in teile}
    api_version = None
    if gemeinsam:
        schluessel = list(gemeinsam)
        quelle = "\n\n".join(
            f"{_ZAUN} {{#t{i}}}\n{gemeinsam[k]}\n{_ZAUN}" for i, k in enumerate(schluessel)
        )
        doc = pandoc.markdown_zu_json_sync(quelle)
        api_version = doc["pandoc-api-version"]
        for block in doc["blocks"]:
            if block.get("t") == "Div":
                kennung = block["c"][0][0]
                if kennung.startswith("t") and kennung[1:].isdigit():
                    ergebnis[schluessel[int(kennung[1:])]] = block["c"][1]
    for k, v in einzeln.items():
        doc = pandoc.markdown_zu_json_sync(v)
        api_version = doc["pandoc-api-version"]
        ergebnis[k] = doc["blocks"]
    if api_version is None:
        api_version = pandoc.markdown_zu_json_sync("")["pandoc-api-version"]
    return ergebnis, api_version


async def markdown_zu_bloecken(
    db: AsyncSession, teile: dict[str, str]
) -> tuple[dict[str, list[Block]], list]:
    """Liest die Markdown-Teile zu Pandoc-Blöcken. Gibt (Blöcke je Schlüssel, API-Fassung) zurück.

    Diagramme (circuitikz, plot, smiles, mermaid) werden vorher zu Bildern; leere Teile ergeben
    eine leere Liste. Ein Teil mit einer Zeile aus drei oder mehr Doppelpunkten wird einzeln
    gelesen — im gemeinsamen Aufruf schlösse sie seinen Abschnitt zu früh.
    """
    vorbereitet = {k: await prerender_diagrams(db, v or "") for k, v in teile.items()}
    return await asyncio.to_thread(_bloecke_sync, vorbereitet)


# ── Bausteine ─────────────────────────────────────────────────────────────────

def text(s: str) -> list[Inline]:
    """Klartext → Inlines (Wörter, Leerzeichen, Zeilenumbrüche). Kein Markdown."""
    out: list[Inline] = []
    for i, zeile in enumerate(s.split("\n")):
        if i:
            out.append({"t": "LineBreak"})
        for j, wort in enumerate(zeile.split(" ")):
            if j:
                out.append({"t": "Space"})
            if wort:
                out.append({"t": "Str", "c": wort})
    return out


def fett(inlines: list[Inline]) -> Inline:
    return {"t": "Strong", "c": inlines}


def absatz(inlines: list[Inline]) -> Block:
    return {"t": "Para", "c": inlines}


def schlicht(inlines: list[Inline]) -> Block:
    """Absatz ohne Abstand — für Tabellenzellen."""
    return {"t": "Plain", "c": inlines}


def ueberschrift(ebene: int, inlines: list[Inline]) -> Block:
    return {"t": "Header", "c": [ebene, _KEIN_ATTR, inlines]}


def aufzaehlung(punkte: Iterable[list[Block]]) -> Block:
    return {"t": "BulletList", "c": [list(p) for p in punkte]}


def durchstreichen(bloecke: list[Block]) -> list[Block]:
    """Streicht den Text in Absätzen und Listen durch (gestrichene Phasen)."""
    out: list[Block] = []
    for b in bloecke:
        t = b.get("t")
        if t in ("Para", "Plain"):
            out.append({"t": t, "c": [{"t": "Strikeout", "c": b["c"]}]})
        elif t in ("BulletList", "OrderedList"):
            punkte = b["c"] if t == "BulletList" else b["c"][1]
            neu = [durchstreichen(p) for p in punkte]
            out.append({"t": t, "c": neu if t == "BulletList" else [b["c"][0], neu]})
        else:
            out.append(b)
    return out


def _zelle(bloecke: list[Block]) -> list:
    return [_KEIN_ATTR, {"t": "AlignDefault"}, 1, 1, bloecke]


def _zeile(zellen: list[list[Block]]) -> list:
    return [_KEIN_ATTR, [_zelle(z) for z in zellen]]


def tabelle(
    kopf: list[str], zeilen: list[list[list[Block]]], breiten: Optional[list[float]] = None
) -> Block:
    """Tabelle mit fettem Kopf; Zellen sind Blocklisten. `breiten` sind Anteile (Summe ≈ 1)."""
    spalten = len(kopf)
    if breiten is None:
        breiten = [1 / spalten] * spalten
    spec = [[{"t": "AlignDefault"}, {"t": "ColWidth", "c": b}] for b in breiten]
    kopfzeile = _zeile([[schlicht([fett(text(k))])] for k in kopf])
    return {"t": "Table", "c": [
        _KEIN_ATTR,
        [None, []],                      # keine Bildunterschrift
        spec,
        [_KEIN_ATTR, [kopfzeile]],
        [[_KEIN_ATTR, 0, [], [_zeile(z) for z in zeilen]]],
        [_KEIN_ATTR, []],
    ]}


# ── Schreiben ─────────────────────────────────────────────────────────────────

async def dokument_zu_office(
    bloecke: list[Block],
    *,
    api_version: list,
    fmt: str,
    reference_doc: Optional[str] = None,
    quer: bool = False,
) -> bytes:
    """Schreibt die Blöcke als DOCX/ODT, mit `quer` im Querformat. Tabellen bekommen Linien.

    Kein `title` in den Metadaten: Pandoc setzte ihn als eigene Titelzeile vor das Dokument,
    zusätzlich zur Überschrift, die der Export selbst baut.
    """
    dokument = {"pandoc-api-version": api_version, "meta": {}, "blocks": bloecke}
    return await asyncio.to_thread(
        pandoc.json_zu_office_sync, dokument, fmt=fmt, reference_doc=reference_doc, quer=quer,
    )
