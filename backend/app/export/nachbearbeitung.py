"""Nachbearbeitung fertiger DOCX/ODT-Dateien: Tabellenlinien und Querformat (0.39).

Pandoc schreibt Tabellen **ohne Linien** — im ODT ausdrücklich (`fo:border="none"` an den
Zellstilen), im DOCX über die Formatvorlage „Table“, die keine Rahmen hat. In der
Textverarbeitung sah eine Tabelle deshalb aus wie Text mit Tabulatoren (Jan, 11.11.2026).
Seit 0.39 bekommt jede Tabelle dünne Linien, und zwar direkt an der Tabelle bzw. den Zellen —
sie gelten auch mit einer Schulvorlage, deren Schriften und Formatvorlagen bleiben.

Das Curriculum ist breit (vier Spalten Volltext) und kommt im Querformat. Gedreht wird die
Seite der fertigen Datei, nicht die Vorlage: So bleiben die Ränder der Schulvorlage erhalten.
"""
from __future__ import annotations

import io
import re
import zipfile
from typing import Callable

# ── ZIP ───────────────────────────────────────────────────────────────────────


def zip_mit_ersetzung(roh: bytes, ersetzungen: dict[str, Callable[[str], str]]) -> bytes:
    """Schreibt das ZIP neu und wendet je Eintrag eine Ersetzung auf den XML-Text an.

    Reihenfolge und Kompression je Eintrag bleiben — im ODT muss `mimetype` zuerst und
    unkomprimiert stehen, sonst erkennt LibreOffice die Datei nicht.
    """
    quelle = zipfile.ZipFile(io.BytesIO(roh))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as ziel:
        for info in quelle.infolist():
            daten = quelle.read(info.filename)
            if info.filename in ersetzungen:
                daten = ersetzungen[info.filename](daten.decode("utf-8")).encode("utf-8")
            ziel.writestr(info, daten, compress_type=info.compress_type)
    return out.getvalue()


# ── Tabellenlinien ────────────────────────────────────────────────────────────

_LINIE = 'w:val="single" w:sz="4" w:space="0" w:color="000000"'
_DOCX_RAHMEN = "<w:tblBorders>" + "".join(
    f"<w:{seite} {_LINIE} />" for seite in ("top", "left", "bottom", "right", "insideH", "insideV")
) + "</w:tblBorders>"
# Was im Schema von `w:tblPr` **hinter** `w:tblBorders` steht — davor wird eingefügt.
_DOCX_DAHINTER = ("<w:shd", "<w:tblLayout", "<w:tblCellMar", "<w:tblLook", "<w:tblCaption",
                  "<w:tblDescription", "</w:tblPr>")
_TBLPR_RE = re.compile(r"<w:tblPr>.*?</w:tblPr>", re.S)


def _docx_linien(xml: str) -> str:
    def einsetzen(m: re.Match) -> str:
        pr = m.group(0)
        if "<w:tblBorders" in pr:
            return pr
        stelle = min(i for i in (pr.find(t) for t in _DOCX_DAHINTER) if i >= 0)
        return pr[:stelle] + _DOCX_RAHMEN + pr[stelle:]

    return _TBLPR_RE.sub(einsetzen, xml)


_ODT_ZELLSTIL_RE = re.compile(
    r'(<style:style\b[^>]*style:family="table-cell"[^>]*>\s*<style:table-cell-properties\b)([^>]*?)(/?>)'
)
_ODT_RAHMEN = ' fo:border="0.5pt solid #000000" fo:padding="0.1cm"'


def _odt_linien(xml: str) -> str:
    def einsetzen(m: re.Match) -> str:
        attribute = re.sub(r'\s*fo:(border|padding)(-[a-z]+)?="[^"]*"', "", m.group(2))
        return m.group(1) + attribute + _ODT_RAHMEN + m.group(3)

    return _ODT_ZELLSTIL_RE.sub(einsetzen, xml)


# ── Querformat ────────────────────────────────────────────────────────────────

_PGSZ_RE = re.compile(r"<w:pgSz\b([^>]*?)/>")
_A4_DOCX = '<w:pgSz w:w="11906" w:h="16838" />'
_A4_QUER_DOCX = '<w:pgSz w:w="16838" w:h="11906" w:orient="landscape" />'


def _docx_seitenformat(xml: str, pgsz: str = _A4_DOCX) -> str:
    """Setzt `pgsz` vor die Ränder bzw. ans Ende von sectPr, wenn kein Seitenformat da ist.

    ⚠️ Pandoc 3.11 (Prod, CI) übernimmt das `pgSz` der eingebauten A4-Vorlage nicht ins
    Dokument, 3.13 schon — ohne `pgSz` nimmt Word seine Voreinstellung (US: Letter). Deshalb
    sichert die Nachbearbeitung A4 unabhängig von der Pandoc-Fassung. Eine Schulvorlage mit
    eigenem Seitenformat bleibt unberührt.
    """
    if _PGSZ_RE.search(xml):
        return xml
    for marke in ("<w:pgMar", "</w:sectPr>"):
        if marke in xml:
            return xml.replace(marke, pgsz + marke)
    return xml


def _attr(attrs: str, name: str) -> str | None:
    m = re.search(rf'{name}="([^"]*)"', attrs)
    return m.group(1) if m else None


def _docx_quer(xml: str) -> str:
    def drehen(m: re.Match) -> str:
        breite, hoehe = _attr(m.group(1), "w:w"), _attr(m.group(1), "w:h")
        if not (breite and hoehe):
            return _A4_QUER_DOCX
        b, h = sorted((int(breite), int(hoehe)), reverse=True)
        return f'<w:pgSz w:w="{b}" w:h="{h}" w:orient="landscape" />'

    if _PGSZ_RE.search(xml):
        return _PGSZ_RE.sub(drehen, xml)
    return _docx_seitenformat(xml, _A4_QUER_DOCX)


_EINHEIT_CM = {"cm": 1.0, "mm": 0.1, "in": 2.54, "pt": 2.54 / 72}
_SEITE_RE = re.compile(r"<style:page-layout-properties\b[^>]*>")


def _laenge_cm(wert: str | None) -> float | None:
    m = re.fullmatch(r"([\d.]+)(cm|mm|in|pt)", wert or "")
    return float(m.group(1)) * _EINHEIT_CM[m.group(2)] if m else None


def _odt_quer(xml: str) -> str:
    def drehen(m: re.Match) -> str:
        tag = m.group(0)
        breite, hoehe = _attr(tag, "fo:page-width"), _attr(tag, "fo:page-height")
        b, h = _laenge_cm(breite), _laenge_cm(hoehe)
        if b is not None and h is not None and b < h:
            tag = (tag.replace(f'fo:page-width="{breite}"', "\0B")
                      .replace(f'fo:page-height="{hoehe}"', f'fo:page-height="{breite}"')
                      .replace("\0B", f'fo:page-width="{hoehe}"'))
        if "style:print-orientation=" in tag:
            return re.sub(r'style:print-orientation="[^"]*"', 'style:print-orientation="landscape"', tag)
        return tag.replace("<style:page-layout-properties", '<style:page-layout-properties style:print-orientation="landscape"', 1)

    return _SEITE_RE.sub(drehen, xml)


# ── Einstieg ──────────────────────────────────────────────────────────────────


def nachbearbeiten(data: bytes, fmt: str, *, quer: bool = False) -> bytes:
    """Linien an alle Tabellen; DOCX ohne Seitenformat wird A4; mit `quer` Querformat."""
    if fmt == "docx":
        schritte = [_docx_linien, _docx_quer if quer else _docx_seitenformat]
        return zip_mit_ersetzung(data, {"word/document.xml": _nacheinander(schritte)})
    if fmt == "odt":
        ersetzungen = {"content.xml": _odt_linien}
        if quer:
            ersetzungen["styles.xml"] = _odt_quer
        return zip_mit_ersetzung(data, ersetzungen)
    return data


def _nacheinander(schritte):
    def anwenden(xml: str) -> str:
        for s in schritte:
            xml = s(xml)
        return xml
    return anwenden
