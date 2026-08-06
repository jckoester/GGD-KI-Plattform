"""UP-8 Schritt 1 — Adapter-Schnittstelle."""
from datetime import date, datetime

import pytest

from app.calendar import (
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

PASSWORD = "P@ss wort!mit'Sonder\"zeichen$§"


# ── Fake-Adapter: die Schnittstelle einmal wirklich implementiert ──────────────


class FakeAdapter(CalendarAdapter):
    """Minimale Implementierung — belegt, dass die Schnittstelle erfüllbar ist."""

    def __init__(self, password: str = PASSWORD) -> None:
        self._password = password

    @property
    def name(self) -> str:
        return "fake"

    async def fetch_week(self, element: str, week: date) -> FetchResult:
        monday = week.fromordinal(week.toordinal() - week.weekday())
        return FetchResult(
            lessons=[
                Lesson(
                    date=monday,
                    start_period=1,
                    periods=2,
                    state=LessonState.SUBSTITUTION,
                    external_uid="4711",
                    subject="M",
                    class_names=("8a",),
                    teacher_names=(element,),
                    covered_by="ABC",
                )
            ],
            warnings=["1 Eintrag ohne Datum übersprungen"],
            fetched_at=datetime(2026, 8, 6, 12, 0),
        )

    async def check(self) -> None:
        if self._password != PASSWORD:
            # So MUSS es sein: Die Meldung nennt den Fehler, nicht das Geheimnis.
            raise AuthenticationError("Anmeldung am Kalenderdienst fehlgeschlagen")


class LeakyAdapter(FakeAdapter):
    """Gegenbeispiel — schreibt das Passwort in die Fehlermeldung."""

    async def check(self) -> None:
        raise AuthenticationError(f"Login mit {self._password} fehlgeschlagen")


# ── Schnittstelle ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fake_adapter_liefert_normalisierte_stunden():
    result = await FakeAdapter().fetch_week("XYZ", date(2026, 5, 20))
    assert len(result.lessons) == 1
    lesson = result.lessons[0]
    assert lesson.date == date(2026, 5, 18)  # Montag derselben Woche
    assert lesson.state is LessonState.SUBSTITUTION
    assert lesson.external_uid == "4711"
    assert lesson.covered_by == "ABC"
    assert result.warnings == ["1 Eintrag ohne Datum übersprungen"]


@pytest.mark.parametrize(
    "state,expected",
    [
        (LessonState.REGULAR, True),
        (LessonState.EXAM, True),
        (LessonState.CANCELLED, True),
        (LessonState.SUBSTITUTION, True),
        (LessonState.SHIFTED, True),
        (LessonState.NON_TEACHING, False),
        (LessonState.UNKNOWN, False),
    ],
)
def test_creates_slot(state, expected):
    """Pausenaufsicht und Unbekanntes erzeugen keinen Slot — im Zweifel nichts anlegen."""
    lesson = Lesson(date=date(2026, 5, 18), start_period=1, periods=1, state=state)
    assert lesson.creates_slot is expected


def test_uebernommene_aufsicht_erzeugt_keinen_slot():
    """Fremder Unterricht gehört nicht in den eigenen Jahresplan — unabhängig vom Zustand."""
    lesson = Lesson(
        date=date(2026, 5, 18), start_period=1, periods=1,
        state=LessonState.SUBSTITUTION, covering_for="XYZ",
    )
    assert not lesson.creates_slot
    assert not lesson.delivers_planned_content


@pytest.mark.parametrize(
    "state,covered_by,expected",
    [
        (LessonState.REGULAR, None, True),
        (LessonState.EXAM, None, True),
        (LessonState.SHIFTED, None, True),      # Ziel einer Verlegung: findet statt
        (LessonState.CANCELLED, None, False),
        # Der Kern der Begriffsklärung: Vertretung = Aufsicht, kein Unterricht.
        (LessonState.SUBSTITUTION, "XYZ", False),
        (LessonState.NON_TEACHING, None, False),
        (LessonState.UNKNOWN, None, False),
    ],
)
def test_delivers_planned_content(state, covered_by, expected):
    """Ob das geplante Stundenziel erreicht wurde — die Grundlage der Umplanung."""
    lesson = Lesson(
        date=date(2026, 5, 18), start_period=1, periods=1,
        state=state, covered_by=covered_by,
    )
    assert lesson.delivers_planned_content is expected


def test_vertretung_erzeugt_slot_aber_keinen_inhalt():
    """Die eigene vertretene Stunde: Slot ja (sie stand im Plan), Inhalt nein.

    Genau diese Kombination fordert die Umplanung an — ohne den Slot verschwände die
    Stunde, ohne die Inhaltsaussage gälte sie als gehalten.
    """
    lesson = Lesson(
        date=date(2026, 5, 18), start_period=1, periods=1,
        state=LessonState.SUBSTITUTION, covered_by="XYZ",
    )
    assert lesson.creates_slot
    assert not lesson.delivers_planned_content


def test_holiday_einzeltag():
    tag = Holiday(start=date(2026, 5, 15), end=date(2026, 5, 15), name="beweglicher Ferientag")
    block = Holiday(start=date(2026, 2, 16), end=date(2026, 2, 22), name="Faschingsferien")
    assert tag.is_single_day
    assert not block.is_single_day


def test_reschedule_traegt_zielzeitpunkt():
    """Beleg aus der Erhebung: Verlegungen kennen ihr Ziel — der Dialog kann vorschlagen."""
    lesson = Lesson(
        date=date(2026, 7, 9),
        start_period=3,
        periods=1,
        state=LessonState.SHIFTED,
        reschedule=Reschedule(date=date(2026, 7, 10), start_period=5),
    )
    assert lesson.reschedule.date == date(2026, 7, 10)


@pytest.mark.asyncio
async def test_optionale_methoden_melden_sich_verstaendlich():
    """Wer sie nicht kann, sagt das — statt mit AttributeError zu scheitern."""
    with pytest.raises(NotImplementedError, match="fake"):
        await FakeAdapter().fetch_holidays()


def test_fehlertypen_sind_unterscheidbar():
    """`no_school_year` braucht einen eigenen Rat — es ist kein Defekt, sondern ein
    Zeitpunktproblem (WebUntis liefert Ferien nur bei aktivem Schuljahr)."""
    assert issubclass(NoActiveSchoolYearError, CalendarSourceError)
    assert issubclass(AuthenticationError, CalendarSourceError)
    assert not issubclass(NoActiveSchoolYearError, AuthenticationError)


# ── Fehlermeldungen tragen keine Zugangsdaten ────────────────────────────────


@pytest.mark.asyncio
async def test_fehlermeldung_enthaelt_keine_zugangsdaten():
    """Adapter-Meldungen werden angezeigt und protokolliert.

    Ein Adapter, der eine Bibliotheks-Ausnahme durchreicht, kann darin Zugangsdaten
    transportieren — deshalb formulieren Adapter ihre Meldungen selbst. Bleibt auch nach
    dem Wegfall der DB-Verschlüsselung wichtig: Das Passwort steht jetzt in der Umgebung,
    ein Leck ginge über Logs und Fehleranzeigen.
    """
    with pytest.raises(CalendarSourceError) as exc:
        await FakeAdapter(password="falsch").check()
    meldung = str(exc.value)
    assert PASSWORD not in meldung
    assert "falsch" not in meldung


@pytest.mark.asyncio
async def test_der_test_hat_zaehne():
    """Gegenprobe: Der Test oben würde ein Leck auch bemerken."""
    with pytest.raises(CalendarSourceError) as exc:
        await LeakyAdapter().check()
    assert PASSWORD in str(exc.value)
