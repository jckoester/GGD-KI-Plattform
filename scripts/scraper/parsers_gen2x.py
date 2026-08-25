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
    operator_knoten_aus_tabelle,
)
from scripts.scraper.references import strip_soft_hyphens

# Überschriften-ids: "2.1" (Abschnitt.Unterabschnitt) und "3.1.1" (Leitidee)
_ID_UNTERABSCHNITT = re.compile(r'^(\d+)\.(\d+)$')
_ID_LEITIDEE = re.compile(r'^(\d+)\.(\d+)\.(\d+)$')
# Physik gliedert eine Ebene tiefer: `3.3.1.1 Kinematik` unter `3.3.1 Mechanik`.
_ID_UNTEREBENE = re.compile(r'^(\d+)\.(\d+)\.(\d+)\.(\d+)$')
# Zeilen-ids der Kompetenzen: "2.1(1)" / "3.1.1(12)"
_ID_KOMPETENZ = re.compile(r'^(\d+(?:\.\d+)+)\((\d+)\)$')

# „Klassen 5/6", „Klasse 11", „Klassen 12/13 (Leistungsfach)"
_BAND = re.compile(r'Klassen?\s+(\d+(?:\s*/\s*\d+)*)')
_NIVEAU_IM_BAND = {"Leistungsfach": "leistung", "Basisfach": "basis"}
_NIVEAU_KUERZEL = {"leistung": "LF", "basis": "BF"}
# „Basisfach mit Schwerpunkt Astrophysik" → ASTROPHYSIK. Nur nötig, wo ein Fach
# mehrere Bänder derselben Stufen und desselben Niveaus führt (Physik).
_SCHWERPUNKT = re.compile(r'Schwerpunkt\s+([A-Za-zÄÖÜäöüß]+)')


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

    **Ein Band ist durch Stufen und Niveau nicht immer eindeutig.** Physik führt in
    12/13 *zwei* Basisfächer — „Basisfach mit Schwerpunkt Quantenphysik" und
    „… Astrophysik". Beide ergäben `12-13-BF`, und die Leitideen `3.4.1` und `3.5.1`
    bekämen denselben Bezeichner. Steht ein Schwerpunkt in der Überschrift, wandert er
    deshalb ins Segment: ``12-13-BF-ASTROPHYSIK``. Die übrigen Bänder bleiben, wie sie
    waren — Mathematik merkt davon nichts.
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
    schwerpunkt = _SCHWERPUNKT.search(sauber)
    if schwerpunkt:
        segment += "-" + schwerpunkt.group(1).upper()
    return segment, min(stufen), max(stufen), niveau


# Verweise stehen in einer **eigenen** Zeile hinter der Kompetenz
# (`tr.bp_allg_content_item_table_level_bpx`), aufgeteilt in Kästen je Verweisart.
_VERWEISZEILE = "level_bpx"
_REL_JE_BOX = {
    "box--p": "develops",    # prozessbezogene Kompetenz desselben Plans
    "box--i": "related_to",  # inhaltsbezogene Kompetenz desselben Plans
    "box--l": "references",  # Leitperspektive
    "box--f": "related_to",  # Kompetenz eines anderen Fachs
}
# Anker einer Leitperspektive: `BNE(2)` → Token `BNE_02` (Form der alten Generation)
_LP_ANKER = re.compile(r'^([A-Z]+)\((\d+)\)$')
# Adresse eines anderen Fachs. GEN2X-Seiten verweisen auf **beide** Generationen:
#   …_ALLG_GYM_PH(V3.0)   neue Generation, Fassung in Klammern
#   …_ALLG_GYM_GK.V2      alte Generation, Edition als Suffix
#   …_ALLG_GYM_LUT        alte Generation, Basisfassung
# Die Fassungsangabe landet einheitlich in `quell_version`; der Import bildet beide
# Formen auf `bp_version` ab.
_FREMDFACH = re.compile(r'_ALLG_[A-Z]+_([A-Z0-9]+)(?:\(([^)]+)\)|(\.V\d+))?$')
# Voreinstellung für `_knoten(bp_version=…)`: aus dem Bezeichner ableiten.
_AUS_BEZEICHNER = object()

# Kürzel einer Leitperspektive in der Überschrift: „… (LDW)"
_LP_KUERZEL_IN_TITEL = re.compile(r'\(([A-ZÄÖÜ]{2,5})\)\s*$')
# id eines Leitperspektiven-Aspekts: `BNE(1)`
_ID_LP_ASPEKT = re.compile(r'^([A-Z]+)\((\d+)\)$')


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
    niveau: str = "regulär", relations: list[dict[str, str]] | None = None,
    bp_version: Any = _AUS_BEZEICHNER,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Baut einen JSONL-Knoten im Schema der alten Generation.

    ``bp_version`` wird normalerweise aus dem Bezeichner abgeleitet. Leitperspektiven
    setzen sie auf ``""`` — sie gehören zu keiner Fachplan-Edition. **Nicht ``None``:**
    Die Spalte `context_nodes.bp_version` ist NOT NULL. Der klassische Parser drückt
    dasselbe aus, indem er den Schlüssel ganz weglässt und der Import seinen Standardwert
    `""` einsetzt; hier steht er ausdrücklich da.
    """
    return {
        "bp_id": bp_id,
        "type": "knowledge",
        "content_type": content_type,
        "title": title,
        "content": content,
        "content_hash": _content_hash(content),
        "parent_bp_id": parent_bp_id,
        "relations": relations or [],
        "min_grade": min_grade,
        "max_grade": max_grade,
        "niveau": niveau,
        "bp_version": (
            extract_bp_version(bp_id) if bp_version is _AUS_BEZEICHNER else bp_version
        ),
        "metadata": {
            "bp_id": bp_id,
            "breadcrumb": breadcrumb,
            "source_url": url,
            "scraped_at": _now_iso(),
            **(extra_metadata or {}),
        },
        "visibility": "global",
    }


def _kompetenzzeilen(ueberschrift) -> list[tuple[str, int, str, str, Any]]:
    """Kompetenzen unter einer Überschrift: (kompetenz_nr, standard_nr, text, gruppe, zeile).

    Gelesen wird die auf die Überschrift folgende Tabelle. ``gruppe`` ist die fett
    gesetzte Zwischenzeile darüber („Zahlbereiche erkunden") — in V2 nur bei den
    prozessbezogenen Kompetenzen erfasst, hier für beide, weil die Quelle sie führt.
    """
    tabelle = None
    for sib in ueberschrift.find_next_siblings():
        # h6 mit abbrechen: Sonst griffe eine Leitidee mit Unterebenen die Tabelle der
        # ersten Unterebene ab — die Kompetenzen hingen dann eine Ebene zu hoch, mit
        # vierstelliger Nummer an einem dreistelligen Knoten.
        if sib.name in ("h3", "h4", "h5", "h6"):
            break
        gefunden = sib.find("table") if sib.name == "section" else None
        if gefunden is not None:
            tabelle = gefunden
            break
    if tabelle is None:
        return []

    zeilen: list[tuple[str, int, str, str, Any]] = []
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
        zeilen.append(
            (tr["id"], int(m.group(2)), _text(koerper) if koerper else _text(tr), gruppe, tr)
        )
    return zeilen


def _verweise(
    zeile, bp_id_fach: str, band_segmente: dict[str, str]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Verweise einer Kompetenzzeile: (auflösbare ``relations``, offene Verweise).

    **Auflösbar** ist, was im selben Dokument liegt — prozess- und inhaltsbezogene
    Kompetenzen desselben Plans. Deren Bezeichner lässt sich vollständig bilden.

    **Offen** bleibt, was den Bestand einer anderen Quelle braucht:

    * *Cross-Fach* (`PH(V3.0) 3.2.7 (2)`) — der Bezeichner des Ziels hängt an der
      Bandgliederung des **anderen** Fachs, die in diesem Dokument nicht steht. Physik
      und Geografie gliedern zudem tiefer (``3.3.1.1``) als Mathematik. Aufgelöst wird
      das beim Import über (Fach, Fassung, Nummer) — Schritt 7.

    Offene Verweise landen in den Metadaten statt im Nirwana: Die Angabe ist damit
    erfasst und muss später nicht neu geholt werden.
    """
    relations: list[dict[str, str]] = []
    offen: list[dict[str, str]] = []

    for verweiszeile in _verweiszeilen(zeile):
        for box in verweiszeile.select("div.box"):
            klassen = box.get("class") or []
            relation = next(
                (_REL_JE_BOX[k] for k in klassen if k in _REL_JE_BOX), None
            )
            if relation is None:
                continue
            for a in box.find_all("a", href=True):
                href = a["href"]
                ziel = _verweis_ziel(href, bp_id_fach, band_segmente)
                if ziel is not None:
                    relations.append({"target_bp_id": ziel, "type": relation})
                    continue

                fremd = _FREMDFACH.search(href.split("#")[0])
                nr_ziel = href.split("#", 1)[1] if "#" in href else ""
                if fremd and nr_ziel:
                    offen.append({
                        "art": "cross_fach",
                        "fach_code": fremd.group(1),
                        # Klammer-Fassung (GEN2X), Suffix (alte Generation) oder "" (Basis)
                        "quell_version": fremd.group(2) or fremd.group(3) or "",
                        "nr": nr_ziel,
                        "type": relation,
                    })
                elif fremd:
                    # Verweis auf die **ganze** Fachseite, ohne Sprungmarke. Das ist kein
                    # Kompetenzbezug, sondern ein „siehe auch dieses Fach". Ihn als
                    # unaufgeloesten Kompetenzverweis zu fuehren, erzeugte 500 Warnungen
                    # ueber etwas, das gar kein Ziel hat.
                    continue
                else:
                    # Alles, was hier landet, ist ein Anker, den dieses Dokument selbst
                    # nicht auflösen konnte — im vollständigen Fachplan darf das nicht
                    # vorkommen. Trotzdem erfassen statt verschlucken: Ein stillschweigend
                    # verlorener Verweis wäre nirgends zu sehen.
                    offen.append({"art": "dokumentintern", "nr": href, "type": relation})
    return relations, offen


def _verweiszeilen(zeile):
    """Die Verweiszeile(n) direkt hinter einer Kompetenzzeile."""
    for sib in zeile.find_next_siblings("tr"):
        if _VERWEISZEILE not in " ".join(sib.get("class") or []):
            return
        yield sib


def _verweis_ziel(href: str, bp_id_fach: str, band_segmente: dict[str, str]) -> str | None:
    """bp_id des Verweisziels — oder ``None``, wenn es hier nicht bestimmbar ist."""
    if href.startswith("#"):
        return _anker_zu_bp_id(href[1:], bp_id_fach, band_segmente)

    anker = href.split("#", 1)[1] if "#" in href else ""
    lp = _LP_ANKER.match(anker)
    if lp and "_ALLG_LP(" in href:
        # Leitperspektiven tragen die Tokenform der alten Generation: `BNE(2)` → `BNE_02`.
        # Fünf der sechs Leitperspektiven sind unverändert; die sechste (LDW) ersetzt die
        # bisherige Medienbildung und ist noch nicht importiert — der Verweis wird
        # trotzdem erzeugt, damit die Lücke beim Import **auffällt** statt zu verschwinden.
        return f"{lp.group(1)}_{int(lp.group(2)):02d}"
    return None


def _anker_zu_bp_id(anker: str, bp_id_fach: str, band_segmente: dict[str, str]) -> str | None:
    """Dokumentinterner Anker → bp_id. ``2.1(1)`` → ``…_PK_01_01``."""
    m = _ID_KOMPETENZ.match(anker)
    pfad, standard = (m.group(1), int(m.group(2))) if m else (anker, None)
    teile = pfad.split(".")

    if teile[0] == "2" and len(teile) == 2:
        basis = f"{bp_id_fach}_PK_{int(teile[1]):02d}"
        return basis if standard is None else f"{basis}_{standard:02d}"

    if teile[0] == "3" and len(teile) in (3, 4):
        segment = band_segmente.get(teile[1])
        if segment is None:
            return None
        basis = f"{bp_id_fach}_IK_{segment}_{int(teile[2]):02d}"
        if len(teile) == 4:
            # Unterebene (Physik, Chemie, Geografie): `3.2.1.3` bzw. `3.2.1.3(4)`.
            # Ihr Index steht an der Stelle, die sonst der Platzhalter `00` fuellt.
            basis = f"{basis}_{int(teile[3]):02d}"
            return basis if standard is None else f"{basis}_{standard:02d}"
        return basis if standard is None else f"{basis}_00_{standard:02d}"

    return None


def _kompetenzen_anhaengen(
    knoten: list[dict[str, Any]], ueberschrift, eltern_bp_id: str,
    gruppen_segment: str, url: str, breadcrumb: list[str],
    min_grade: int | None, max_grade: int | None, niveau: str,
    bp_id_fach: str, band_segmente: dict[str, str],
) -> None:
    """Hängt die Kompetenzen unter einer Überschrift an die Knotenliste.

    ``gruppen_segment`` ist die Stelle, die in der alten Generation immer ``00`` war
    (326 von 326 Knoten). Bei Fächern mit einer Ebene mehr — Physik gliedert
    `3.3.1.1 Kinematik` unter `3.3.1 Mechanik` — trägt sie den Index der Unterebene.
    """
    for kompetenz_nr, standard_nr, text, gruppe, zeile in _kompetenzzeilen(ueberschrift):
        relations, offen = _verweise(zeile, bp_id_fach, band_segmente)
        knoten.append(
            _knoten(
                # Unter einer Leitidee steht der Platzhalter `00` dazwischen, unter
                # einer Unterebene nicht — deren Index steckt schon im Elternknoten.
                bp_id=f"{eltern_bp_id}_{gruppen_segment}_{standard_nr:02d}"
                if gruppen_segment == "00"
                else f"{eltern_bp_id}_{standard_nr:02d}",
                content_type="ik_kompetenz",
                title=f"{kompetenz_nr} {text}",
                content=f"({standard_nr}) {text}",
                parent_bp_id=eltern_bp_id, url=url, breadcrumb=breadcrumb,
                min_grade=min_grade, max_grade=max_grade, niveau=niveau,
                relations=relations,
                extra_metadata={
                    "kompetenz_nr": kompetenz_nr,
                    "standard_nr": standard_nr,
                    "thematische_gruppe": gruppe,
                    **({"offene_verweise": offen} if offen else {}),
                },
            )
        )


def parse_gen2x_leitperspektiven(
    soup: "BeautifulSoup", url: str, bp_id_basis: str = "BP2016BW_ALLG_LP"
) -> list[dict[str, Any]]:
    """Zerlegt die GEN2X-Leitperspektivenseite in Knoten.

    Auch hier gilt der Zuschnitt der neuen Generation: **eine** Seite für alle
    Leitperspektiven statt einer je Stück. Die Überschriften nennen das Kürzel in
    Klammern (`2.5 Leben und Lernen in einer digitalisierten Welt (LDW)`), die Aspekte
    tragen es als `id` (`LDW(1)`).

    Die Knoten folgen dem bestehenden Schema — `BP2016BW_ALLG_LP_BNE` für die
    Leitperspektive, `BNE_01` für den Aspekt. Das ist die Form, in der Fachpläne beider
    Generationen auf sie verweisen.

    **Bewusst ohne `bp_version`:** Leitperspektiven gehören zu keinem Fach und keiner
    Fachplan-Edition. Von den 37 Aspekten, die es in beiden Fassungen gibt, sind **alle
    37 textgleich** — es gibt also nichts zu unterscheiden. Der einzige echte Unterschied
    ist, dass die Medienbildung (MB) durch „Leben und Lernen in einer digitalisierten
    Welt" (LDW) abgelöst wurde; beide bleiben nebeneinander bestehen, solange Fächer auf
    beiden Fassungen unterrichtet werden.
    """
    breadcrumb_basis = [_text(b) for b in soup.select(".breadcrumb__item")]
    knoten: list[dict[str, Any]] = []

    for h in soup.find_all("h4"):
        m = _ID_UNTERABSCHNITT.match(h.get("id") or "")
        if not m or m.group(1) != "2":
            continue
        titel_roh = _text(h)
        kuerzel_m = _LP_KUERZEL_IN_TITEL.search(titel_roh)
        if not kuerzel_m:
            continue
        kuerzel = kuerzel_m.group(1)
        # „2.5 Leben und Lernen … (LDW)" → „Leben und Lernen …"
        titel = _LP_KUERZEL_IN_TITEL.sub("", titel_roh).strip()
        titel = re.sub(r"^\d+(\.\d+)*\s+", "", titel).strip()

        lp_bp_id = f"{bp_id_basis}_{kuerzel}"
        bc = breadcrumb_basis + [titel]
        knoten.append(
            _knoten(
                bp_id=lp_bp_id, content_type="leitperspektive",
                title=titel, content=_intro(h) or titel,
                parent_bp_id=None, url=url, breadcrumb=bc, bp_version="",
                extra_metadata={"kuerzel": kuerzel},
            )
        )
        for aspekt_nr, text in _lp_aspekte(h, kuerzel):
            knoten.append(
                _knoten(
                    bp_id=f"{kuerzel}_{aspekt_nr:02d}",
                    content_type="leitperspektive_aspekt",
                    title=text, content=text,
                    parent_bp_id=lp_bp_id, url=url, breadcrumb=bc, bp_version="",
                    extra_metadata={"kuerzel": kuerzel, "aspekt_nr": aspekt_nr},
                )
            )

    if not knoten:
        raise ScraperParseError(url, "Keine Leitperspektiven gefunden")
    return knoten


def _lp_aspekte(ueberschrift, kuerzel: str) -> list[tuple[int, str]]:
    """Aspekte einer Leitperspektive: (Nummer, Text), aus den Zeilen-ids `BNE(1)`."""
    aspekte: list[tuple[int, str]] = []
    for sib in ueberschrift.find_next_siblings():
        if sib.name in ("h3", "h4"):
            break
        for el in sib.find_all(attrs={"id": True}):
            m = _ID_LP_ASPEKT.match(el.get("id") or "")
            if not m or m.group(1) != kuerzel:
                continue
            # Der sichtbare Text beginnt mit der Nummer („(1) …") — sie steht schon
            # in `aspekt_nr` und würde den Titel nur doppeln.
            aspekte.append((int(m.group(2)), re.sub(r"^\(\d+\)\s*", "", _text(el))))
    return aspekte


def _operatoren(soup, url: str, bp_id_fach: str) -> list[dict[str, Any]]:
    """Operatoren aus Abschnitt 4 desselben Dokuments.

    Die alte Generation legte sie auf eine eigene Anhangseite (`…_OP`), die neue führt
    sie im Fachplan selbst. Gefunden wird die Tabelle über die Klasse ``op_table`` an
    ihren Zeilen — die setzt die Quelle ausdrücklich, und sie hält auch dann, wenn ein
    anderes Fach den Abschnitt anders nummeriert. Ein Fach ohne Operatoren liefert
    schlicht nichts.

    Die bp_ids bleiben `…_OP_01` wie gehabt, damit Chat-Werkzeug und Anzeige nichts
    davon merken.
    """
    zeile = soup.select_one("tr.op_table")
    if zeile is None:
        return []
    tabelle = zeile.find_parent("table")
    if tabelle is None:
        return []
    return operator_knoten_aus_tabelle(tabelle, url, bp_id_fach, f"{bp_id_fach}_OP")


def _intro(ueberschrift) -> str:
    """Einleitungstext direkt unter einer Überschrift (vor der Kompetenztabelle)."""
    for sib in ueberschrift.find_next_siblings():
        if sib.name in ("h3", "h4", "h5", "h6"):
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

    ueberschriften = soup.find_all(["h3", "h4", "h5", "h6"])

    # Bandgliederung zuerst: Ein Verweis `#3.1.4(1)` nennt nur den **Index** des Bandes
    # (hier 1), nicht dessen Stufen. Ohne diese Zuordnung ließe sich der Bezeichner des
    # Ziels nicht bilden — und Verweise stehen auch in Abschnitt 2, also vor der Stelle,
    # an der die Bänder sonst gelesen würden.
    band_segmente: dict[str, str] = {}
    for h in ueberschriften:
        m = _ID_UNTERABSCHNITT.match(h.get("id") or "")
        if m and m.group(1) == "3":
            band_segmente[m.group(2)] = band_aus_ueberschrift(_text(h))[0]

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
                extra_metadata={"nr": m.group(0)},
            )
        )
        for kompetenz_nr, standard_nr, text, gruppe, zeile in _kompetenzzeilen(h):
            relations, offen = _verweise(zeile, bp_id_fach, band_segmente)
            knoten.append(
                _knoten(
                    bp_id=f"{gruppen_bp_id}_{standard_nr:02d}",
                    content_type="pk_kompetenz",
                    title=f"{kompetenz_nr} {text}",
                    content=f"({standard_nr}) {text}",
                    parent_bp_id=gruppen_bp_id, url=url, breadcrumb=bc,
                    relations=relations,
                    extra_metadata={
                        "kompetenz_nr": kompetenz_nr,
                        "standard_nr": standard_nr,
                        "thematische_gruppe": gruppe,
                        **({"offene_verweise": offen} if offen else {}),
                    },
                )
            )

    # ── Abschnitt 3: inhaltsbezogene Kompetenzen, gegliedert nach Bändern ────
    band: tuple[str, int, int, str] | None = None
    band_titel = ""
    # Zuletzt gesehene Leitidee — Bezugspunkt für eine etwaige Unterebene.
    leitidee: tuple[str, list[str], tuple[str, int, int, str]] | None = None
    for h in ueberschriften:
        hid = h.get("id") or ""

        m_band = _ID_UNTERABSCHNITT.match(hid)
        if m_band and m_band.group(1) == "3":
            band_titel = _text(h)
            band = band_aus_ueberschrift(band_titel)
            continue

        # Unterebene (`3.3.1.1 Kinematik`): eigener Knoten unter der Leitidee. Ihre
        # Kompetenzen tragen den Unterebenen-Index dort, wo sonst der Platzhalter `00`
        # steht — die Stelle war in der alten Generation für Gruppen vorgesehen und
        # bekommt hier endlich einen Inhalt.
        m_ue = _ID_UNTEREBENE.match(hid)
        if m_ue and m_ue.group(1) == "3":
            if leitidee is None:
                raise ScraperParseError(url, f"Unterebene {hid} ohne Leitidee")
            eltern_bp_id, eltern_bc, band_werte = leitidee
            segment, min_grade, max_grade, niveau = band_werte
            unter_nr = int(m_ue.group(4))
            gruppen_segment = f"{unter_nr:02d}"
            titel = _text(h)
            bc = eltern_bc + [titel]
            knoten.append(
                _knoten(
                    bp_id=f"{eltern_bp_id}_{unter_nr:02d}", content_type="leitidee",
                    title=titel, content=_intro(h) or titel,
                    parent_bp_id=eltern_bp_id, url=url, breadcrumb=bc,
                    min_grade=min_grade, max_grade=max_grade, niveau=niveau,
                    extra_metadata={"nr": hid},
                )
            )
            _kompetenzen_anhaengen(
                knoten, h, f"{eltern_bp_id}_{unter_nr:02d}", gruppen_segment,
                url, bc, min_grade, max_grade, niveau, bp_id_fach, band_segmente,
            )
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
        leitidee = (li_bp_id, bc, band)
        knoten.append(
            _knoten(
                bp_id=li_bp_id, content_type="leitidee",
                title=li_titel, content=_intro(h) or li_titel,
                parent_bp_id=bp_id_fach, url=url, breadcrumb=bc,
                min_grade=min_grade, max_grade=max_grade, niveau=niveau,
                # Die Nummer als eigenes Feld, nicht nur im Titel: Cross-Fach-Verweise
                # anderer Fächer nennen genau sie (`PH(V3.0) 3.4.3`), und die Auflösung
                # in Schritt 7 sucht danach. Sie stammt aus dem `id`-Attribut der
                # Überschrift — also aus der Quelle, nicht aus dem Titeltext geklaubt.
                extra_metadata={"nr": hid},
            )
        )
        _kompetenzen_anhaengen(
            knoten, h, li_bp_id, "00",
            url, bc, min_grade, max_grade, niveau, bp_id_fach, band_segmente,
        )

    # ── Abschnitt 4: Operatoren ──────────────────────────────────────────────
    knoten.extend(_operatoren(soup, url, bp_id_fach))

    return knoten
