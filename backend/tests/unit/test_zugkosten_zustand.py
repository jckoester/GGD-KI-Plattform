"""Wie belastbar die Kostensumme eines Chat-Zuges ist.

Ein Zug besteht aus mehreren LLM-Anfragen (je Werkzeugrunde eine, dazu die
Titelgenerierung). Findet die Abrechnung nicht alle SpendLogs, ist die Summe eine
**Teilsumme** — bis Migration 0058 ununterscheidbar von einer vollständigen, und
damit ein stiller Fehlbetrag in der Admin-Statistik.
"""
from app.chat.router import Zugkosten


def test_alle_gefunden_ist_vollstaendig():
    assert Zugkosten(summe=0.01, gefunden=3, gesamt=3).zustand == "vollstaendig"


def test_teilsumme_ist_unvollstaendig():
    # Der eigentliche Punkt: Die Summe existiert und ist trotzdem zu niedrig.
    assert Zugkosten(summe=0.006, gefunden=2, gesamt=3).zustand == "unvollstaendig"


def test_nichts_gefunden_ist_ebenfalls_unvollstaendig():
    # Nicht „vollständig, nur eben null" — es ist schlicht nichts bekannt.
    assert Zugkosten(summe=None, gefunden=0, gesamt=3).zustand == "unvollstaendig"


def test_zug_ohne_anfragen_gilt_als_vollstaendig():
    # 0 von 0: Es gibt nichts abzurechnen, also fehlt auch nichts.
    assert Zugkosten(summe=None, gefunden=0, gesamt=0).zustand == "vollstaendig"


def test_zustand_kennt_nur_die_erlaubten_werte():
    # Der CHECK-Constraint aus 0058 lässt nichts anderes zu — ein Tippfehler hier
    # äußerte sich erst beim Schreiben, mitten im Chat.
    erlaubt = {"ausstehend", "vollstaendig", "unvollstaendig"}
    for gefunden, gesamt in ((0, 0), (0, 2), (1, 2), (2, 2)):
        assert Zugkosten(None, gefunden, gesamt).zustand in erlaubt
