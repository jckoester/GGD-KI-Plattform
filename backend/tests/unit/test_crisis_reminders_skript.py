"""Wächter über `scripts/crisis_reminders.py` — den Probelauf.

Der Trockenlauf ersetzt die Vermerk-Funktionen aus `app.crisis.erinnerung`, damit er
`last_reminder_at` nicht setzt. Solange es **eine** war, war das offensichtlich; seit
Migration 0060 sind es zwei, und die zweite zu vergessen bliebe stumm: Der Probelauf
liefe durch, verschickte nichts — und schöbe die Antrags-Erinnerung trotzdem um eine
Woche nach hinten.

Der Test leitet die Liste aus dem Modul ab statt sie aufzuzählen. Eine dritte
Vermerk-Funktion bricht ihn damit von selbst, ohne dass jemand daran denken muss.

Geprüft wird die **Quelle**, nicht das Verhalten: Das Skript ist ein
`__main__`-Programm ohne `__init__.py` (siehe CLAUDE.md, „`scripts/`-Paketkonflikt");
es auszuführen hieße, eine Datenbank und einen Argumentparser mitzubringen, um eine
Zuweisung zu prüfen.
"""
import inspect
from pathlib import Path

import pytest

from app.crisis import erinnerung

SKRIPT = Path(__file__).resolve().parents[2] / "scripts" / "crisis_reminders.py"


def _vermerk_funktionen() -> list[str]:
    """Alle `_vermerke*`-Koroutinen des Erinnerungsmoduls."""
    return sorted(
        name
        for name, wert in vars(erinnerung).items()
        if name.startswith("_vermerke") and inspect.iscoroutinefunction(wert)
    )


def test_das_modul_hat_ueberhaupt_vermerk_funktionen():
    """Sonst prüfte der Test unten eine leere Menge und wäre immer grün."""
    assert len(_vermerk_funktionen()) >= 2


def test_der_probelauf_legt_jede_vermerk_funktion_stumm():
    quelle = SKRIPT.read_text(encoding="utf-8")
    fehlend = [
        name for name in _vermerk_funktionen()
        if f"erinnerung.{name} =" not in quelle
    ]
    assert not fehlend, (
        "Der Probelauf (`--dry-run`) ersetzt diese Vermerk-Funktion(en) nicht: "
        f"{fehlend}. Ohne die Zuweisung setzt ein Trockenlauf `last_reminder_at` "
        "und verschiebt die nächste Erinnerung — ein Probelauf, der etwas ändert, "
        "ist keiner."
    )


@pytest.mark.parametrize("name", _vermerk_funktionen())
def test_lauf_ruft_die_vermerke_ueber_das_modul_auf(name):
    """Das Monkeypatching des Skripts wirkt nur bei einem Modul-Attributzugriff.

    Würde `lauf` die Funktion beim Import an einen lokalen Namen binden (etwa
    `from .erinnerung import _vermerke`), liefe die Zuweisung im Skript ins Leere —
    und zwar lautlos.
    """
    quelle = inspect.getsource(erinnerung.lauf)
    assert f"await {name}(" in quelle
