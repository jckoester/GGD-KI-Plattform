"""Was ein Assistent herstellt — die Angabe „stellt her" (0.40, Päckchen AM).

Ein **Werkzeug** ist ein Assistent mit dieser Angabe: Er trägt in der Assistentenliste eine
Marke („erstellt Bilder") und lässt sich danach filtern. Die Angabe ist ein eigenes Feld, keine
Ableitung aus den Fähigkeiten zur Laufzeit (Plan 0.40, F1): Ein Schaltplan-Assistent stellt
Diagramme her, ohne eine Fähigkeit dafür zu brauchen, und wer einem Bild-Assistenten die Marke
abwählt, will das so.

Diese Liste ist die **einzige** Quelle. Das Frontend holt Kennungen und Beschriftungen über
`GET /assistants/produktarten`; die Migration 0102 belegt den Bestand nach `faehigkeit` vor.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Produktart:
    id: str
    #: Marke an der Assistentenkarte.
    marke: str
    #: Beschriftung im Filter der Assistentenliste und im Editor.
    filter: str
    #: Fähigkeit, deren Einschalten im Editor diese Art vorschlägt (und nach der die Migration
    #: den Bestand vorbelegt). ``None`` = keine; die Angabe wird von Hand gesetzt.
    faehigkeit: Optional[str] = None


#: Reihenfolge = Reihenfolge in Editor, Filter und Marken.
PRODUKTARTEN: tuple[Produktart, ...] = (
    Produktart("image", "erstellt Bilder", "Bilder", "image_generation"),
    Produktart("diagram", "erstellt Diagramme", "Diagramme"),
    Produktart("document", "erstellt Dokumente", "Dokumente"),
    Produktart("lesson_plan", "plant Stunden", "Stundenentwürfe", "lesson_planning"),
    Produktart("year_plan", "plant das Schuljahr", "Jahresplanung", "planning"),
)

KENNUNGEN: frozenset[str] = frozenset(p.id for p in PRODUKTARTEN)


def unbekannte(werte: list[str]) -> list[str]:
    """Kennungen, die es nicht gibt — in der Reihenfolge des Eingangs."""
    return [w for w in werte if w not in KENNUNGEN]


def geordnet(werte: list[str]) -> list[str]:
    """Bekannte Kennungen ohne Doppelte, in der Reihenfolge von ``PRODUKTARTEN``."""
    gesetzt = set(werte)
    return [p.id for p in PRODUKTARTEN if p.id in gesetzt]
