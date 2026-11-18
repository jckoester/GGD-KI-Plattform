"""Vorige und nächste Stunde **nach Terminen der Gruppe** (0.48, Päckchen N, F4–F6).

Die Navigation im Stundenentwurf kannte bis 0.47 nur die Reihenfolge in der Einheit
(`_build_lesson_nav`). Eine Stunde ohne Einheit — am Schuljahresanfang der Normalfall — hatte
keine, und wer plant, denkt in der Woche: Was kommt am Donnerstag?

Die Regel steht hier als reine Funktion, wie `jetzt.py`. Was sie entscheidet, hängt allein an
den Terminen; die Grenzfälle (Doppelstunde, Ausfall, Termin ohne Entwurf, Lesezustand) lassen
sich so ohne Datenbank prüfen.

- Geordnet nach Datum, dann Stunde im Tag (Termine ohne Stunde zuerst).
- **Ausfälle werden übersprungen** (F5): Ein Ausfall ist kein Ort, an dem man plant.
- **Termine ohne Entwurf zählen mit** (F4 b) — die Oberfläche bietet dort „anlegen“ an. Im
  Lesezustand (Archiv, fremde Gruppe) nicht: Anlegen ginge dort nicht, also zählen nur Termine
  mit einem lesbaren Entwurf.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Protocol
from uuid import UUID

from app.planning.jetzt import NICHT_GEHALTEN


class TerminArtig(Protocol):
    id: UUID
    date: date
    start_period: Optional[int]
    kategorie: str
    stunde_node_id: Optional[UUID]
    thema: Optional[str]


@dataclass(frozen=True)
class Nachbar:
    slot_id: UUID
    datum: date
    start_period: Optional[int]
    kategorie: str
    thema: Optional[str]
    # `None`: Termin ohne (lesbaren) Entwurf — die Oberfläche legt ihn über den Termin an.
    stunde_node_id: Optional[UUID]


def _reihenfolge(s: TerminArtig) -> tuple:
    return (s.date, s.start_period if s.start_period is not None else -1, str(s.id))


def termin_nachbarn(
    termine: Iterable[TerminArtig],
    slot_id: UUID,
    lesbar: set[UUID],
    *,
    anlegen_erlaubt: bool,
) -> tuple[Optional[Nachbar], Optional[Nachbar]]:
    """Voriger und nächster Termin um `slot_id`.

    `lesbar`: die Entwürfe, die es (noch) gibt und die gelesen werden dürfen. Ein
    `stunde_node_id`, das nicht darin steht, gilt als „kein Entwurf“.
    """
    def entwurf(s: TerminArtig) -> Optional[UUID]:
        return s.stunde_node_id if s.stunde_node_id in lesbar else None

    zeilen = sorted(termine, key=_reihenfolge)
    hier = next((i for i, s in enumerate(zeilen) if s.id == slot_id), None)
    if hier is None:
        return None, None

    def zaehlt(s: TerminArtig) -> bool:
        if s.kategorie in NICHT_GEHALTEN:
            return False
        return anlegen_erlaubt or entwurf(s) is not None

    def als_nachbar(s: TerminArtig) -> Nachbar:
        return Nachbar(
            slot_id=s.id, datum=s.date, start_period=s.start_period,
            kategorie=s.kategorie, thema=s.thema, stunde_node_id=entwurf(s),
        )

    vorher = next((als_nachbar(s) for s in reversed(zeilen[:hier]) if zaehlt(s)), None)
    nachher = next((als_nachbar(s) for s in zeilen[hier + 1:] if zaehlt(s)), None)
    return vorher, nachher
