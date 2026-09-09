"""„Jetzt" — wo eine Unterrichtsgruppe gerade steht.

Die Auswahlregel für den ersten Block der Gruppenübersicht: laufende und nächste
Unterrichtseinheit, zuletzt gehaltene und die nächsten Stunden. Sie steht hier als
**reine Funktion**, ohne Datenbank: Was sie entscheidet, hängt allein an den Slots
und am Stichtag, und genau die Grenzfälle (Ferien, Schuljahresende, ein
Unterrichtstag, der heute ist) lassen sich so prüfen, ohne eine Welt aufzubauen.

**Warum nicht über `…/overview`.** Der Endpunkt liefert dieselben Slots, dazu aber
Wochenmuster, alle Einheiten, die Stundenbilanz und den kompletten Schuljahres-
kalender mit Ferien und Feiertagen — für fünf Zeilen einer Übersicht.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Protocol
from uuid import UUID

# Ein Ausfall ist kein Ort, an dem man stehengeblieben ist: Er zählt weder als letzte
# noch als nächste Stunde und nicht in die Stundenzahl einer Einheit. Die übrigen
# Kategorien (`unterricht`, `pruefung`, `puffer`, `vertretung`) zählen — auch der
# Puffer, denn er ist verplante Zeit.
NICHT_GEHALTEN = frozenset({"ausfall"})

# Wie viele kommende Stunden der Block zeigt. Drei, weil die Skizze zwei zeigt und
# eine dritte den Blick auf die Woche vervollständigt, ohne zu einer Liste zu werden.
KOMMENDE = 3


class SlotArtig(Protocol):
    """Was die Regel von einem Slot braucht — ORM-Objekt oder Attrappe."""

    id: UUID
    date: date
    start_period: Optional[int]
    kategorie: str
    ue_node_id: Optional[UUID]
    stunde_node_id: Optional[UUID]
    thema: Optional[str]
    nachbereitet_at: object


@dataclass(frozen=True)
class StundeRef:
    slot_id: UUID
    datum: date
    thema: Optional[str]
    kategorie: str
    hat_entwurf: bool
    nachbereitet: bool
    ist_heute: bool
    stunde_node_id: Optional[UUID]


@dataclass(frozen=True)
class EinheitRef:
    node_id: UUID
    stunden_gesamt: int
    stunden_gehalten: int


@dataclass(frozen=True)
class Jetzt:
    laufende_einheit: Optional[EinheitRef]
    naechste_einheit: Optional[EinheitRef]
    zuletzt: Optional[StundeRef]
    kommende: tuple[StundeRef, ...]


def _sortierschluessel(slot: SlotArtig) -> tuple:
    # `start_period` darf fehlen (Slots aus Importen ohne Stundenraster).
    return (slot.date, slot.start_period if slot.start_period is not None else 0)


def _als_stunde(slot: SlotArtig, heute: date) -> StundeRef:
    return StundeRef(
        slot_id=slot.id,
        datum=slot.date,
        thema=slot.thema,
        kategorie=slot.kategorie,
        hat_entwurf=slot.stunde_node_id is not None,
        nachbereitet=slot.nachbereitet_at is not None,
        ist_heute=slot.date == heute,
        stunde_node_id=slot.stunde_node_id,
    )


def _einheit(slots: list[SlotArtig], node_id: UUID, heute: date) -> EinheitRef:
    zugehoerig = [s for s in slots if s.ue_node_id == node_id]
    return EinheitRef(
        node_id=node_id,
        stunden_gesamt=len(zugehoerig),
        stunden_gehalten=sum(1 for s in zugehoerig if s.date <= heute),
    )


def waehle(slots: Iterable[SlotArtig], heute: date, *, kommende: int = KOMMENDE) -> Jetzt:
    """Wählt aus allen Slots einer Gruppe, was der „Jetzt"-Block zeigt.

    `heute` ist ein Stichtag, kein `date.today()` — die Regel bleibt damit prüfbar.

    **Was mit dem heutigen Tag geschieht.** Eine Stunde, die auf `heute` fällt, steht
    unter *kommend*, nicht unter *zuletzt*: Ob sie schon gehalten wurde, weiß die
    Anwendung nicht (Slots tragen kein Ende), und „schon vorbei" zu behaupten wäre
    die riskantere Vermutung. Sie ist über `ist_heute` gekennzeichnet, damit die
    Oberfläche sie als *heute* beschriften kann, statt als *als Nächstes*.
    Für die Stundenzahl einer Einheit zählt sie dagegen mit (`stunden_gehalten` mit
    `<= heute`) — dort geht es um den Fortschritt der Einheit, nicht um die Frage,
    was als Nächstes ansteht.
    """
    gezaehlt = sorted(
        (s for s in slots if s.kategorie not in NICHT_GEHALTEN),
        key=_sortierschluessel,
    )

    vergangen = [s for s in gezaehlt if s.date < heute]
    ab_heute = [s for s in gezaehlt if s.date >= heute]

    zuletzt = _als_stunde(vergangen[-1], heute) if vergangen else None

    # Laufende Einheit: die des jüngsten Slots bis einschließlich heute, der eine
    # Einheit trägt. Vor dem ersten Unterrichtstag gibt es keine — dann ist die
    # erste kommende Einheit die „nächste", nicht die „laufende".
    bis_heute_mit_ue = [s for s in gezaehlt if s.date <= heute and s.ue_node_id is not None]
    laufende_id = bis_heute_mit_ue[-1].ue_node_id if bis_heute_mit_ue else None

    # Nächste Einheit: die erste ab heute, die sich von der laufenden unterscheidet.
    naechste_id = None
    for s in ab_heute:
        if s.ue_node_id is not None and s.ue_node_id != laufende_id:
            naechste_id = s.ue_node_id
            break

    return Jetzt(
        laufende_einheit=_einheit(gezaehlt, laufende_id, heute) if laufende_id else None,
        naechste_einheit=_einheit(gezaehlt, naechste_id, heute) if naechste_id else None,
        zuletzt=zuletzt,
        kommende=tuple(_als_stunde(s, heute) for s in ab_heute[:kommende]),
    )
