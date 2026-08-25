"""Parser für die neue Seitengeneration von bildungsplaene-bw.de („GEN2X", ab V3).

Der Unterschied zur alten Generation ist **nicht** das Markup, sondern der Zuschnitt:
Wo bisher eine Übersichtsseite auf Dutzende Unterseiten verwies, steht jetzt der ganze
Fachplan in **einem** Dokument, gegliedert über Sprungmarken.

    <h3 id="2">   2 Prozessbezogene Kompetenzen
      <h4 id="2.1">   2.1 Mathematisch argumentieren und beweisen   → pk_gruppe
        <tr id="2.1(1)">                                            → pk_kompetenz
    <h3 id="3">   3 Inhaltsbezogene Kompetenzen
      <h4 id="3.1">   3.1 Klassen 5/6                               → Jahrgangsband
        <h5 id="3.1.1">   3.1.1 Leitidee Zahl – Variable – Operation → leitidee
          <tr id="3.1.1(1)">                                        → ik_kompetenz

Die Kompetenzen stehen weiterhin in Tabellen, und die **Nummer steht als `id` an der
Zeile** — sie muss nicht mehr aus Fließtext geklaubt werden. Das war die größte
Fehlerquelle des alten Parsers.

Ausgabe ist bewusst **dasselbe JSONL-Schema** wie bisher, inklusive der bp_id-Bildung
`BP2016BW_ALLG_GYM_M.V3_IK_5-6_01_00_01` (Entscheidung E1 im Plan). Import,
Editions-Fahrplan, Archivierung und Anzeige merken davon nichts.

**Was sich inhaltlich ändert und niemanden überraschen sollte:** Die prozessbezogenen
Kompetenzen sind neu nummeriert — `2.1(1)` statt `2.1.1` in V2. Die inhaltsbezogenen
behalten ihre Form (`3.1.1(1)`).
"""

import re
from typing import Any

try:
    from bs4 import BeautifulSoup
except ImportError:  # vgl. parsers.py — der PDF-Import läuft ohne bs4
    BeautifulSoup = None  # type: ignore

from scripts.scraper.parsers import (
    ScraperParseError,
    _content_hash,
    _now_iso,
    extract_bp_version,
)
from scripts.scraper.references import strip_soft_hyphens

# Überschriften-ids: "2.1" (Abschnitt.Unterabschnitt) und "3.1.1" (Leitidee)
_ID_UNTERABSCHNITT = re.compile(r'^(\d+)\.(\d+)$')
_ID_LEITIDEE = re.compile(r'^(\d+)\.(\d+)\.(\d+)$')
# Zeilen-ids der Kompetenzen: "2.1(1)" / "3.1.1(12)"
_ID_KOMPETENZ = re.compile(r'^(\d+(?:\.\d+)+)\((\d+)\)$')

# „Klassen 5/6", „Klasse 11", „Klassen 12/13 (Leistungsfach)"
_BAND = re.compile(r'Klassen?\s+(\d+(?:\s*/\s*\d+)*)')
_NIVEAU_IM_BAND = {"Leistungsfach": "leistung", "Basisfach": "basis"}
_NIVEAU_KUERZEL = {"leistung": "LF", "basis": "BF"}


def band_aus_ueberschrift(text: str) -> tuple[str, int, int, str]:
    """Zerlegt eine Bandüberschrift in (Bezeichner-Segment, min_grade, max_grade, niveau).

    ``"3.1 Klassen 5/6"``                   → ``("5-6", 5, 6, "regulär")``
    ``"3.4 Klasse 11"``                     → ``("11", 11, 11, "regulär")``
    ``"3.5 Klassen 12/13 (Leistungsfach)"`` → ``("12-13-LF", 12, 13, "leistung")``

    Die Bänder haben sich mit V3 geändert: V2 kannte 5-6, 7-8, 9-10 und 11-12 (BF/LF),
    V3 führt **Klasse 11 allein** und **12/13** — es ist ein G9-Plan. Einzelstufen-Bänder
    ergeben ``min_grade == max_grade``; ohne diesen Fall stünde Klasse 11 ohne Stufe da.

    Das erzeugte Segment ist so gebaut, dass die vorhandenen Helfer
    ``extract_grades_from_bp_id`` und ``extract_niveau_from_bp_id`` es unverändert lesen.
    """
    sauber = strip_soft_hyphens(text)
    m = _BAND.search(sauber)
    if not m:
        raise ValueError(f"Keine Klassenstufen in Bandüberschrift: {sauber!r}")

    stufen = [int(s) for s in re.split(r'\s*/\s*', m.group(1))]
    niveau = "regulär"
    for wort, wert in _NIVEAU_IM_BAND.items():
        if wort in sauber:
            niveau = wert
            break

    segment = "-".join(str(s) for s in stufen)
    if niveau != "regulär":
        segment += "-" + _NIVEAU_KUERZEL[niveau]
    return segment, min(stufen), max(stufen), niveau


def _text(el) -> str:
    """Sichtbarer Text eines Elements, ohne weiche Trennstriche.

    GEN2X setzt U+00AD im gesamten Fließtext (``Leit\xadge\xaddan\xadken``). Bliebe er
    stehen, gingen Titel, Suche und Content-Hash daneben — und zwar unsichtbar.
    """
    return strip_soft_hyphens(el.get_text(" ", strip=True)) if el else ""


def _knoten(
    *, bp_id: str, content_type: str, title: str, content: str,
    parent_bp_id: str | None, url: str, breadcrumb: list[str],
    min_grade: int | None = None, max_grade: int | None = None,
    niveau: str = "regulär", extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Baut einen JSONL-Knoten im Schema der alten Generation."""
    return {
        "bp_id": bp_id,
        "type": "knowledge",
        "content_type": content_type,
        "title": title,
        "content": content,
        "content_hash": _content_hash(content),
        "parent_bp_id": parent_bp_id,
        "relations": [],
        "min_grade": min_grade,
        "max_grade": max_grade,
        "niveau": niveau,
        "bp_version": extract_bp_version(bp_id),
        "metadata": {
            "bp_id": bp_id,
            "breadcrumb": breadcrumb,
            "source_url": url,
            "scraped_at": _now_iso(),
            **(extra_metadata or {}),
        },
        "visibility": "global",
    }


def _kompetenzzeilen(ueberschrift) -> list[tuple[str, int, str, str]]:
    """Kompetenzen unter einer Überschrift: (kompetenz_nr, standard_nr, text, gruppe).

    Gelesen wird die auf die Überschrift folgende Tabelle. ``gruppe`` ist die fett
    gesetzte Zwischenzeile darüber („Zahlbereiche erkunden") — in V2 nur bei den
    prozessbezogenen Kompetenzen erfasst, hier für beide, weil die Quelle sie führt.
    """
    tabelle = None
    for sib in ueberschrift.find_next_siblings():
        if sib.name in ("h3", "h4", "h5"):
            break
        gefunden = sib.find("table") if sib.name == "section" else None
        if gefunden is not None:
            tabelle = gefunden
            break
    if tabelle is None:
        return []

    zeilen: list[tuple[str, int, str, str]] = []
    gruppe = ""
    for tr in tabelle.find_all("tr"):
        klassen = " ".join(tr.get("class") or [])
        if "subhead" in klassen:
            gruppe = _text(tr)
            continue
        m = _ID_KOMPETENZ.match(tr.get("id") or "")
        if not m:
            continue
        koerper = tr.select_one(".text-body")
        zeilen.append((tr["id"], int(m.group(2)), _text(koerper) if koerper else _text(tr), gruppe))
    return zeilen


def _intro(ueberschrift) -> str:
    """Einleitungstext direkt unter einer Überschrift (vor der Kompetenztabelle)."""
    for sib in ueberschrift.find_next_siblings():
        if sib.name in ("h3", "h4", "h5"):
            return ""
        if sib.name == "div":
            return _text(sib)
        if sib.name == "section":
            return ""
    return ""


def parse_gen2x_dokument(
    soup: "BeautifulSoup",
    url: str,
    bp_id_fach: str,
) -> list[dict[str, Any]]:
    """Zerlegt eine GEN2X-Fachplanseite in JSONL-Knoten.

    ``bp_id_fach`` ist die Kennung im **alten** Schema, z. B.
    ``BP2016BW_ALLG_GYM_M.V3`` (Entscheidung E1). Der GEN2X-Bezeichner der Quelle
    landet in den Metadaten des Fachplan-Knotens, bleibt also nachvollziehbar.
    """
    h1 = soup.find("h1")
    if h1 is None:
        raise ScraperParseError(url, "Keine <h1> — kein GEN2X-Fachplan")
    fach_titel = _text(h1)
    breadcrumb_basis = [_text(b) for b in soup.select(".breadcrumb__item")]

    knoten: list[dict[str, Any]] = [
        _knoten(
            bp_id=bp_id_fach,
            content_type="fachplan",
            title=fach_titel,
            content=fach_titel,
            parent_bp_id=None,
            url=url,
            breadcrumb=breadcrumb_basis,
            extra_metadata={"gen2x_id": url.rstrip("/").split("/")[-1]},
        )
    ]

    ueberschriften = soup.find_all(["h3", "h4", "h5"])

    # ── Abschnitt 2: prozessbezogene Kompetenzen ─────────────────────────────
    for h in ueberschriften:
        m = _ID_UNTERABSCHNITT.match(h.get("id") or "")
        if not m or m.group(1) != "2":
            continue
        gruppen_nr = int(m.group(2))
        gruppen_bp_id = f"{bp_id_fach}_PK_{gruppen_nr:02d}"
        gruppen_titel = _text(h)
        bc = breadcrumb_basis + [gruppen_titel]
        knoten.append(
            _knoten(
                bp_id=gruppen_bp_id, content_type="pk_gruppe",
                title=gruppen_titel, content=_intro(h) or gruppen_titel,
                parent_bp_id=bp_id_fach, url=url, breadcrumb=bc,
            )
        )
        for kompetenz_nr, standard_nr, text, gruppe in _kompetenzzeilen(h):
            knoten.append(
                _knoten(
                    bp_id=f"{gruppen_bp_id}_{standard_nr:02d}",
                    content_type="pk_kompetenz",
                    title=f"{kompetenz_nr} {text}",
                    content=f"({standard_nr}) {text}",
                    parent_bp_id=gruppen_bp_id, url=url, breadcrumb=bc,
                    extra_metadata={
                        "kompetenz_nr": kompetenz_nr,
                        "standard_nr": standard_nr,
                        "thematische_gruppe": gruppe,
                    },
                )
            )

    # ── Abschnitt 3: inhaltsbezogene Kompetenzen, gegliedert nach Bändern ────
    band: tuple[str, int, int, str] | None = None
    band_titel = ""
    for h in ueberschriften:
        hid = h.get("id") or ""

        m_band = _ID_UNTERABSCHNITT.match(hid)
        if m_band and m_band.group(1) == "3":
            band_titel = _text(h)
            band = band_aus_ueberschrift(band_titel)
            continue

        m_li = _ID_LEITIDEE.match(hid)
        if not m_li or m_li.group(1) != "3":
            continue
        if band is None:
            raise ScraperParseError(url, f"Leitidee {hid} ohne vorangehendes Jahrgangsband")

        segment, min_grade, max_grade, niveau = band
        li_nr = int(m_li.group(3))
        li_bp_id = f"{bp_id_fach}_IK_{segment}_{li_nr:02d}"
        li_titel = _text(h)
        bc = breadcrumb_basis + [band_titel, li_titel]
        knoten.append(
            _knoten(
                bp_id=li_bp_id, content_type="leitidee",
                title=li_titel, content=_intro(h) or li_titel,
                parent_bp_id=bp_id_fach, url=url, breadcrumb=bc,
                min_grade=min_grade, max_grade=max_grade, niveau=niveau,
            )
        )
        for kompetenz_nr, standard_nr, text, gruppe in _kompetenzzeilen(h):
            knoten.append(
                _knoten(
                    # Das feste `00` ist das Gruppen-Segment der alten Generation. Es
                    # trug dort nie einen anderen Wert (326 von 326 Knoten) und bleibt
                    # als Platzhalter erhalten, damit die bp_ids vergleichbar bleiben.
                    bp_id=f"{li_bp_id}_00_{standard_nr:02d}",
                    content_type="ik_kompetenz",
                    title=f"{kompetenz_nr} {text}",
                    content=f"({standard_nr}) {text}",
                    parent_bp_id=li_bp_id, url=url, breadcrumb=bc,
                    min_grade=min_grade, max_grade=max_grade, niveau=niveau,
                    extra_metadata={
                        "kompetenz_nr": kompetenz_nr,
                        "standard_nr": standard_nr,
                        "thematische_gruppe": gruppe,
                    },
                )
            )

    return knoten
