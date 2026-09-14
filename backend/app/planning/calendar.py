"""Schuljahres- und Ferienkalender.

Lädt aus config/school_year.yaml als Single Source of Truth.
SCHOOL_YEAR_PATH-Umgebungsvariable überschreibt den Pfad.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, field_validator, model_validator

from app.core.paths import aufloesen


class FerienPeriod(BaseModel):
    name: str
    von: date
    bis: date


class NamedDay(BaseModel):
    """Ein einzelner Tag (Feiertag oder unterrichtsfreier Tag), optional benannt.

    Akzeptiert in der YAML sowohl ein bloßes Datum (``- 2026-10-03``) als auch
    ein Mapping mit Namen (``- { name: "Tag der Deutschen Einheit", datum: 2026-10-03 }``),
    analog zu den Ferien.
    """

    datum: date
    name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_bare_date(cls, value):
        # Erlaubt die Kurzform ohne Namen: nur das Datum.
        if isinstance(value, (date, str)):
            return {"datum": value}
        return value


class SchoolYearConfig(BaseModel):
    schuljahr: str
    beginn: date
    ende: date
    halbjahreswechsel: date
    ferien: list[FerienPeriod] = []
    feiertage: list[NamedDay] = []
    unterrichtsfreie_tage: list[NamedDay] = []
    # Wie 14-tägige Wochen gezählt werden — siehe `ab_phasen()`. Die Vorgabe entspricht
    # der Beobachtung am GGD; welche gilt, liest man einmal am Stundenplan ab.
    ab_zaehlung: Literal["unterrichtswoche", "kalenderwoche"] = "unterrichtswoche"

    @model_validator(mode="after")
    def _validate_order(self) -> "SchoolYearConfig":
        if not (self.beginn < self.halbjahreswechsel < self.ende):
            raise ValueError(
                "Reihenfolge muss gelten: beginn < halbjahreswechsel < ende"
            )
        for f in self.ferien:
            if f.von < self.beginn or f.bis > self.ende:
                raise ValueError(
                    f"Ferienperiode '{f.name}' liegt außerhalb des Schuljahres"
                )
        return self

    @property
    def feiertage_set(self) -> frozenset[date]:
        return frozenset(t.datum for t in self.feiertage)

    @property
    def unterrichtsfrei_set(self) -> frozenset[date]:
        return frozenset(t.datum for t in self.unterrichtsfreie_tage)


# Die Wurzel **nicht** selbst ausrechnen: `parent`×4 ergab im Container `/` und damit
# `/config/school_year.yaml` — genau der Fehler vom 30.08.2026, der damals Jugendschutz
# und Krisenerkennung still ausfallen ließ. Dass es auf Prod trug, lag allein an
# `SCHOOL_YEAR_PATH` in der Compose; hier stand der Fehler weiter drin.
#
# Der Wächter über diese Fehlerklasse suchte nach `parents[N]` und übersah die
# Schreibweise mit aneinandergehängten `.parent`. Er kennt sie jetzt.
_DEFAULT_PATH = aufloesen(
    os.environ.get("SCHOOL_YEAR_PATH", "") or "config/school_year.yaml"
)


@lru_cache(maxsize=1)
def load_school_year(path: Path | None = None) -> SchoolYearConfig:
    p = path or _DEFAULT_PATH
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return SchoolYearConfig.model_validate(data)


def is_schoolday(d: date, cfg: SchoolYearConfig | None = None) -> bool:
    """True wenn d ein regulärer Schultag ist (kein Wochenende, Ferien, Feiertag)."""
    c = cfg or load_school_year()
    if d < c.beginn or d > c.ende:
        return False
    if d.weekday() >= 5:  # 5=Samstag, 6=Sonntag
        return False
    if d in c.feiertage_set:
        return False
    if d in c.unterrichtsfrei_set:
        return False
    for f in c.ferien:
        if f.von <= d <= f.bis:
            return False
    return True


def halbjahr_of(d: date, cfg: SchoolYearConfig | None = None) -> int:
    """Gibt 1 oder 2 zurück. Tage außerhalb des Schuljahres: 1 wenn vor Wechsel, 2 sonst."""
    c = cfg or load_school_year()
    return 1 if d < c.halbjahreswechsel else 2


def halbjahr_bounds(halbjahr: int, cfg: SchoolYearConfig | None = None) -> tuple[date, date]:
    """Gibt (start, end) des Halbjahres zurück (beide Grenzen inklusiv)."""
    c = cfg or load_school_year()
    if halbjahr == 1:
        return c.beginn, c.halbjahreswechsel - timedelta(days=1)
    return c.halbjahreswechsel, c.ende


# ── A-/B-Wochen ──────────────────────────────────────────────────────────────

# Die drei erlaubten Werte von `group_week_patterns.rhythmus`. Sie stehen hier, weil hier
# auch die Regel steht, die sie in konkrete Wochen übersetzt — die Ableitung aus dem
# Stundenplan und der Slot-Generator müssen dieselben benutzen.
WOECHENTLICH = "woechentlich"
A_WOCHE = "a_woche"
B_WOCHE = "b_woche"


def ab_phasen(cfg: SchoolYearConfig | None = None) -> dict[date, int]:
    """Montag jeder Unterrichtswoche des Schuljahres → 0 (A) oder 1 (B).

    Phase 0 ist die **erste Unterrichtswoche des Schuljahres**. Ein konfiguriertes
    Ankerdatum gibt es bewusst nicht: Welche Woche „A" heißt, ist gleichgültig, solange
    Ableitung und Generator dieselbe Zuordnung benutzen. Gebraucht wird nur die Zählweise,
    und die unterscheidet sich zwischen Schulen wirklich:

    * `unterrichtswoche` — Ferienwochen zählen nicht mit, der Takt läuft über sie hinweg
      weiter. So hält es das GGD (am Stundenplan abgelesen: vor den einwöchigen
      Herbstferien B, danach A).
    * `kalenderwoche` — jede Kalenderwoche zählt, auch eine Ferienwoche.

    Der Unterschied ist keine Geschmacksfrage: Bei **ungerader** Ferienlänge laufen beide
    Zählweisen auseinander, und dann liegt jede 14-tägige Stunde bis zu den nächsten Ferien
    in der falschen Woche. Im Schuljahr 2025/26 traf das drei von sechs Ferienlücken.

    Ein **Mapping**, keine Einzelabfrage: Die Unterrichtswochenzählung muss bei jeder
    Frage wieder am Schuljahresbeginn anfangen, und der Slot-Generator geht jeden Schultag
    eines Halbjahres durch. Einmal bauen, danach nachschlagen.
    """
    c = cfg or load_school_year()
    nach_kalenderwochen = c.ab_zaehlung == "kalenderwoche"
    phasen: dict[date, int] = {}
    montag = c.beginn - timedelta(days=c.beginn.weekday())
    erste: date | None = None
    gezaehlt = 0
    while montag <= c.ende:
        if any(is_schoolday(montag + timedelta(days=n), c) for n in range(5)):
            if erste is None:
                erste = montag
            if nach_kalenderwochen:
                phasen[montag] = ((montag - erste).days // 7) % 2
            else:
                phasen[montag] = gezaehlt % 2
                gezaehlt += 1
        montag += timedelta(weeks=1)
    return phasen


def ab_schultage(
    halbjahr: int, cfg: SchoolYearConfig | None = None
) -> tuple[list[date], list[date]]:
    """Die Schultage eines Halbjahres, getrennt nach A-Woche (Phase 0) und B-Woche.

    Die **Tage**, nicht die Wochenanfänge: Erst damit beantwortet ein Filter nach Wochentag
    die Frage „wann findet dieses Muster statt" vollständig — ein Feiertag nimmt einen
    einzelnen Termin heraus, ohne die Woche zu berühren. Die Oberfläche braucht deshalb
    keinen eigenen Schulkalender; zwei Kalenderrechnungen könnten auseinanderlaufen.
    """
    c = cfg or load_school_year()
    start, ende = halbjahr_bounds(halbjahr, c)
    phasen = ab_phasen(c)
    je_phase: tuple[list[date], list[date]] = ([], [])
    tag = start
    while tag <= ende:
        if is_schoolday(tag, c):
            je_phase[phasen[tag - timedelta(days=tag.weekday())]].append(tag)
        tag += timedelta(days=1)
    return je_phase
