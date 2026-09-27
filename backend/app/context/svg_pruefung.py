"""Ist dieses SVG harmlos genug, um es zu speichern und später anzuzeigen?

**Warum es das Modul erst ab Paket 10 gibt.** Bis dahin kamen alle SVGs im
Wissensgraphen aus eigenen Werkzeugen — LaTeX über `dvisvgm`/`pdftocairo`, der
Render-Sidecar, matplotlib. `app/render/export.py` schreibt diese Annahme sogar hin
(„die SVGs stammen aus den eigenen Renderern"). Mit dem Upload-Dialog (AP3) stimmt sie
nicht mehr: Eine Lehrkraft lädt eine Datei hoch, deren Inhalt niemand gesehen hat, und
sie landet in `metadata.illustrationen[].svg` — also in der Datenbank, im Chat-Kontext,
in der Detailansicht und im PDF-Export.

**Geprüft, nicht umgeschrieben.** Ein Sanitisierer, der ein Bild „repariert", gibt der
Autorin etwas anderes zurück, als sie hochgeladen hat, und sie erfährt es nicht. Wer
eine Zeichnung importiert, soll sie unverändert wiederfinden — oder eine Meldung
bekommen, was daran nicht geht. Deshalb gibt diese Prüfung einen **Grund** zurück und
kein Ergebnis-SVG.

**Sperrliste, keine Positivliste.** Die gefährlichen Bauteile sind wenige und bekannt;
die harmlosen sind viele und wachsen (die Pilotdateien tragen unter anderem ein
`c2pa:manifest` aus einem fremden Namensraum). Eine Positivliste der Elemente hätte
genau solche Dateien abgewiesen, ohne dass irgendjemand dadurch sicherer wäre.

⚠️ **Das Frontend sanitisiert zusätzlich** (`sanitizeSvg`, DOMPurify). Das ist kein
Grund, hier nachlässig zu sein: Dieselben Bytes gehen auch in den PDF-Export, in dem
kein DOMPurify sitzt, und an DOMPurify vorbei kommt jeder, der die API direkt liest.
"""
from __future__ import annotations

import re
from xml.etree import ElementTree

#: Der Namensraum, den ein SVG-Wurzelelement tragen muss.
SVG_NS = "http://www.w3.org/2000/svg"

# ⚠️ **Vor dem Parsen, nicht danach.** Expat löst keine *externen* Entities auf, wohl
# aber interne — „billion laughs" wäre damit möglich, und zwar bevor irgendeine Prüfung
# den Baum zu sehen bekommt. Werkzeugerzeugte SVGs haben keine Dokumenttypdeklaration;
# eine hochgeladene Datei mit einer hat sie aus einem Grund.
_DEKLARATION = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)

#: `url(…)` in einem Attributwert oder in `<style>` — erlaubt ist nur der Verweis auf
#: eine Stelle **im selben Dokument** (`url(#clip1)`, so arbeiten Clip-Pfade).
_URL = re.compile(r"url\(\s*['\"]?\s*([^)'\"]*)", re.IGNORECASE)

#: Elemente, die ein Bild nicht braucht und die Verhalten mitbringen: Skript, fremdes
#: Markup, eingebettete Dokumente, Animation. Ein importierter Fachbegriff zeigt eine
#: **stehende** Zeichnung; `<animate attributeName="href" to="javascript:…">` ist der
#: Grund, warum auch die Animationselemente hier stehen.
VERBOTENE_ELEMENTE = frozenset({
    "script", "foreignobject", "iframe", "embed", "object", "audio", "video",
    "handler", "animate", "animatetransform", "animatemotion", "set",
})


def _lokal(name: str) -> str:
    """`{http://…}path` → `path`, kleingeschrieben."""
    return name.rsplit("}", 1)[-1].lower()


def _url_grund(wert: str, wo: str) -> str | None:
    for treffer in _URL.finditer(wert):
        ziel = treffer.group(1).strip()
        if not ziel.startswith("#"):
            return f"verweist in {wo} nach außen — `url({ziel[:40]})`"
    return None


def pruefe_svg(roh: str) -> str | None:
    """``None``, wenn die Datei gespeichert werden darf; sonst der Grund im Klartext.

    Der Grund wird Lehrkräften im Importbericht gezeigt — er nennt das Bauteil, nicht
    die Gefahr. „Enthält `<script>`" sagt, was zu entfernen ist; „unsicher" nicht.
    """
    if _DEKLARATION.search(roh):
        return "enthält eine Dokumenttyp- oder Entity-Deklaration"
    try:
        wurzel = ElementTree.fromstring(roh)
    except ElementTree.ParseError as fehler:
        return f"ist kein gültiges XML ({fehler})"

    if wurzel.tag != f"{{{SVG_NS}}}svg":
        # ⚠️ Auch ein `<svg>` **ohne** `xmlns` fällt durch. Das ist die einzige Zusage
        # der Datei, eine Zeichnung sein zu wollen; ohne sie liest ein Browser den
        # Inhalt als HTML. Jedes Zeichenwerkzeug schreibt den Namensraum.
        return (
            f"hat <{_lokal(wurzel.tag)}> als Wurzelelement — erwartet wird ein <svg> "
            f"mit `xmlns=\"{SVG_NS}\"`"
        )

    for element in wurzel.iter():
        name = _lokal(element.tag)
        if name in VERBOTENE_ELEMENTE:
            return f"enthält <{name}>"
        if name == "style":
            text = element.text or ""
            if "@import" in text.lower():
                return "enthält ein `@import` in <style>"
            if grund := _url_grund(text, "<style>"):
                return grund

        for attribut, wert in element.attrib.items():
            kurz = _lokal(attribut)
            if kurz.startswith("on"):
                return f"enthält das Ereignis-Attribut `{kurz}`"
            if "javascript:" in wert.replace(" ", "").lower():
                return f"enthält `javascript:` in `{kurz}`"
            if kurz == "href" and not wert.strip().startswith("#"):
                # `<use xlink:href="#g0-1">` ist der Normalfall aus dvisvgm; alles
                # andere holt etwas von außen oder führt etwas aus.
                return f"verweist mit `{kurz}` nach außen — `{wert.strip()[:40]}`"
            if grund := _url_grund(wert, f"`{kurz}`"):
                return grund
    return None
