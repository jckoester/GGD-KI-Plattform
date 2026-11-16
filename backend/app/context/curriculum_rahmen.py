"""Rahmenangaben eines Curriculums (0.46, Päckchen AP Teil B, Schritt 4; E19, E20).

Stehen als `metadata.rahmen` am Curriculum-Knoten:

    {"wochenstunden": {"7": 2, "8": 2},
     "lehrwerk": "…", "beschluesse": "…", "schwerpunkte": "…", "absprachen": "…"}

- **Wochenstunden** je Klassenstufe des Bands. Daraus der verplanbare Rahmen:
  30 Stunden je Wochenstunde (E19, Faustregel der Schule) — die Zahl rechnet der Code,
  nicht das Modell. Spiegel im Frontend: `lib/curriculum_rahmen.js`.
- **Textfelder** sind Markdown; im Export als Abschnitt „Rahmen" vor dem ersten Kapitel (E20).

Leere Angaben fallen beim Normalisieren weg; ein Rahmen ohne Angaben ist `{}`.
"""
from __future__ import annotations

import re

from app.context.grades import parse_grade_band

STUNDEN_JE_WOCHENSTUNDE = 30
MAX_WOCHENSTUNDEN = 10

#: Textfelder in der Reihenfolge der Anzeige, mit Beschriftung.
TEXTFELDER: tuple[tuple[str, str], ...] = (
    ("lehrwerk", "Lehrwerk"),
    ("beschluesse", "Beschlüsse der Fachschaft"),
    ("schwerpunkte", "Schwerpunkte"),
    ("absprachen", "Absprachen"),
)


def stufen(jahrgangsstufe: str | None) -> list[int]:
    """Die Klassenstufen eines Bands („7/8" → [7, 8], „9" → [9])."""
    lo, hi = parse_grade_band(jahrgangsstufe)
    return [] if lo is None else list(range(lo, hi + 1))


def _zahl(wert) -> float | int:
    if isinstance(wert, bool):
        raise ValueError("Wochenstunden müssen eine Zahl sein.")
    if isinstance(wert, str):
        wert = wert.strip().replace(",", ".")
    try:
        z = float(wert)
    except (TypeError, ValueError):
        raise ValueError(f"Wochenstunden müssen eine Zahl sein, nicht „{wert}“.") from None
    if not 0 <= z <= MAX_WOCHENSTUNDEN or (z * 2) % 1:
        raise ValueError(f"Wochenstunden zwischen 0 und {MAX_WOCHENSTUNDEN}, in halben Stunden.")
    return int(z) if z.is_integer() else z


def rahmen_normalisieren(rahmen: dict | None) -> dict:
    """Prüft und bereinigt die Rahmenangaben (Kopie). `ValueError` bei unbrauchbaren Werten."""
    if rahmen is None:
        return {}
    if not isinstance(rahmen, dict):
        raise ValueError("Die Rahmenangaben müssen ein Objekt sein.")
    aus: dict = {}
    ws = rahmen.get("wochenstunden") or {}
    if not isinstance(ws, dict):
        raise ValueError("Wochenstunden je Klassenstufe als Objekt, etwa {\"7\": 2}.")
    wochenstunden = {}
    for stufe, wert in ws.items():
        stufe = str(stufe).strip()
        if not re.fullmatch(r"\d{1,2}", stufe):
            raise ValueError(f"„{stufe}“ ist keine Klassenstufe.")
        if wert is None or (isinstance(wert, str) and not wert.strip()):
            continue
        wochenstunden[stufe] = _zahl(wert)
    if wochenstunden:
        aus["wochenstunden"] = dict(sorted(wochenstunden.items(), key=lambda kv: int(kv[0])))
    for feld, _ in TEXTFELDER:
        wert = rahmen.get(feld)
        if wert is None:
            continue
        if not isinstance(wert, str):
            raise ValueError(f"„{feld}“ muss Text sein.")
        if wert.strip():
            aus[feld] = wert.strip()
    return aus


def verplanbar(rahmen: dict | None, jahrgangsstufe: str | None) -> int | float | None:
    """Verplanbare Stunden des Bands: 30 × Wochenstunden, über alle Stufen (E19).

    `None`, solange nicht für jede Stufe des Bands Wochenstunden angegeben sind — eine halbe
    Bilanz wäre irreführend.
    """
    ws = (rahmen or {}).get("wochenstunden") or {}
    st = stufen(jahrgangsstufe)
    if not st or any(str(s) not in ws for s in st):
        return None
    summe = sum(ws[str(s)] for s in st) * STUNDEN_JE_WOCHENSTUNDE
    return int(summe) if float(summe).is_integer() else summe


def _zahl_text(z) -> str:
    return str(z).replace(".", ",")


def wochenstunden_text(rahmen: dict | None, jahrgangsstufe: str | None) -> str:
    """„Kl. 7: 2 · Kl. 8: 2 — verplanbar: 120 Std. (30 je Wochenstunde)" für den Export."""
    ws = (rahmen or {}).get("wochenstunden") or {}
    st = [str(s) for s in stufen(jahrgangsstufe)]
    reihe = [s for s in st if s in ws] + [s for s in ws if s not in st]
    if not reihe:
        return ""
    text = " · ".join(f"Kl. {s}: {_zahl_text(ws[s])}" for s in reihe)
    if (v := verplanbar(rahmen, jahrgangsstufe)) is not None:
        text += f" — verplanbar: {_zahl_text(v)} Std. ({STUNDEN_JE_WOCHENSTUNDE} je Wochenstunde)"
    return text


def rahmen_abschnitte(rahmen: dict | None, jahrgangsstufe: str | None) -> list[tuple[str, str]]:
    """(Beschriftung, Text) für den Abschnitt „Rahmen" im Export; leer, wenn nichts angegeben ist.

    Die Wochenstunden-Zeile ist Klartext, die Textfelder sind Markdown.
    """
    rahmen = rahmen or {}
    aus = []
    if ws := wochenstunden_text(rahmen, jahrgangsstufe):
        aus.append(("Wochenstunden", ws))
    for feld, label in TEXTFELDER:
        if rahmen.get(feld):
            aus.append((label, rahmen[feld]))
    return aus
