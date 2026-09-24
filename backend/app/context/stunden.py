"""Die Stundenzahl eines Curriculum-Kapitels — aus freiem JSON zu einer Zahl.

⚠️ **Warum es diese Datei gibt.** `context_nodes.metadata` ist JSONB und erzwingt nichts.
Der Curriculum-Entwurf deklarierte `std: str | None` (`context/schemas.py`), die
Jahresplanung las dasselbe Feld als `int | None` (`planning/schemas.py`). Im Dev-Bestand
standen daraufhin **18 von 24** Kapiteln als Zeichenkette da, 6 als Zahl.

Aufgefallen ist das nicht an der Typannotation, sondern an einem Absturz: Pydantic wandelt
`"12"` beim Bauen einer Antwort still in `12` um, nur `_build_balance` rechnet **vor** der
Validierung — `max(0, zugewiesen - soll_std)` warf `TypeError`, und die **ganze**
Jahresübersicht antwortete mit 500. Die Lehrkraft sah, wie eine neu angelegte
Unterrichtseinheit nicht erschien, klickte noch einmal und hatte eine Dublette
(Jan, 24.09.2026).

Die Lehre: *Eine Typannotation über einem JSONB-Feld ist eine Hoffnung, keine Zusage.*
Wer aus `metadata` liest, normalisiert selbst.
"""

from __future__ import annotations


def als_stundenzahl(wert: object) -> int | None:
    """Eine ganze Zahl von Unterrichtsstunden — oder ``None``, wenn es keine ist.

    **Streng mit Absicht.** Angenommen wird nur, was *vollständig* eine nicht-negative
    ganze Zahl ist; alles andere wird zu ``None`` („unbekannt"). Aus ``"12-14"`` die 12 zu
    nehmen wäre bequem und eine **Erfindung**: Niemand hat 12 Stunden gesagt. Eine
    fehlende Angabe kann die Oberfläche benennen, eine falsche nicht.

    >>> als_stundenzahl(12), als_stundenzahl("12"), als_stundenzahl(" 12 ")
    (12, 12, 12)
    >>> als_stundenzahl("12-14"), als_stundenzahl("ca. 8"), als_stundenzahl("")
    (None, None, None)
    >>> als_stundenzahl(None), als_stundenzahl(-3), als_stundenzahl(True)
    (None, None, None)
    """
    # `bool` ist in Python eine `int`-Unterklasse: `True` würde sonst zu 1 Stunde.
    if isinstance(wert, bool):
        return None
    if isinstance(wert, int):
        return wert if wert >= 0 else None
    if isinstance(wert, float):
        return int(wert) if wert >= 0 and wert.is_integer() else None
    if isinstance(wert, str):
        text = wert.strip()
        if not text.isdigit():  # schließt Vorzeichen, Punkte und Zusätze aus
            return None
        return int(text)
    return None
