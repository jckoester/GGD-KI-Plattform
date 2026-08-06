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

    **Zu `SUBSTITUTION` siehe die Begriffsklärung bei `Lesson.covered_by`** — „Vertretung"
    bedeutet an dieser Schule Aufsicht, nicht Fortführung des Unterrichts.
    """

    REGULAR = "regular"
    EXAM = "exam"
    CANCELLED = "cancelled"
    SUBSTITUTION = "substitution"
    SHIFTED = "shifted"
    # Kein Unterricht — Pausenaufsicht, Bereitschaft, Zusatztermine. Erzeugt keinen Slot.
    NON_TEACHING = "non_teaching"
    UNKNOWN = "unknown"


# Abbildung auf die `kategorie` eines `lesson_slots` (CHECK-Constraint dort:
# unterricht/pruefung/ausfall/puffer/vertretung). Hier zentral, damit Schritt 6 und
# Schritt 8 dieselbe Zuordnung verwenden und nicht auseinanderlaufen.
SLOT_CATEGORY: dict[LessonState, str] = {
    LessonState.REGULAR: "unterricht",
    LessonState.EXAM: "pruefung",
    LessonState.CANCELLED: "ausfall",
    LessonState.SUBSTITUTION: "vertretung",
    # SHIFTED ist **Unterricht**, kein Ausfall. Die Aufzeichnung vom 06.08.2026 zeigt: Eine
    # Verlegung erscheint als Paar — der Ursprung als `CANCEL`, das Ziel als `SHIFT`. Der
    # `SHIFT`-Termin ist die Stunde, die tatsächlich stattfindet; als Ausfall geführt,
    # verschwände sie aus der Jahresplanung, obwohl unterrichtet wird. Der Ausfall steckt
    # in der Gegenseite des Paares, die ohnehin `CANCELLED` ist.
    LessonState.SHIFTED: "unterricht",
}


@dataclass(frozen=True)
class Reschedule:
    """Der **andere** Termin einer Verlegung.

    Eine Verlegung erscheint in WebUntis als **Paar**: am Ursprungstermin ein `CANCEL`, am
    Zieltermin ein `SHIFT` — beide mit derselben `lessonId` und beide mit einem
    `rescheduleInfo`, das auf die jeweils andere Seite zeigt. Ohne die Richtung wäre nicht
    zu unterscheiden, ob ein Termin abgegeben oder aufgenommen hat; der Verschiebe-Dialog
    aus UP-6 würde eine bereits verlegte Stunde erneut zum Verlegen anbieten.

    `is_source = True`: **Dieser** Termin ist der Ursprung, der Unterricht findet am
    genannten Termin statt.
    `is_source = False`: Dieser Termin ist das Ziel, der Unterricht kam vom genannten
    Termin hierher.
    """

    date: date
    start_period: int | None = None
    is_source: bool = True

    @property
    def moved_to(self) -> "date | None":
        """Wohin die Stunde verlegt wurde — None, wenn dieser Termin das Ziel ist."""
        return self.date if self.is_source else None

    @property
    def moved_from(self) -> "date | None":
        """Woher die Stunde kam — None, wenn dieser Termin der Ursprung ist."""
        return None if self.is_source else self.date


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
    # Kennung der Unterrichtsgruppe aus der Quelle (WebUntis: `studentGroup`, am GGD in der
    # Form `ET_5_BU` = Fach_Jahrgang_Kürzel). Trägt die Zuordnung zur `teaching_group` in
    # Schritt 7 — ohne sie müsste sie aus Fach und Klasse erraten werden.
    student_group: str | None = None

    # ── Vertretung: zwei Seiten, zwei völlig verschiedene Folgen ──────────────
    #
    # **Begriffsklärung.** „Vertretung" heißt an dieser Schule: Eine andere Lehrkraft
    # übernimmt die **Aufsicht** über die Klasse. Sie führt den Unterricht nicht fort. Sie
    # kann Aufgaben der ausfallenden Lehrkraft austeilen, das geplante Stundenziel wird
    # aber **nicht** erreicht. Eine vertretene Stunde ist für die Jahresplanung damit so
    # gut wie ausgefallen und muss umgeplant werden — siehe `delivers_planned_content`.
    #
    # Welche Seite man sieht, hängt davon ab, wessen Plan abgefragt wurde. Die Aufzeichnung
    # vom 06.08.2026 zeigt beide Rollen in denselben Feldern (`elements[].id` /
    # `.orgId`), weshalb sie hier auseinandergehalten werden:

    # Ich übernehme die Aufsicht für diese Lehrkraft. **Fremder** Unterricht: fremdes Fach,
    # fremde Klasse, keine meiner Unterrichtsgruppen. Erzeugt deshalb keinen Slot in meiner
    # Jahresplanung — es ist eine Beanspruchung meiner Zeit, keine Stunde meines Plans.
    covering_for: str | None = None
    # Meine Stunde, beaufsichtigt von dieser Lehrkraft. Erzeugt einen Slot — **mein**
    # Stundenziel steht aus und muss nachgeholt werden.
    covered_by: str | None = None

    reschedule: Reschedule | None = None
    # Rohwert der Quelle, wenn `state` UNKNOWN ist. Für die Fehlermeldung, nicht für Logik.
    raw_state: str | None = None

    @property
    def creates_slot(self) -> bool:
        """Ob aus dieser Stunde ein `lesson_slot` in **meiner** Jahresplanung werden darf.

        Drei Fälle sagen Nein:

        * Pausenaufsicht (`BREAKSUPERVISION`), Bereitschaft, Zusatztermine — kein Unterricht.
        * Ein unbekannter Zustand — im Zweifel nichts anlegen und melden, statt etwas
          Falsches anzulegen.
        * **Eine Vertretung, die ich übernehme** (`covering_for`). Das ist der Unterricht
          einer anderen Lehrkraft in einer Klasse, die keine meiner Unterrichtsgruppen ist.
          Als Slot angelegt, stünde eine fremde Stunde in meinem Jahresplan.
        """
        if self.covering_for:
            return False
        return self.state not in (LessonState.NON_TEACHING, LessonState.UNKNOWN)

    @property
    def delivers_planned_content(self) -> bool:
        """Ob das **geplante Stundenziel** an diesem Termin erreicht wurde.

        Der Unterschied zu `creates_slot` ist der Kern der Umplanung: Ein Slot kann
        entstehen, ohne dass Unterricht im geplanten Sinne stattgefunden hat.

        Nein sagt das bei Ausfall — und bei **Vertretung**: Die vertretende Lehrkraft führt
        den Unterricht nicht fort, sondern beaufsichtigt (siehe Begriffsklärung oben). Was
        an einem solchen Termin geplant war, steht weiterhin aus.

        Ja sagt es bei regulärem Unterricht, bei Prüfungen und am **Ziel** einer Verlegung —
        dort findet die Stunde statt, nur zu anderer Zeit.
        """
        if not self.creates_slot:
            return False
        if self.covered_by:
            return False
        return self.state in (
            LessonState.REGULAR,
            LessonState.EXAM,
            LessonState.SHIFTED,
        )


@dataclass(frozen=True)
class SchoolYear:
    """Ein Schuljahr, wie die Quelle es kennt.

    Enthält bewusst **keinen** Halbjahreswechsel: Die WebUntis-Schnittstelle kennt ihn
    nicht (`getSchoolyears` liefert nur `id`, `name`, `startDate`, `endDate`). Er ist eine
    Entscheidung der Schule und bleibt in `school_year.yaml`.
    """

    name: str
    start: date
    end: date

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end


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

    async def fetch_holidays(
        self, within: tuple[date, date] | None = None
    ) -> list[Holiday]:
        """Unterrichtsfreie Abschnitte (Datenstrom A).

        `within` grenzt auf ein Schuljahr ein (Beginn, Ende). Quellen liefern gern den
        Kalender **aller** Jahre; ohne Eingrenzung bekäme der Import Abschnitte, die er
        anschließend sämtlich verwerfen müsste.

        Optional: Eine Quelle, die nur Stundenpläne kennt, überschreibt das nicht.
        """
        raise NotImplementedError(f"{self.name} liefert keinen Ferienkalender")

    async def fetch_school_years(self) -> list[SchoolYear]:
        """Die Schuljahre, die die Quelle kennt — für Beginn und Ende.

        Optional wie `fetch_holidays`.
        """
        raise NotImplementedError(f"{self.name} kennt keine Schuljahre")

    async def check(self) -> None:
        """Verbindung und Zugangsdaten prüfen, ohne Daten zu holen.

        Für den „Verbindung testen"-Knopf in der Verwaltung. Wirft bei Fehlschlag eine
        `CalendarSourceError`; Erfolg ist die Abwesenheit einer Ausnahme.
        """
        raise NotImplementedError(f"{self.name} unterstützt keine Verbindungsprüfung")
