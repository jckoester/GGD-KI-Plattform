"""„Mein Tag" — die eigenen Stunden für heute und den nächsten Schultag.

Die Auswahlregel für die Startseite. Sie steht hier als **reine Funktion**, ohne
Datenbank: Was sie entscheidet, hängt allein an den Slots, am Stichtag und am
Schuljahreskalender — und genau die Grenzfälle (Freitag, Ferienvorabend,
Schuljahresende) lassen sich so prüfen, ohne eine Welt aufzubauen. Dasselbe Muster wie
`jetzt.py`.

⚠️ **Keine Uhrzeit.** `lesson_slots` trägt `start_period` und `periods`, aber keine
Tageszeit (Befund Jan, 23.09.2026). Ob eine Stunde schon *vorbei* ist, lässt sich daraus
nicht sagen; das käme nur aus dem Stundenraster des Stundenplans, und dafür eine
Abhängigkeit aufzumachen, nur um Zeilen grau zu färben, stünde in keinem Verhältnis.
Was es gibt, ist die **Reihenfolge** — danach wird sortiert und beschriftet
(„3.–4. Stunde" statt „09:45").

**Warum „nächster Schultag" und nicht „morgen".** Am Freitag ist morgen Samstag, vor den
Ferien liegt der nächste Unterricht Wochen entfernt. Eine Kachel „Morgen", die den
8. Januar zeigt, wäre eine Falschauskunft. Gesucht wird deshalb der nächste Tag, den der
Schuljahreskalender als Schultag führt.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional, Protocol
from uuid import UUID

from app.planning.calendar import SchoolYearConfig, is_schoolday

# Wie weit vorwärts nach einem Schultag gesucht wird. Sechs Wochen decken die
# Sommerferien nicht ab — das ist Absicht: Danach gibt es keinen „nächsten Schultag"
# mehr, sondern ein neues Schuljahr.
MAX_VORLAUF_TAGE = 42


class SlotArtig(Protocol):
    """Was die Regel von einem Slot braucht — ORM-Objekt oder Attrappe."""

    id: UUID
    group_id: int
    date: date
    start_period: Optional[int]
    periods: Optional[int]
    kategorie: str
    thema: Optional[str]
    ue_node_id: Optional[UUID]
    stunde_node_id: Optional[UUID]
    anpassung_noetig: bool


@dataclass(frozen=True)
class StundeAmTag:
    slot_id: UUID
    group_id: int
    start_period: Optional[int]
    periods: int
    kategorie: str
    thema: Optional[str]
    hat_entwurf: bool
    # ⚠️ **Die Id, nicht nur das Ja/Nein.** Ohne sie lässt sich der Weg in den
    # Stundenentwurf nicht bauen — `hat_entwurf` sagt, *dass* es einen gibt, nicht
    # *welchen*. Das hat am 24.09.2026 einen toten Link erzeugt, den weder der
    # Funktionstest noch der Quelltext-Wächter sahen.
    stunde_node_id: Optional[UUID]
    ue_node_id: Optional[UUID]
    anpassung_noetig: bool

    @property
    def stundenbezeichnung(self) -> str:
        """„3." oder „1.–2." — die Zeitangabe, die das System hat.

        **Ohne das Wort „Stunde"** (Jan, 24.09.2026): In einer Tagesliste steht es in
        jeder Zeile und kostet Platz, den der Titel besser braucht. Die Ordnungszahl
        allein ist eindeutig — und ein angehängtes „h" wäre es gerade **nicht**, weil es
        sich als Uhrzeit lesen ließe, die es hier nicht gibt.
        """
        if self.start_period is None:
            return "ohne Angabe"
        if self.periods > 1:
            return f"{self.start_period}.–{self.start_period + self.periods - 1}."
        return f"{self.start_period}."


@dataclass(frozen=True)
class Tag:
    datum: date
    ist_heute: bool
    stunden: tuple[StundeAmTag, ...]
    # Nur gesetzt, wenn `stunden` leer ist: warum. Siehe `grund_fuer_leeren_tag`.
    grund: Optional[str] = None


@dataclass(frozen=True)
class MeinTag:
    heute: Tag
    naechster: Optional[Tag]


def naechster_schultag(
    ab: date, cfg: SchoolYearConfig, *, max_tage: int = MAX_VORLAUF_TAGE
) -> Optional[date]:
    """Der nächste Schultag **nach** `ab` — oder `None`, wenn keiner mehr kommt.

    Bewusst nicht `ab + 1 Tag`: Am Freitag ist das Samstag, vor den Ferien ein Ferientag.
    Gefragt ist, wann wieder Unterricht stattfindet.

    `None` am Schuljahresende ist eine Auskunft, kein Fehler — die Oberfläche sagt dann,
    dass das Schuljahr zu Ende ist, statt einen Tag zu erfinden.
    """
    for versatz in range(1, max_tage + 1):
        kandidat = ab + timedelta(days=versatz)
        if is_schoolday(kandidat, cfg):
            return kandidat
    return None


def grund_fuer_leeren_tag(datum: date, cfg: SchoolYearConfig) -> str:
    """Warum an diesem Tag nichts steht — damit die Oberfläche nicht raten muss.

    ⚠️ **Drei Lagen, drei Sätze.** „Heute kein Unterricht", „Ferien" und „noch keine
    Planung" sind für die Lehrkraft völlig verschiedene Auskünfte: Die erste ist eine
    Feststellung, die zweite eine Erklärung, die dritte eine **Aufforderung**. Sie
    zusammenzufassen wäre der bequeme Weg und der falsche — wer zu Schuljahresbeginn
    „heute kein Unterricht" liest, sucht den Fehler bei sich.

    Der Grund wird hier bestimmt und nicht in der Oberfläche: Ferien, Feiertage und
    unterrichtsfreie Tage stehen im Schuljahreskalender, und den hat nur der Server.
    """
    if datum < cfg.beginn or datum > cfg.ende:
        return "ausserhalb_schuljahr"
    if datum.weekday() >= 5:
        return "wochenende"
    if datum in cfg.feiertage_set:
        return "feiertag"
    if datum in cfg.unterrichtsfrei_set:
        return "unterrichtsfrei"
    for f in cfg.ferien:
        if f.von <= datum <= f.bis:
            return "ferien"
    return "kein_unterricht"


def _als_stunde(slot: SlotArtig) -> StundeAmTag:
    return StundeAmTag(
        slot_id=slot.id,
        group_id=slot.group_id,
        start_period=slot.start_period,
        # `periods` kann fehlen (Import ohne Stundenraster) — dann ist es eine Stunde.
        periods=slot.periods or 1,
        kategorie=slot.kategorie,
        thema=slot.thema,
        hat_entwurf=slot.stunde_node_id is not None,
        stunde_node_id=slot.stunde_node_id,
        ue_node_id=slot.ue_node_id,
        anpassung_noetig=bool(slot.anpassung_noetig),
    )


def _sortierschluessel(slot: SlotArtig) -> tuple:
    # `start_period` darf fehlen (Slots aus Importen ohne Stundenraster). Solche Stunden
    # ans Ende statt an den Anfang: Ohne Angabe ist „irgendwann" ehrlicher als „zuerst".
    return (slot.start_period is None, slot.start_period or 0, slot.group_id)


def _tag(
    slots: Iterable[SlotArtig], datum: date, heute: date, cfg: SchoolYearConfig
) -> Tag:
    passend = sorted((s for s in slots if s.date == datum), key=_sortierschluessel)
    return Tag(
        datum=datum,
        ist_heute=datum == heute,
        stunden=tuple(_als_stunde(s) for s in passend),
        grund=None if passend else grund_fuer_leeren_tag(datum, cfg),
    )


def waehle(slots: Iterable[SlotArtig], heute: date, cfg: SchoolYearConfig) -> MeinTag:
    """Heute und der nächste Schultag, je mit den Stunden darin.

    **Ausfall und Vertretung bleiben sichtbar** — anders als im „Jetzt"-Block. Dort geht
    es um „wo stehe ich?", hier um „was ist heute los?", und eine ausgefallene Stunde ist
    eine Auskunft über den Tag: Sie erklärt die Lücke, statt sie zu verschweigen.

    **Heute wird immer gezeigt** — auch wenn es kein Schultag ist. Wer sonntags
    nachsieht, soll nicht rätseln, ob die Seite kaputt ist; die Oberfläche sagt dann
    „heute kein Unterricht" und der zweite Block trägt den Montag.
    """
    alle = list(slots)
    naechster_tag = naechster_schultag(heute, cfg)
    return MeinTag(
        heute=_tag(alle, heute, heute, cfg),
        naechster=_tag(alle, naechster_tag, heute, cfg) if naechster_tag else None,
    )
