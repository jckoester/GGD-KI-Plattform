"""Die reinen Teile von `finde_stunde` (0.15, Schritt 3): Zeitraum, Datum, Teiltreffer.

Das Datum rechnet der Server — deshalb hier jeder Wert von `wann` gegen einen festen Tag.
"""
from datetime import date

import pytest

from app.planning.stunde_finden import WANN, flach, lies_datum, zeitraum

FREITAG = date(2026, 10, 9)


@pytest.mark.parametrize("wann,erwartet", [
    ("heute", (date(2026, 10, 9), date(2026, 10, 9))),
    # Der Kalendertag, nicht der nächste Schultag — dafür gibt es „naechste".
    ("morgen", (date(2026, 10, 10), date(2026, 10, 10))),
    ("naechste", (date(2026, 10, 9), date(2026, 11, 20))),
    ("diese_woche", (date(2026, 10, 5), date(2026, 10, 11))),
    ("naechste_woche", (date(2026, 10, 12), date(2026, 10, 18))),
    ("letzte_woche", (date(2026, 9, 28), date(2026, 10, 4))),
])
def test_zeitraum(wann, erwartet):
    assert zeitraum(wann, FREITAG) == erwartet


def test_datum_braucht_ein_datum():
    assert zeitraum("datum", FREITAG) is None
    assert zeitraum("datum", FREITAG, datum=date(2026, 10, 15)) == (date(2026, 10, 15),) * 2


def test_jeder_wert_ist_aufgeloest():
    """Ein neuer Wert in `WANN` ohne Zweig in `zeitraum` fiele sonst erst im Chat auf."""
    for wann in WANN:
        assert zeitraum(wann, FREITAG, datum=FREITAG) is not None, wann
    assert zeitraum("uebermorgen", FREITAG) is None


@pytest.mark.parametrize("text,heute,erwartet", [
    ("2026-10-15", FREITAG, date(2026, 10, 15)),
    ("15.10.2026", FREITAG, date(2026, 10, 15)),
    ("15.10.26", FREITAG, date(2026, 10, 15)),
    ("15.10.", FREITAG, date(2026, 10, 15)),
    # Ohne Jahr das nächstliegende — über den Jahreswechsel hinweg.
    ("3.1.", date(2026, 12, 20), date(2027, 1, 3)),
    ("28.12.", date(2027, 1, 4), date(2026, 12, 28)),
])
def test_lies_datum(text, heute, erwartet):
    assert lies_datum(text, heute) == erwartet


@pytest.mark.parametrize("text", ["", "morgen", "31.02.", "15/10", "15.10.2026x"])
def test_kein_datum(text):
    assert lies_datum(text, FREITAG) is None


def test_flach_fuer_teiltreffer():
    assert flach("Ch-9 d") == "ch9d"
    assert flach("9d") in flach("ch-9d")
    assert flach(None) == ""
