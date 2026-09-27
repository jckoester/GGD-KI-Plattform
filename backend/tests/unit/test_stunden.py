"""Die Normalisierung der Kapitel-Stundenzahl.

⚠️ Der Anlass war kein Schönheitsfehler: Eine Zeichenketten-`std` ließ die **ganze**
Jahresübersicht mit 500 antworten (`TypeError` in `_build_balance`), und die Lehrkraft
sah nur, dass ihre neue Unterrichtseinheit nicht erschien.
"""
import pytest

from app.context.stunden import als_stundenzahl


@pytest.mark.parametrize("wert,erwartet", [
    (12, 12),
    ("12", 12),
    ("  12  ", 12),
    ("0", 0),
    (0, 0),
    (12.0, 12),
])
def test_nimmt_was_eindeutig_eine_zahl_ist(wert, erwartet):
    assert als_stundenzahl(wert) == erwartet


@pytest.mark.parametrize("wert", ["12-14", "ca. 8", "8 Std", "", "   ", "acht", None, [], {}])
def test_erfindet_keine_zahl(wert):
    """⚠️ **Aus „12-14" die 12 zu nehmen wäre bequem und eine Erfindung.**

    Niemand hat 12 Stunden gesagt. Eine fehlende Angabe kann die Oberfläche benennen,
    eine falsche nicht.
    """
    assert als_stundenzahl(wert) is None


def test_true_ist_keine_stunde():
    """`bool` ist in Python eine `int`-Unterklasse — ohne eigene Prüfung wäre `True` 1."""
    assert als_stundenzahl(True) is None
    assert als_stundenzahl(False) is None


def test_negative_stundenzahl_ist_keine():
    assert als_stundenzahl(-3) is None
    assert als_stundenzahl("-3") is None
