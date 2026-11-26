"""Zeitrechnung des Jahresverlaufsplans (Päckchen BD, Schritt 3).

Feste Kalender im Test, nicht `config/`: Die Datei wird zum Schuljahreswechsel getauscht.
Der erste ist der Kalender 2025/26 der Schule — auf ihm stehen die Beispiele der Vorlage für die
Fachschaften (`Konzept/Jahresverlaufsplan-Vorlage.md`).
"""
from datetime import date

import pytest

from app.planning.calendar import SchoolYearConfig
from app.planning.verlaufsplan_zeit import (
    SCHULJAHRESENDE, ferienabschnitte, halbjahr_ab_woche, lage, wochen_bis_zu_den_ferien,
)

KALENDER_2025_26 = SchoolYearConfig.model_validate({
    "schuljahr": "2025/26", "beginn": "2025-09-15", "ende": "2026-07-29",
    "halbjahreswechsel": "2026-02-02",
    "ferien": [
        {"name": "Herbstferien", "von": "2025-10-27", "bis": "2025-11-02"},
        {"name": "Weihnachtsferien", "von": "2025-12-22", "bis": "2026-01-05"},
        {"name": "Faschingsferien", "von": "2026-02-16", "bis": "2026-02-22"},
        {"name": "Osterferien", "von": "2026-03-30", "bis": "2026-04-12"},
        {"name": "Pfingstferien", "von": "2026-05-25", "bis": "2026-06-07"},
    ],
    "feiertage": ["2025-10-03", "2026-01-06", "2026-05-01", "2026-05-14"],
    "unterrichtsfreie_tage": ["2026-05-15", "2026-07-20", "2026-07-21", "2026-07-22",
                              "2026-07-23", "2026-07-24", "2026-07-29"],
})

# Beispiel A der Vorlage: Mathematik Kl. 9, grob
MATHE_9 = [
    {"id": "a1", "wochen": 4, "kapitel_ids": ["aehnlich"]},
    {"id": "a2", "wochen": 6, "kapitel_ids": ["pythagoras"]},
    {"id": "a3", "wochen": 3, "kapitel_ids": ["periodisch"]},
    {"id": "a4", "wochen": 6, "kapitel_ids": ["potenzen"]},
    {"id": "a5", "wochen": 5, "kapitel_ids": ["kreise"]},
    {"id": "a6", "wochen": 4, "kapitel_ids": ["exponential"]},
    {"id": "a7", "wochen": 2, "kapitel_ids": []},                  # Puffer
    {"id": "a8", "wochen": 7, "kapitel_ids": ["wahrscheinlich"]},
]


def _l(abschnitte, cfg=KALENDER_2025_26, **kw):
    return lage(abschnitte, cfg, **kw)


class TestFerienabschnitte:
    def test_zwischen_den_ferien(self):
        f = ferienabschnitte(KALENDER_2025_26)
        assert [(a.von_woche, a.bis_woche, a.endet_mit) for a in f] == [
            (1, 6, "Herbstferien"), (7, 13, "Weihnachtsferien"), (14, 19, "Faschingsferien"),
            (20, 24, "Osterferien"), (25, 30, "Pfingstferien"), (31, 37, SCHULJAHRESENDE),
        ]
        assert sum(a.wochen for a in f) == 37

    def test_bis_zu_den_ferien(self):
        assert wochen_bis_zu_den_ferien(1, KALENDER_2025_26) == 6
        assert wochen_bis_zu_den_ferien(5, KALENDER_2025_26) == 2
        assert wochen_bis_zu_den_ferien(6, KALENDER_2025_26) == 1
        assert wochen_bis_zu_den_ferien(31, KALENDER_2025_26) == 7   # länger als 6: erlaubt
        assert wochen_bis_zu_den_ferien(50, KALENDER_2025_26) == 1   # hinter dem Schuljahr


class TestBeispielMathe:
    @pytest.fixture
    def plan(self):
        return _l(MATHE_9, wochenstunden=4)

    def test_wochen_und_daten(self, plan):
        assert [(a.von_woche, a.bis_woche) for a in plan.abschnitte] == [
            (1, 4), (5, 10), (11, 13), (14, 19), (20, 24), (25, 28), (29, 30), (31, 37)]
        a1, a2, *_, a8 = plan.abschnitte
        assert (a1.beginn, a1.ende) == (date(2025, 9, 15), date(2025, 10, 10))
        assert (a2.beginn, a2.ende) == (date(2025, 10, 13), date(2025, 11, 28))
        # Letzte Woche: zwei Tage — der 29.07. ist unterrichtsfrei
        assert (a8.beginn, a8.ende) == (date(2026, 6, 8), date(2026, 7, 28))

    def test_ferien(self, plan):
        a = plan.abschnitte
        assert a[1].ueber_ferien == ["Herbstferien"] and a[1].vor_ferien is None
        assert a[2].ueber_ferien == [] and a[2].vor_ferien == "Weihnachtsferien"
        assert a[3].vor_ferien == "Faschingsferien"
        assert a[6].vor_ferien == "Pfingstferien"
        assert a[7].vor_ferien is None     # Schuljahresende sind keine eingetragenen Ferien

    def test_halbjahr(self, plan):
        assert [a.nr for a in plan.abschnitte if a.halbjahreswechsel] == [4]

    def test_lang_nur_ueber_sechs(self, plan):
        assert [a.nr for a in plan.abschnitte if a.lang] == [8]

    def test_geht_auf(self, plan):
        assert (plan.unterrichtswochen, plan.belegt, plan.frei, plan.ueberhang) == (37, 37, 0, 0)
        assert all(a.ausserhalb == 0 for a in plan.abschnitte)

    def test_stunden(self, plan):
        assert plan.abschnitte[0].stunden == 16
        assert sum(a.stunden for a in plan.abschnitte) == 148


class TestWochengenau:
    def test_chemie_bis_herbst(self):
        plan = _l([{"wochen": 1}] * 6, wochenstunden=2)
        a = plan.abschnitte
        # Woche 3 endet am Donnerstag: 3. Oktober
        assert (a[2].beginn, a[2].ende) == (date(2025, 9, 29), date(2025, 10, 2))
        assert a[5].vor_ferien == "Herbstferien"
        assert [x.vor_ferien for x in a[:5]] == [None] * 5
        assert (plan.belegt, plan.frei) == (6, 31)


class TestRaender:
    def test_ueberhang(self):
        plan = _l([{"wochen": 36}, {"wochen": 4}, {"wochen": 2}])
        a = plan.abschnitte
        assert (plan.belegt, plan.ueberhang, plan.frei) == (42, 5, 0)
        assert a[1].ausserhalb == 3 and a[1].ende == date(2026, 7, 28)
        # ganz hinter dem Schuljahr: keine Daten
        assert a[2].ausserhalb == 2 and a[2].beginn is None and a[2].ende is None

    def test_leerer_plan(self):
        plan = _l([])
        assert (plan.belegt, plan.frei, plan.abschnitte) == (0, 37, [])

    def test_dauer_null_wird_abgelehnt(self):
        with pytest.raises(ValueError):
            _l([{"wochen": 0}])

    def test_halbjahr_am_abschnittsbeginn_zaehlt_nicht(self):
        # Woche 18 beginnt am 02.02.2026, dem Halbjahreswechsel
        plan = _l([{"wochen": 17}, {"wochen": 2}])
        assert [a.halbjahreswechsel for a in plan.abschnitte] == [False, False]
        assert plan.abschnitte[1].beginn == date(2026, 2, 2)

    def test_ferien_beginnen_mitten_in_der_woche(self):
        cfg = SchoolYearConfig.model_validate({
            "schuljahr": "2030/31", "beginn": "2030-09-09", "ende": "2030-12-20",
            "halbjahreswechsel": "2030-11-04",
            "ferien": [{"name": "Herbstferien", "von": "2030-10-30", "bis": "2030-11-01"}],
        })
        # Woche 8 (28.10.) hat Montag und Dienstag Unterricht, dann Ferien
        plan = lage([{"wochen": 8}, {"wochen": 1}], cfg)
        a = plan.abschnitte
        assert a[0].ende == date(2030, 10, 29) and a[0].vor_ferien == "Herbstferien"
        assert a[1].beginn == date(2030, 11, 4)
        assert [(f.von_woche, f.bis_woche) for f in ferienabschnitte(cfg)] == [(1, 8), (9, 15)]

    def test_kurze_ferien_am_wochenanfang(self):
        # Zwei freie Tage ab Montag: Die Woche hat danach Unterricht und zählt hinter die Ferien.
        cfg = SchoolYearConfig.model_validate({
            "schuljahr": "2030/31", "beginn": "2030-09-09", "ende": "2030-12-20",
            "halbjahreswechsel": "2030-11-04",
            "ferien": [{"name": "Fasnet", "von": "2030-10-28", "bis": "2030-10-29"}],
        })
        plan = lage([{"wochen": 7}, {"wochen": 1}], cfg)
        a = plan.abschnitte
        assert a[0].vor_ferien == "Fasnet" and a[0].ende == date(2030, 10, 25)
        assert a[1].beginn == date(2030, 10, 30)


class TestKapitelbilanz:
    KAPITEL = [{"id": "k1", "titel": "Eins", "std": 12}, {"id": "k2", "titel": "Zwei", "std": 8},
               {"id": "k3", "titel": "Drei", "std": 4}]

    def test_aufteilen_und_fehlende(self):
        plan = _l([{"wochen": 3, "kapitel_ids": ["k1"]},
                   {"wochen": 2, "kapitel_ids": ["k1", "k2"]},
                   {"wochen": 1, "kapitel_ids": ["fremd"]}],
                  wochenstunden=4, kapitel=self.KAPITEL)
        b = {k.kapitel_id: (k.soll, k.geplant, k.wochen) for k in plan.kapitel}
        assert b["k1"] == (12, 16.0, 4.0)
        assert b["k2"] == (8, 4.0, 1.0)
        assert b["k3"] == (4, 0, 0)
        # Ein Kapitel, das nicht (mehr) im Curriculum steht, bleibt sichtbar
        assert b["fremd"] == (None, 4.0, 1.0)
        assert [k.kapitel_id for k in plan.kapitel] == ["k1", "k2", "k3", "fremd"]
        assert plan.kapitel_ohne_abschnitt == ["k3"]

    def test_ohne_wochenstunden_nur_wochen(self):
        plan = _l([{"wochen": 3, "kapitel_ids": ["k1", "k1"]}], kapitel=self.KAPITEL)
        k1 = plan.kapitel[0]
        assert (k1.geplant, k1.wochen) == (None, 3.0)   # doppelt genannt zählt einmal
        assert plan.abschnitte[0].stunden is None


class TestSequenzbilanz:
    """Sequenzgenaue Planung (BD Schritt 7): je Sequenz, zusammengefasst je Kapitel."""
    KAPITEL = [
        {"id": "k1", "titel": "Ähnlichkeit", "std": 99, "sequenzen": [
            {"id": "s1", "titel": "Strahlensätze", "std": 6}, {"id": "s2", "titel": "Streckung", "std": 6}]},
        {"id": "k2", "titel": "Pythagoras", "std": 20, "sequenzen": [{"id": "s3", "titel": "Satzgruppe", "std": None}]},
        {"id": "k3", "titel": "Kreise", "std": 8, "sequenzen": []},
    ]

    def test_je_sequenz_und_je_kapitel(self):
        plan = _l([{"wochen": 2, "sequenz_ids": ["s1", "s2"]},
                   {"wochen": 1, "sequenz_ids": ["s1"]},
                   {"wochen": 1, "sequenz_ids": ["fremd"]}],
                  wochenstunden=4, kapitel=self.KAPITEL, planungsart="sequenz")
        k = {b.kapitel_id: b for b in plan.kapitel}
        # Soll aus den Sequenzen (6 + 6), nicht aus dem Kapitel (99)
        assert (k["k1"].soll, k["k1"].geplant, k["k1"].wochen) == (12, 12.0, 3.0)
        assert [(x.sequenz_id, x.geplant, x.wochen) for x in k["k1"].sequenzen] == [("s1", 8.0, 2.0), ("s2", 4.0, 1.0)]
        # Sequenzen ohne Stunden: Soll des Kapitels
        assert (k["k2"].soll, k["k2"].geplant) == (20, 0)
        assert k["k3"].soll == 8 and k["k3"].sequenzen == []
        # Fremde Sequenz am Ende, ohne Titel
        assert (k["fremd"].titel, k["fremd"].geplant) == (None, 4.0)
        assert [b.kapitel_id for b in plan.kapitel] == ["k1", "k2", "k3", "fremd"]
        assert plan.kapitel_ohne_abschnitt == ["k2", "k3"]
        assert plan.sequenzen_ohne_abschnitt == ["s3"]

    def test_kapitelfelder_zaehlen_bei_sequenzgenau_nicht(self):
        plan = _l([{"wochen": 2, "kapitel_ids": ["k1"]}], kapitel=self.KAPITEL, planungsart="sequenz")
        assert plan.kapitel[0].wochen == 0 and plan.kapitel_ohne_abschnitt == ["k1", "k2", "k3"]

    def test_kapitelgenau_unveraendert(self):
        plan = _l([{"wochen": 2, "kapitel_ids": ["k1"], "sequenz_ids": ["s3"]}], wochenstunden=4,
                  kapitel=self.KAPITEL)
        assert (plan.kapitel[0].soll, plan.kapitel[0].geplant) == (99, 8.0)
        assert plan.kapitel[0].sequenzen == [] and plan.sequenzen_ohne_abschnitt == []


class TestAblaufleiste:
    """Was die Ablaufleiste braucht (zweiter Durchgang): Wochen mit Montag, Ferienlücken, Halbjahr."""

    def test_wochen_mit_montag(self):
        p = _l(MATHE_9)
        assert len(p.wochen) == p.unterrichtswochen == 37
        assert (p.wochen[0].index, p.wochen[0].montag) == (1, date(2025, 9, 15))
        # Nach den Herbstferien geht es mit Woche 7 am 03.11. weiter
        assert (p.wochen[6].index, p.wochen[6].montag) == (7, date(2025, 11, 3))

    def test_ferien_als_luecken_ohne_sommer(self):
        p = _l(MATHE_9)
        assert [(m.name, m.nach_woche) for m in p.ferien] == [
            ("Herbstferien", 6), ("Weihnachtsferien", 13), ("Faschingsferien", 19),
            ("Osterferien", 24), ("Pfingstferien", 30),
        ]

    def test_ferien_nach_der_letzten_woche_sind_keine_luecke(self):
        cfg = KALENDER_2025_26.model_copy(update={"ferien": [
            *KALENDER_2025_26.ferien,
            {"name": "Sommerferien", "von": date(2026, 7, 27), "bis": date(2026, 7, 29)},
        ]})
        cfg = SchoolYearConfig.model_validate(cfg.model_dump())
        assert "Sommerferien" not in [m.name for m in _l(MATHE_9, cfg).ferien]

    def test_halbjahr_beginnt_in_woche_18(self):
        # Wechsel Montag 02.02.2026; Woche 14 beginnt am 05.01. (Ende der Weihnachtsferien)
        assert halbjahr_ab_woche(KALENDER_2025_26) == 18
        assert _l([]).halbjahr_ab_woche == 18

    def test_halbjahr_mitten_in_der_woche_zaehlt_diese_woche(self):
        cfg = SchoolYearConfig.model_validate({**KALENDER_2025_26.model_dump(), "halbjahreswechsel": "2026-02-06"})
        assert halbjahr_ab_woche(cfg) == 18

    def test_halbjahr_in_den_ferien_naechste_woche(self):
        # Wechsel am Mittwoch der Faschingsferien → erste Woche danach (20)
        cfg = SchoolYearConfig.model_validate({**KALENDER_2025_26.model_dump(), "halbjahreswechsel": "2026-02-18"})
        assert halbjahr_ab_woche(cfg) == 20
