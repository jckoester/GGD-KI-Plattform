"""Adapter-Schnittstelle für Stundenplan- und Kalenderquellen (UP-8, Schritt 1).

Zweck wie beim `AuthAdapter` (ADR-003 Teil 2): Die Planungslogik kennt **keine** konkrete
Quelle. WebUntis ist eine Implementierung dieser Schnittstelle, nicht die Schnittstelle
selbst — eine Schule ohne WebUntis bleibt voll arbeitsfähig (Handpflege in
`school_year.yaml`, manuelle Wochenmuster), und ein anderer Stundenplanserver braucht
später nur einen Adapter, kein neues Datenmodell.

Der `Lesson`-Datensatz ist die Normalform: Was hier nicht auftaucht, kennt die
Planungslogik nicht. Er ist nach dem gebaut, was die Erhebung vom 06.08.2026 belegt hat —
`cellState`, `lessonId`, typisierte `elements`, `orgId`, `rescheduleInfo`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class LessonState(Enum):
    """Zustand einer Stunde, quellenunabhängig.

    Bewusst eine geschlossene Aufzählung statt der WebUntis-`cellState`-Zeichenkette: Ein
    unbekannter Zustand aus einer Quelle darf nicht ungeprüft bis in die Slot-Logik
    durchschlagen. Der Adapter bildet ab; was er nicht kennt, wird `UNKNOWN` und
    entsprechend gemeldet.
    """

    REGULAR = "regular"
    CANCELLED = "cancelled"
    SUBSTITUTION = "substitution"
    SHIFTED = "shifted"
    # Kein Unterricht — Pausenaufsicht, Bereitschaft, Zusatztermine. Erzeugt keinen Slot.
    NON_TEACHING = "non_teaching"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Reschedule:
    """Zielzeitpunkt einer Verlegung, falls die Quelle ihn nennt.

    Die Erhebung hat belegt, dass WebUntis das tut (`rescheduleInfo`) — deshalb kann der
    Verschiebe-Dialog aus UP-6 konkret vorschlagen statt nur zu melden.
    """

    date: date
    start_period: int | None = None


@dataclass(frozen=True)
class Lesson:
    """Eine Stunde aus einer Kalenderquelle, normalisiert.

    `external_uid` ist die stabile Identität der Quelle (bei WebUntis die `lessonId`). Sie
    trägt die Idempotenz: Ein zweiter Abruf derselben Woche darf keine Dubletten erzeugen.
    Ohne sie wäre jeder Wiederholungslauf ein Ratespiel über Datum und Stunde.
    """

    date: date
    start_period: int | None
    periods: int
    state: LessonState
    external_uid: str | None = None

    subject: str | None = None
    class_names: tuple[str, ...] = ()
    teacher_names: tuple[str, ...] = ()
    room: str | None = None

    # Wer ursprünglich vorgesehen war — aus `elements[].orgId`. Nur bei Vertretung gesetzt.
    original_teacher: str | None = None
    reschedule: Reschedule | None = None
    # Rohwert der Quelle, wenn `state` UNKNOWN ist. Für die Fehlermeldung, nicht für Logik.
    raw_state: str | None = None

    @property
    def creates_slot(self) -> bool:
        """Ob aus dieser Stunde ein `lesson_slot` werden darf.

        Pausenaufsicht (`BREAKSUPERVISION`), Bereitschaft und Zusatztermine sind kein
        Unterricht. Ein unbekannter Zustand erzeugt ebenfalls keinen Slot — im Zweifel
        nichts anlegen und melden, statt etwas Falsches anzulegen.
        """
        return self.state not in (LessonState.NON_TEACHING, LessonState.UNKNOWN)


@dataclass(frozen=True)
class Holiday:
    """Ein unterrichtsfreier Abschnitt (Datenstrom A).

    `start == end` ist ein Einzeltag. Die Einteilung in Ferien / Feiertag / beweglicher Tag
    trifft **nicht** der Adapter: `is_schoolday()` fragt alle drei Config-Schlüssel gleich
    ab, die Kategorie ist Lesbarkeit. Der Adapter liefert Zeitraum und Namen; wie das in
    `school_year.yaml` einsortiert wird, entscheidet der Import (Schritt 4).
    """

    start: date
    end: date
    name: str

    @property
    def is_single_day(self) -> bool:
        return self.start == self.end


@dataclass
class FetchResult:
    """Ergebnis eines Abrufs — Nutzdaten **und** was dabei nicht sauber war.

    Die Warnungen sind kein Beiwerk. Ein Adapter, der still das Beste aus kaputten Daten
    macht, erzeugt einen Plan, dem man ansieht, dass er stimmt, ohne dass er stimmt. Was
    übersprungen wurde, gehört in die Statusanzeige.
    """

    lessons: list[Lesson] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fetched_at: datetime | None = None


class CalendarSourceError(RuntimeError):
    """Basisfehler aller Adapter.

    Wichtig: Die Meldung wird in `calendar_sources.last_error` gespeichert und dem Admin
    angezeigt. Sie darf **niemals** Zugangsdaten enthalten — auch nicht in einer
    durchgereichten Ursprungsmeldung. Adapter formulieren sie selbst, statt eine
    Bibliotheks-Ausnahme weiterzureichen.
    """


class AuthenticationError(CalendarSourceError):
    """Anmeldung fehlgeschlagen — falsche Zugangsdaten oder Konto gesperrt."""


class NoActiveSchoolYearError(CalendarSourceError):
    """Die Quelle hat kein aktives Schuljahr.

    Eigener Fehlertyp, weil er einen eigenen Rat verdient: Das ist kein Defekt, sondern
    ein Zeitpunktproblem. WebUntis liefert den Ferienkalender nur bei aktivem Schuljahr
    (Erhebung 06.08.2026) — in den Sommerferien also gar nicht. Als allgemeiner Fehler
    gemeldet, sähe das nach einer kaputten Einrichtung aus.
    """


class CalendarAdapter(ABC):
    """Eine Quelle für Stundenplandaten.

    Implementierungen bekommen ihre Verbindungsparameter aus `calendar_sources.config`
    (entschlüsselt) und halten sonst keinen Zustand, der einen Prozess überlebt.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Kurzname für Anzeige und Protokoll, z. B. `webuntis`."""

    @abstractmethod
    async def fetch_week(self, element: str, week: date) -> FetchResult:
        """Stunden einer Kalenderwoche für ein Element (z. B. ein Lehrkraft-Kürzel).

        `week` ist ein beliebiges Datum **in** der gewünschten Woche; der Adapter bestimmt
        die Wochengrenzen selbst. Das erspart jedem Aufrufer die Montagsrechnung — und
        damit die Sorte Fehler, die nur in Wochen mit Feiertag auffällt.
        """

    async def fetch_holidays(self) -> list[Holiday]:
        """Unterrichtsfreie Abschnitte (Datenstrom A).

        Optional: Eine Quelle, die nur Stundenpläne kennt, überschreibt das nicht. Der
        Ferien-Import fällt dann auf den eingetragenen ICS-Kalender oder die Handpflege
        zurück.
        """
        raise NotImplementedError(f"{self.name} liefert keinen Ferienkalender")

    async def check(self) -> None:
        """Verbindung und Zugangsdaten prüfen, ohne Daten zu holen.

        Für den „Verbindung testen"-Knopf in der Verwaltung. Wirft bei Fehlschlag eine
        `CalendarSourceError`; Erfolg ist die Abwesenheit einer Ausnahme.
        """
        raise NotImplementedError(f"{self.name} unterstützt keine Verbindungsprüfung")
