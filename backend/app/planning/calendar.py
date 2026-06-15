"""Schuljahres- und Ferienkalender.

Lädt aus config/school_year.yaml als Single Source of Truth.
SCHOOL_YEAR_PATH-Umgebungsvariable überschreibt den Pfad (Docker).
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator, model_validator


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


_DEFAULT_PATH = Path(
    os.environ.get("SCHOOL_YEAR_PATH", "")
    or Path(__file__).resolve().parent.parent.parent.parent / "config" / "school_year.yaml"
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
