"""Bausteine für Assistenten-Prompts (0.26, Plan „Rückfall-Assistenten“, Schritt 2).

Ein Baustein ist ein gemessener Textblock, den mehrere Assistenten teilen — etwa
„Begleiten statt lösen“ (Schema jeder Antwort, Hilfe in Stufen, Prüfung gegen den Operator)
und „Grundton“ (Lehrkraft-Behauptung, andere Assistenten, fremde Anliegen, Ton).
Der Assistent wählt ihn über `assistants.bausteine`; die Plattform hängt ihn hinter den
Prompt (`app/pedagogy/compose.py`).

⚠️ **Kommt mit dem Release; die Schule pflegt ihn nicht** (Plan F10, Jan 28.10.2026). Das ist
eine bewusste Abkehr vom Muster „Schulentscheidungen liegen in `config/`“: `pedagogy.yaml`
ist eine Instanzdatei und wird nie überschrieben, eine Nachjustierung erreichte bestehende
Installationen dort nicht. Ein Override durch die Schule steht als Todo („Assistenten-
Bausteine: Override durch die Schule“).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Neben dem Modul, nicht über die Wurzel gerechnet (`test_container_pfade.py`).
VERZEICHNIS = Path(__file__).parent


@dataclass(frozen=True)
class Baustein:
    schluessel: str
    label: str
    beschreibung: str


#: Reihenfolge = Reihenfolge im Systemtext, wenn ein Assistent mehrere wählt.
BAUSTEINE: tuple[Baustein, ...] = (
    Baustein(
        "begleiten_statt_loesen",
        "Begleiten statt lösen",
        "Schema jeder Antwort, nicht vorsagen, Hilfe in Stufen, Prüfung gegen den Operator — "
        "für Schüler-Assistenten, die bei einer Aufgabe begleiten.",
    ),
    # Getrennt, weil nicht jeder Schüler-Assistent eine Aufgabe begleitet: Wer abfragt und
    # Übungen stellt (Lernen und Prüfungsvorbereitung), hat ein eigenes Antwortschema, das
    # „Begleiten statt lösen“ widerspräche (Jan, 28.10.2026, L1).
    Baustein(
        "grundton",
        "Grundton",
        "Lehrkraft-Behauptung, andere Assistenten, Begriffsfragen und fremde Anliegen, Ton — "
        "für alle Schüler-Assistenten.",
    ),
)
SCHLUESSEL = frozenset(b.schluessel for b in BAUSTEINE)


@lru_cache(maxsize=None)
def text(schluessel: str) -> str:
    """Der Text eines Bausteins. Ein unbekannter Schlüssel ist ein Programmierfehler."""
    if schluessel not in SCHLUESSEL:
        raise KeyError(f"unbekannter Baustein {schluessel!r}")
    return (VERZEICHNIS / f"{schluessel}.md").read_text(encoding="utf-8").strip()


def texte(gewaehlt: list[str] | None) -> str:
    """Die gewählten Bausteine in fester Reihenfolge, Unbekanntes übergangen.

    Übergangen statt Fehler: Ein Assistent aus einer neueren Fassung oder ein entfernter
    Baustein soll den Chat nicht anhalten. API und Seed weisen Unbekanntes vorher ab.
    """
    wahl = set(gewaehlt or [])
    return "\n\n".join(text(b.schluessel) for b in BAUSTEINE if b.schluessel in wahl)


def liste() -> list[dict]:
    """Für den Editor: Schlüssel, Label, Beschreibung."""
    return [{"key": b.schluessel, "label": b.label, "beschreibung": b.beschreibung}
            for b in BAUSTEINE]
