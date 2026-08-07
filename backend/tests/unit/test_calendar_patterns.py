"""UP-8 Schritt 6 — Wochenmuster aus abgerufenen Wochen ableiten.

Das Zeitraster stammt aus der echten Aufzeichnung: elf Einheiten, lückenlos nach den
Stunden 1, 3, 5, 8 und 10. Genau daran entscheidet sich, was eine Doppelstunde ist.
"""
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.calendar.base import Lesson, LessonState
from app.calendar.patterns import (
    A_WOCHE,
    B_WOCHE,
    WOECHENTLICH,
    contiguous_periods,
    derive_patterns,
    week_index,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _timegrid() -> list[tuple[int, int]]:
    raster = json.loads((FIXTURES / "webuntis_timegrid.json").read_text(encoding="utf-8"))

    def minuten(wert):
        stunde, rest = divmod(int(wert), 100)
        return stunde * 60 + rest

    return sorted(
        {
            (minuten(u["startTime"]), minuten(u["endTime"]))
            for tag in raster
            for u in tag["timeUnits"]
        }
    )


TIMEGRID = _timegrid()
MONTAG = date(2026, 6, 8)
WOCHEN = [MONTAG + timedelta(weeks=n) for n in range(4)]


def stunde(
    tag: date,
    start: int,
    *,
    fach="M",
    klasse=("5C",),
    gruppe=None,
    state=LessonState.REGULAR,
    periods=1,
    covering_for=None,
) -> Lesson:
    return Lesson(
        date=tag,
        start_period=start,
        periods=periods,
        state=state,
        subject=fach,
        class_names=klasse,
        student_group=gruppe,
        covering_for=covering_for,
    )


def jede_woche(wochentag: int, start: int, **kwargs) -> list[Lesson]:
    return [
        stunde(w + timedelta(days=wochentag), start, **kwargs) for w in WOCHEN
    ]


# ── Zeitraster ───────────────────────────────────────────────────────────────


def test_zusammenhaengende_stunden_aus_echtem_raster():
    """Doppelstunden haben Lücke 0; jede Pause misst 5 bis 30 Minuten."""
    assert contiguous_periods(TIMEGRID) == {1, 3, 5, 8, 10}


def test_ohne_raster_keine_doppelstunden():
    """Vorgabe des Plans: im Zweifel zwei Einzelstunden — die lassen sich leichter
    zusammenfassen als trennen."""
    assert contiguous_periods([]) == set()


def test_wochenindex():
    assert week_index(MONTAG, MONTAG) == 0
    assert week_index(MONTAG + timedelta(days=4), MONTAG) == 0   # Freitag derselben Woche
    assert week_index(MONTAG + timedelta(weeks=3), MONTAG) == 3


# ── Doppelstunden ────────────────────────────────────────────────────────────


def test_lueckenlose_stunden_werden_zur_doppelstunde():
    lessons = [*jede_woche(1, 3), *jede_woche(1, 4)]        # Di 3.+4., Lücke 0
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    assert len(ergebnis.proposals) == 1
    assert (ergebnis.proposals[0].start_period, ergebnis.proposals[0].periods) == (3, 2)


def test_ueber_eine_pause_hinweg_wird_nicht_verschmolzen():
    """Stunde 2 und 3 trennt eine 25-Minuten-Pause — zwei Einzelstunden."""
    lessons = [*jede_woche(1, 2), *jede_woche(1, 3)]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    assert [(p.start_period, p.periods) for p in ergebnis.proposals] == [(2, 1), (3, 1)]


def test_dreierblock_bleibt_zusammen_solange_luecke_null():
    """Stunden 3, 4, 5: nach 3 lückenlos, nach 4 zehn Minuten Pause → 2 + 1."""
    lessons = [*jede_woche(1, 3), *jede_woche(1, 4), *jede_woche(1, 5)]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    assert [(p.start_period, p.periods) for p in ergebnis.proposals] == [(3, 2), (5, 1)]


def test_bereits_verschmolzene_doppelstunde_wird_aufgeteilt_und_wieder_gepaart():
    """Meldet die Quelle eine Stunde mit `periods=2`, deckt sie beide Positionen ab."""
    lessons = [
        stunde(w + timedelta(days=1), 3, periods=2) for w in WOCHEN
    ]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    assert [(p.start_period, p.periods) for p in ergebnis.proposals] == [(3, 2)]


# ── Rhythmus ─────────────────────────────────────────────────────────────────


def test_jede_woche_ist_woechentlich():
    ergebnis = derive_patterns(jede_woche(0, 1), wochen=WOCHEN, timegrid=TIMEGRID)
    assert ergebnis.proposals[0].rhythmus == WOECHENTLICH
    assert ergebnis.proposals[0].sicher


def test_jede_zweite_woche_ab_der_ersten_ist_a_woche():
    lessons = [
        stunde(WOCHEN[i], 1) for i in (0, 2)
    ]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    assert ergebnis.proposals[0].rhythmus == A_WOCHE
    assert ergebnis.proposals[0].sicher


def test_jede_zweite_woche_ab_der_zweiten_ist_b_woche():
    lessons = [stunde(WOCHEN[i], 1) for i in (1, 3)]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    assert ergebnis.proposals[0].rhythmus == B_WOCHE


def test_eine_woche_erlaubt_keine_rhythmus_aussage():
    """Aus einer Beobachtung 14-tägig zu schließen wäre geraten — und der Hinweis sagt das."""
    eine = [WOCHEN[0]]
    ergebnis = derive_patterns([stunde(WOCHEN[0], 1)], wochen=eine, timegrid=TIMEGRID)
    assert ergebnis.proposals[0].rhythmus == WOECHENTLICH
    assert any("eine Woche" in h for h in ergebnis.hinweise)


def test_luecken_werden_als_unsicher_gekennzeichnet():
    """Drei von vier Wochen ist weder wöchentlich noch 14-tägig — meist ein Feiertag."""
    lessons = [stunde(WOCHEN[i], 1) for i in (0, 1, 2)]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    assert ergebnis.proposals[0].rhythmus == WOECHENTLICH
    assert not ergebnis.proposals[0].sicher


def test_stunden_ohne_gemeinsames_auftreten_verschmelzen_nicht():
    """Stunde 3 in allen vier Wochen, Stunde 4 nur in zweien.

    Das sind **zwei** Sachverhalte: eine verlässliche wöchentliche Stunde und eine
    gelegentliche Verlängerung. Als Doppelstunde zusammengefasst wäre beides verloren —
    die Länge wäre falsch (2 statt 1) und die sichere Stunde erbte die Unsicherheit der
    unsicheren.

    Aufgefallen bei der Abnahme an echten Daten (Schritt 13): Eine einmalige
    Klassenarbeit, die in die Folgestunde hineinreichte, machte aus einer wöchentlichen
    Deutschstunde eine „Doppelstunde, 1× gesehen".
    """
    lessons = [*jede_woche(1, 3), *[stunde(WOCHEN[i] + timedelta(days=1), 4) for i in (0, 1)]]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)

    assert [(p.start_period, p.periods, p.gesehen) for p in ergebnis.proposals] == [
        (3, 1, 4),
        (4, 1, 2),
    ]
    assert ergebnis.proposals[0].sicher          # die wöchentliche bleibt sicher
    assert not ergebnis.proposals[1].sicher      # die gelegentliche wird gemeldet


def test_gemeinsam_aufgetretene_stunden_verschmelzen_weiterhin():
    """Gegenprobe zur Regel oben — die echte Doppelstunde darf nicht zerfallen.

    An echten Daten war das der Normalfall: 684 von 686 benachbarten Stundenpaaren
    traten in denselben Wochen auf.
    """
    lessons = [*jede_woche(1, 3), *jede_woche(1, 4)]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)

    assert len(ergebnis.proposals) == 1
    block = ergebnis.proposals[0]
    assert (block.start_period, block.periods, block.gesehen) == (3, 2, 4)
    assert block.sicher


def test_verschiedene_rhythmen_verschmelzen_nicht():
    """Eine wöchentliche und eine 14-tägige Stunde sind zwei Sachverhalte — auch wenn sie
    im Raster aneinandergrenzen."""
    lessons = [
        *jede_woche(1, 3),
        *[stunde(WOCHEN[i] + timedelta(days=1), 4) for i in (0, 2)],   # A-Woche
    ]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    assert [(p.start_period, p.periods, p.rhythmus) for p in ergebnis.proposals] == [
        (3, 1, WOECHENTLICH),
        (4, 1, A_WOCHE),
    ]


# ── Welche Stunden zählen ────────────────────────────────────────────────────


def test_ausfall_gehoert_zum_muster():
    """Die Stunde stand im Plan — genau das soll das Muster abbilden."""
    lessons = [
        *jede_woche(0, 1)[:3],
        stunde(WOCHEN[3], 1, state=LessonState.CANCELLED),
    ]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    assert ergebnis.proposals[0].gesehen == 4


def test_vertretung_gehoert_zum_muster():
    lessons = [
        *jede_woche(0, 1)[:3],
        stunde(WOCHEN[3], 1, state=LessonState.SUBSTITUTION),
    ]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    assert ergebnis.proposals[0].gesehen == 4


def test_verlegtes_ziel_erzeugt_kein_muster():
    """Der `SHIFT`-Termin ist ein einmaliges Vorkommnis an ungewöhnlicher Position —
    als Muster wäre er ein Phantom."""
    lessons = [
        *jede_woche(0, 1),
        stunde(WOCHEN[0] + timedelta(days=2), 7, state=LessonState.SHIFTED),
    ]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    assert [(p.weekday, p.start_period) for p in ergebnis.proposals] == [(0, 1)]


def test_uebernommene_aufsicht_erzeugt_kein_muster():
    """Fremder Unterricht gehört nicht in den eigenen Stundenplan."""
    lessons = [
        stunde(w, 1, state=LessonState.SUBSTITUTION, covering_for="XYZ") for w in WOCHEN
    ]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    assert ergebnis.proposals == []


def test_pausenaufsicht_wird_gemeldet_nicht_eingeplant():
    """An echten Daten aufgefallen: Pausenaufsicht trägt nur einen Raum (HOF-S, MENSA).

    Steht sie ausnahmsweise als Vertretung im Plan, rutscht sie durch den Zustandsfilter
    und erzeugte ein Muster ohne Gruppe.
    """
    lessons = [
        stunde(w, 2, fach=None, klasse=(), state=LessonState.SUBSTITUTION)
        for w in WOCHEN
    ]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    assert ergebnis.proposals == []
    assert any("ohne Fach und Klasse" in h for h in ergebnis.hinweise)


# ── Gruppenzuordnung ─────────────────────────────────────────────────────────


def test_studentgroup_hat_vorrang_vor_fach_und_klasse():
    """Sonst erschiene dieselbe Gruppe doppelt, sobald die Quelle beides mal liefert."""
    lessons = [
        *[stunde(w, 1, gruppe="ET_5_BU") for w in WOCHEN],
        *[stunde(w + timedelta(days=1), 1, gruppe="ET_5_BU", fach="ETH") for w in WOCHEN],
    ]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    assert {p.key.label for p in ergebnis.proposals} == {"ET_5_BU"}


def test_ohne_studentgroup_trennen_fach_und_klasse():
    lessons = [
        *[stunde(w, 1, fach="M", klasse=("5C",)) for w in WOCHEN],
        *[stunde(w, 2, fach="M", klasse=("6C",)) for w in WOCHEN],
    ]
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    assert {p.key.label for p in ergebnis.proposals} == {"M 5C", "M 6C"}


def test_ohne_wochen_kein_muster():
    ergebnis = derive_patterns([stunde(MONTAG, 1)], wochen=[])
    assert ergebnis.proposals == []
    assert ergebnis.hinweise


@pytest.mark.parametrize("tag", [0, 1, 2, 3, 4])
def test_wochentag_wird_uebernommen(tag):
    ergebnis = derive_patterns(jede_woche(tag, 1), wochen=WOCHEN, timegrid=TIMEGRID)
    assert ergebnis.proposals[0].weekday == tag


# ── Auswahl der Wochen ───────────────────────────────────────────────────────


def _cfg():
    from app.planning.calendar import SchoolYearConfig

    return SchoolYearConfig(
        schuljahr="2025/26",
        beginn=date(2025, 9, 15),
        ende=date(2026, 7, 29),
        halbjahreswechsel=date(2026, 2, 2),
        ferien=[{"name": "Pfingstferien", "von": date(2026, 5, 25), "bis": date(2026, 6, 5)}],
        feiertage=[],
        unterrichtsfreie_tage=[],
    )


def test_wochenauswahl_ist_zusammenhaengend(monkeypatch):
    """Der Kern: über eine Ferienlücke hinweg ist der A/B-Takt nicht bestimmbar.

    Würden Ferienwochen einfach übersprungen, lägen zwischen zwei ausgewählten Wochen
    zwei Kalenderwochen — und jede Rhythmus-Aussage wäre geraten.
    """
    from app.calendar import router as kalender_router
    from app.planning import calendar as planungskalender

    monkeypatch.setattr(planungskalender, "load_school_year", _cfg)
    monkeypatch.setattr(kalender_router, "load_school_year", _cfg)

    wochen = kalender_router._unterrichtswochen(date(2026, 6, 12), 4)
    assert len(wochen) == 4
    assert all((wochen[i + 1] - wochen[i]).days == 7 for i in range(3))
    # Die Pfingstferien liegen NICHT dazwischen.
    assert wochen[-1] < date(2026, 5, 25)


def test_wochenauswahl_bricht_am_schuljahresbeginn_ab(monkeypatch):
    from app.calendar import router as kalender_router
    from app.planning import calendar as planungskalender

    monkeypatch.setattr(planungskalender, "load_school_year", _cfg)
    monkeypatch.setattr(kalender_router, "load_school_year", _cfg)

    wochen = kalender_router._unterrichtswochen(date(2025, 9, 20), 4)
    assert wochen == [date(2025, 9, 15)]


# ── Übernahme in den Editor (Schritt 10b) ────────────────────────────────────


def test_rhythmus_kommt_durch_das_schema():
    """Der Editor schickt `rhythmus` mit — ohne Feld im Schema fiele er lautlos weg."""
    from app.planning.schemas import WeekPatternItem, WeekPatternSet

    gesetzt = WeekPatternSet(
        halbjahr=2,
        patterns=[
            WeekPatternItem(weekday=0, start_period=1, periods=2, rhythmus="a_woche"),
            WeekPatternItem(weekday=2, start_period=5, periods=1),
        ],
    )
    assert gesetzt.patterns[0].rhythmus == "a_woche"
    # Vorgabe wöchentlich: Bestandsmuster kennen das Feld nicht und sind alle wöchentlich.
    assert gesetzt.patterns[1].rhythmus == "woechentlich"


def test_unbekannter_rhythmus_wird_abgelehnt():
    """Sonst landete ein Tippfehler in der Datenbank und verletzte dort den CHECK —
    der Fehler käme erst beim Speichern und ohne Bezug zur Eingabe."""
    import pydantic
    import pytest as _pytest

    from app.planning.schemas import WeekPatternItem

    with _pytest.raises(pydantic.ValidationError):
        WeekPatternItem(weekday=0, start_period=1, periods=1, rhythmus="c_woche")


def test_vorschlag_traegt_alles_was_der_editor_braucht():
    """Wochentag, Stunde, Dauer, Rhythmus — sonst müsste doch wieder abgetippt werden."""
    lessons = jede_woche(1, 3)
    ergebnis = derive_patterns(lessons, wochen=WOCHEN, timegrid=TIMEGRID)
    p = ergebnis.proposals[0]
    assert (p.weekday, p.start_period, p.periods, p.rhythmus) == (1, 3, 1, WOECHENTLICH)
    assert p.sicher is True


@pytest.mark.asyncio
async def test_router_schreibt_den_rhythmus_mit():
    """Der Router baut `GroupWeekPattern` von Hand — ein vergessenes Feld fiele lautlos weg.

    Ohne diesen Test überlebte die Mutation „`rhythmus=item.rhythmus` entfernen"
    unbemerkt: Das Schema trägt das Feld, die Datenbank hat eine Vorgabe, und der Fehler
    zeigte sich erst Monate später als „meine A-Wochen funktionieren nicht".
    """
    from app.db.models import Group, GroupMembership, GroupWeekPattern
    from app.planning.router import set_week_pattern
    from app.planning.schemas import WeekPatternItem, WeekPatternSet

    class FakeDB:
        def __init__(self):
            self.hinzugefuegt: list[GroupWeekPattern] = []

        async def get(self, modell, pk):
            return Group(id=pk, name="Testgruppe", slug="tg", type="teaching_group")

        async def execute(self, stmt):
            class Result:
                def scalar_one_or_none(self_):
                    # Mitgliedschaft nur für die Berechtigungsprüfung vortäuschen.
                    return GroupMembership(
                        group_id=1, pseudonym="p1", role_in_group="teacher"
                    ) if "group_memberships" in str(stmt) else None

            return Result()

        def add(self, obj):
            self.hinzugefuegt.append(obj)

        async def commit(self):
            pass

        async def refresh(self, obj):
            pass

    class User:
        sub = "p1"

    db = FakeDB()
    await set_week_pattern(
        1,
        WeekPatternSet(
            halbjahr=2,
            patterns=[
                WeekPatternItem(weekday=0, start_period=1, periods=2, rhythmus="a_woche"),
                WeekPatternItem(weekday=2, start_period=5, periods=1),
            ],
        ),
        db=db,
        user=User(),
    )
    assert [p.rhythmus for p in db.hinzugefuegt] == ["a_woche", "woechentlich"]
