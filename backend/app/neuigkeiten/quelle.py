"""Die Hinweise aus `app/neuigkeiten/neuigkeiten.yaml` — geladen, geprüft und je Person gefiltert.

**Eine Stelle entscheidet, wer was sieht** (Plan „Fachbegriffe der Stunde", Schritt 6):
- eine der eigenen Rollen steht in `rollen` — Rollen sind additiv, ein Admin ist auch
  Lehrkraft;
- nicht weggeklickt;
- nicht älter als das eigene Konto (F7.1) — wer neu dazukommt, wird nicht mit alten
  Neuigkeiten begrüßt;
- nicht abgelaufen: `bis`, sonst `LAUFZEIT` Tage ab `datum` (0.25) — ohne Vorgabe blieb ein
  Hinweis für immer stehen;
- der `eintrag` liegt in der eigenen Darstellungsstufe (F7.2). Kennt die Konfiguration der
  Schule den Eintrag gar nicht, erscheint der Hinweis trotzdem: Lieber einer zu viel als ein
  verschluckter.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from app.ui.levels import BEKANNTE_EINTRAEGE, UiLevels

# Neben dem Modul, nicht über die Wurzel gerechnet (`test_container_pfade.py`).
DATEI = Path(__file__).with_name("neuigkeiten.yaml")
ROLLEN = frozenset({"student", "teacher", "admin"})
LAUFZEIT = timedelta(days=42)


class Neuigkeit(BaseModel):
    id: str = Field(min_length=1)
    version: str
    datum: date
    rollen: list[str] = Field(min_length=1)
    titel: str = Field(min_length=1)
    text: str = Field(min_length=1)
    link: str | None = None
    bis: date | None = None
    eintrag: str | None = None

    @field_validator("rollen")
    @classmethod
    def _bekannte_rollen(cls, v: list[str]) -> list[str]:
        unbekannt = sorted(set(v) - ROLLEN)
        if unbekannt:
            raise ValueError(f"unbekannte Rolle(n) {unbekannt} — erlaubt sind {sorted(ROLLEN)}")
        return v

    @field_validator("eintrag")
    @classmethod
    def _bekannter_eintrag(cls, v: str | None) -> str | None:
        if v is not None and v not in BEKANNTE_EINTRAEGE:
            raise ValueError(f"unbekannter Navigationseintrag {v!r}")
        return v

    @field_validator("link")
    @classmethod
    def _interner_link(cls, v: str | None) -> str | None:
        # Nur Seiten der Plattform: Der Hinweis führt in die Hilfe, nicht hinaus.
        if v is not None and not v.startswith("/"):
            raise ValueError("link muss mit / beginnen (eine Seite der Plattform)")
        return v


def lade(pfad: Path | None = None) -> list[Neuigkeit]:
    """Liest und prüft die Datei. Eine doppelte `id` ist ein Fehler, keine Kleinigkeit:
    Wer den ersten Hinweis weggeklickt hat, sähe den zweiten nie."""
    roh = yaml.safe_load((pfad or DATEI).read_text(encoding="utf-8")) or []
    if not isinstance(roh, list):
        raise ValueError("neuigkeiten.yaml muss eine Liste sein")
    liste = [Neuigkeit.model_validate(e) for e in roh]
    doppelt = sorted({n.id for n in liste if [m.id for m in liste].count(n.id) > 1})
    if doppelt:
        raise ValueError(f"doppelte id in neuigkeiten.yaml: {doppelt}")
    return liste


@lru_cache(maxsize=1)
def alle() -> tuple[Neuigkeit, ...]:
    """Einmal je Prozess — die Datei kommt mit dem Release und ändert sich nicht im Betrieb."""
    return tuple(lade())


def sichtbar(
    neuigkeiten: tuple[Neuigkeit, ...] | list[Neuigkeit],
    *,
    rollen: list[str],
    gelesen: set[str],
    konto_seit: datetime | None,
    stufe: int | None,
    stufen: UiLevels,
    heute: date,
) -> list[Neuigkeit]:
    """Die Hinweise, die diese Person sieht — die Regeln stehen oben im Modul."""
    eigene = set(rollen) | ({"teacher"} if "admin" in rollen else set())
    zuschnitt = stufen.fuer(rollen)
    erreichbar = set(zuschnitt.eintraege_bis(stufe)) if zuschnitt and stufe else None
    bekannt = {e for s in zuschnitt.stufen for e in s.eintraege} if zuschnitt else set()
    ergebnis = []
    for n in neuigkeiten:
        if not eigene & set(n.rollen) or n.id in gelesen:
            continue
        if konto_seit is not None and n.datum < konto_seit.date():
            continue
        if (n.bis if n.bis is not None else n.datum + LAUFZEIT) < heute:
            continue
        if n.eintrag and erreichbar is not None and n.eintrag in bekannt and n.eintrag not in erreichbar:
            continue
        ergebnis.append(n)
    return sorted(ergebnis, key=lambda n: n.datum, reverse=True)
