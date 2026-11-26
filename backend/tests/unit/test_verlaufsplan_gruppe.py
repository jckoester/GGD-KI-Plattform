"""Abschnitt je Planerwoche (BD Teil B, Schritt 1): ohne Datenbank."""
from datetime import date

from app.planning.verlaufsplan_gruppe import abschnitt_je_woche, wochenschluessel


def test_iso_woche_wie_im_planer():
    assert wochenschluessel(date(2025, 9, 15)) == "2025-W38"
    # Jahreswechsel: Der Montag 29.12.2025 gehört zur ISO-Woche 1 von 2026
    assert wochenschluessel(date(2025, 12, 29)) == "2026-W01"


def test_wochen_ueber_ferien_und_ueberhang():
    lage = {
        "wochen": [{"nr": 1, "montag": "2025-10-06"}, {"nr": 2, "montag": "2025-10-20"},
                   {"nr": 3, "montag": "2025-10-27"}],
        "abschnitte": [{"von_woche": 1, "bis_woche": 2}, {"von_woche": 3, "bis_woche": 5}],
    }
    # Woche 2 liegt nach den Herbstferien; Wochen 4 und 5 sind Überhang ohne Montag
    assert abschnitt_je_woche(lage) == {"2025-W41": 0, "2025-W43": 0, "2025-W44": 1}
    assert abschnitt_je_woche(None) == {}
