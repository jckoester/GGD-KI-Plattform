"""Stundenplan- und Kalenderintegration (UP-8).

`base` definiert die Adapter-Schnittstelle, `secrets` die Verschlüsselung der
Zugangsdaten in `calendar_sources.config`.

**Nicht verwechseln** — drei ähnlich benannte Dinge:

* `app.calendar` (hier) — **externe** Quellen: Stundenplan abrufen, Ferien abrufen.
* `app.planning.calendar` — der **eigene** Schuljahreskalender aus `school_year.yaml`
  (`is_schoolday()`, Halbjahre). Ziel des Ferien-Imports, nicht seine Quelle.
* `calendar` (Stdlib) — wird von absoluten Importen weiterhin korrekt getroffen; dieses
  Paket verschattet es nicht.
"""
from app.calendar.base import (
    AuthenticationError,
    CalendarAdapter,
    CalendarSourceError,
    FetchResult,
    Holiday,
    Lesson,
    LessonState,
    NoActiveSchoolYearError,
    Reschedule,
)

__all__ = [
    "AuthenticationError",
    "CalendarAdapter",
    "CalendarSourceError",
    "FetchResult",
    "Holiday",
    "Lesson",
    "LessonState",
    "NoActiveSchoolYearError",
    "Reschedule",
]
