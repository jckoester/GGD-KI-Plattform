"""Jahrgangs-/Stufen-Parsing — zentral, damit Schreibpfade und Matching konsistent sind.

`parse_grade_band` normalisiert das freie `jahrgangsstufe`-Label eines Curriculums in
strukturierte `(min_grade, max_grade)` (kanonisch in den Spalten `min_grade`/`max_grade`).
`parse_class_grade` zieht die Jahrgangszahl aus einem Klassennamen.
"""

from __future__ import annotations

import re


def parse_grade_band(value: str | None) -> tuple[int | None, int | None]:
    """Normalisiert ein Jahrgangs-/Stufenband in ``(min_grade, max_grade)``.

    Annahme: Bänder sind **zusammenhängend** — min/max genügt. Nicht-zusammenhängende
    Angaben (z. B. ``"5/7"`` ohne 6) würden als ``(5, 7)`` inkl. 6 interpretiert.

    Beispiele::

        "8"         -> (8, 8)
        "5/6"       -> (5, 6)
        "7/8/9/10"  -> (7, 10)
        "5-6"       -> (5, 6)
        "5–6"       -> (5, 6)   # Gedankenstrich
        ""/None/"EF" -> (None, None)
    """
    if not value:
        return (None, None)
    nums = [int(m) for m in re.findall(r"\d+", value)]
    if not nums:
        return (None, None)
    return (min(nums), max(nums))


def parse_class_grade(class_name: str | None) -> int | None:
    """Führende Jahrgangs-Zahl aus einem Klassennamen.

    ``"10C"`` -> 10, ``"8a"`` -> 8, ``"EF"`` -> None, ``"Q1"`` -> None.
    """
    if not class_name:
        return None
    m = re.match(r"^\s*(\d+)", class_name)
    return int(m.group(1)) if m else None
