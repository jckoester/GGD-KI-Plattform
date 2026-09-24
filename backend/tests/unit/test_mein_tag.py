"""Die Auswahlregel der Startseite: heute und der nächste Schultag.

Reine Funktion, reine Tests: ein fester Stichtag und ein gebauter Schuljahreskalender.
Geprüft wird, woran so eine Regel scheitert — Freitag, Ferienvorabend, Schuljahresende,
und die Frage, was ohne Stundenangabe passiert.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional
from uuid import UUID, uuid4

import pytest

from app.planning.calendar import FerienPeriod, NamedDay, SchoolYearConfig
from app.planning.mein_tag import naechster_schultag, waehle

UE = uuid4()

CFG = SchoolYearConfig(
    schuljahr="2026/27",
    beginn=date(2026, 9, 14),
    ende=date(2027, 7, 28),
    halbjahreswechsel=date(2027, 2, 1),
    ferien=[FerienPeriod(name="Herbst", von=date(2026, 10, 26), bis=date(2026, 10, 30))],
    feiertage=[NamedDay(name="Reformationstag", datum=date(2026, 11, 2))],
)


@dataclass
class Slot:
    """Attrappe mit genau den Feldern, die die Regel liest."""
    date: date
    group_id: int = 1
    start_period: Optional[int] = 1
    periods: Optional[int] = 1
    kategorie: str = "unterricht"
    thema: Optional[str] = None
    ue_node_id: Optional[UUID] = None
    stunde_node_id: Optional[UUID] = None
    anpassung_noetig: bool = False
    id: UUID = None

    def __post_init__(self):
        if self.id is None:
            self.id = uuid4()


# ── Der nächste Schultag ──────────────────────────────────────────────────────


def test_am_freitag_ist_der_naechste_schultag_montag():
    """⚠️ **Der Grund, warum die Kachel nicht „Morgen" heißt.**

    Am Freitag ist morgen Samstag. Eine Kachel mit diesem Namen wäre an jedem
    Wochenende eine Falschauskunft — und das ist kein Randfall, sondern zwei von sieben
    Tagen.
    """
    freitag = date(2026, 9, 18)
    assert freitag.weekday() == 4
    assert naechster_schultag(freitag, CFG) == date(2026, 9, 21)


def test_vor_den_ferien_kommt_der_tag_danach():
    """Der letzte Schultag vor den Herbstferien — nächster Unterricht ist eine Woche weiter."""
    letzter = date(2026, 10, 23)          # Freitag vor den Ferien
    assert naechster_schultag(letzter, CFG) == date(2026, 11, 3)


def test_ein_feiertag_wird_uebersprungen():
    # Der 2.11. ist Feiertag; der 3.11. ist der nächste Unterrichtstag.
    assert naechster_schultag(date(2026, 10, 30), CFG) == date(2026, 11, 3)


def test_am_schuljahresende_gibt_es_keinen_naechsten():
    """⚠️ `None` ist eine Auskunft, kein Fehler.

    Die Oberfläche sagt dann, dass das Schuljahr zu Ende ist — statt einen Tag zu
    erfinden oder in das nächste Schuljahr zu greifen, das es noch nicht gibt.
    """
    assert naechster_schultag(date(2027, 7, 28), CFG) is None


def test_die_suche_reicht_ueber_die_ferien_hinweg():
    """Zwei Wochen Pause dürfen die Suche nicht abbrechen lassen."""
    assert naechster_schultag(date(2026, 10, 23), CFG) is not None


# ── Heute und der nächste Tag ─────────────────────────────────────────────────


def test_heute_wird_auch_ohne_unterricht_gezeigt():
    """Wer sonntags nachsieht, soll nicht rätseln, ob die Seite kaputt ist."""
    sonntag = date(2026, 9, 20)
    tag = waehle([Slot(date=date(2026, 9, 21))], sonntag, CFG)
    assert tag.heute.datum == sonntag
    assert tag.heute.stunden == ()
    assert tag.naechster.datum == date(2026, 9, 21)
    assert len(tag.naechster.stunden) == 1


def test_stunden_stehen_in_der_reihenfolge_ihrer_stundennummer():
    """⚠️ Uhrzeiten gibt es nicht — die Reihenfolge schon.

    Eine unsortierte Tagesliste wäre schlechter als eine ohne Uhrzeit.
    """
    heute = date(2026, 9, 21)
    ergebnis = waehle(
        [Slot(date=heute, start_period=5), Slot(date=heute, start_period=1),
         Slot(date=heute, start_period=3)],
        heute, CFG,
    )
    assert [s.start_period for s in ergebnis.heute.stunden] == [1, 3, 5]


def test_stunden_ohne_angabe_stehen_hinten():
    """Ohne Stundenangabe ist „irgendwann" ehrlicher als „zuerst"."""
    heute = date(2026, 9, 21)
    ergebnis = waehle(
        [Slot(date=heute, start_period=None), Slot(date=heute, start_period=2)],
        heute, CFG,
    )
    assert [s.start_period for s in ergebnis.heute.stunden] == [2, None]


def test_ausfall_bleibt_sichtbar():
    """⚠️ Anders als im „Jetzt"-Block.

    Dort geht es um „wo stehe ich?", hier um „was ist heute los?" — eine ausgefallene
    Stunde erklärt die Lücke im Tag, statt sie zu verschweigen.
    """
    heute = date(2026, 9, 21)
    ergebnis = waehle([Slot(date=heute, kategorie="ausfall")], heute, CFG)
    assert [s.kategorie for s in ergebnis.heute.stunden] == ["ausfall"]


def test_nur_die_stunden_des_jeweiligen_tages():
    heute = date(2026, 9, 21)
    ergebnis = waehle(
        [Slot(date=heute), Slot(date=date(2026, 9, 22)), Slot(date=date(2026, 9, 23))],
        heute, CFG,
    )
    assert len(ergebnis.heute.stunden) == 1
    assert len(ergebnis.naechster.stunden) == 1
    assert ergebnis.naechster.datum == date(2026, 9, 22)


def test_am_schuljahresende_fehlt_der_zweite_block():
    ergebnis = waehle([], date(2027, 7, 28), CFG)
    assert ergebnis.naechster is None


# ── Die Beschriftung ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "start,dauer,erwartet",
    [(3, 1, "3."), (3, 2, "3.–4."), (1, 3, "1.–3.")],
)
def test_stundenbezeichnung(start, dauer, erwartet):
    heute = date(2026, 9, 21)
    ergebnis = waehle([Slot(date=heute, start_period=start, periods=dauer)], heute, CFG)
    assert ergebnis.heute.stunden[0].stundenbezeichnung == erwartet


def test_fehlende_stundenangabe_wird_benannt_statt_geraten():
    heute = date(2026, 9, 21)
    ergebnis = waehle([Slot(date=heute, start_period=None)], heute, CFG)
    assert "ohne" in ergebnis.heute.stunden[0].stundenbezeichnung


# ── Warum ein Tag leer ist ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "datum,erwartet",
    [
        (date(2026, 9, 20), "wochenende"),        # Sonntag
        (date(2026, 10, 28), "ferien"),           # Herbstferien
        (date(2026, 11, 2), "feiertag"),
        (date(2026, 9, 21), "kein_unterricht"),   # Schultag, aber keine Stunde
        (date(2026, 8, 1), "ausserhalb_schuljahr"),
    ],
)
def test_grund_unterscheidet_die_lagen(datum, erwartet):
    """⚠️ **Drei Lagen, drei Sätze.**

    „Heute kein Unterricht", „Ferien" und „außerhalb des Schuljahres" sind für die
    Lehrkraft verschiedene Auskünfte. Wer zu Schuljahresbeginn „heute kein Unterricht"
    liest, sucht den Fehler bei sich.
    """
    from app.planning.mein_tag import grund_fuer_leeren_tag

    assert grund_fuer_leeren_tag(datum, CFG) == erwartet


def test_ein_tag_mit_stunden_traegt_keinen_grund():
    """Der Grund ist die Erklärung für die Leere — wo Stunden stehen, erklärt sich nichts."""
    heute = date(2026, 9, 21)
    ergebnis = waehle([Slot(date=heute)], heute, CFG)
    assert ergebnis.heute.grund is None


def test_leerer_tag_traegt_seinen_grund():
    sonntag = date(2026, 9, 20)
    ergebnis = waehle([], sonntag, CFG)
    assert ergebnis.heute.grund == "wochenende"
