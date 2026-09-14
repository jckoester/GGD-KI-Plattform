"""Unit-Tests für app.planning.calendar."""

from datetime import date, timedelta

import pytest

from app.planning.calendar import (
    FerienPeriod,
    NamedDay,
    SchoolYearConfig,
    ab_phasen,
    ab_schultage,
    halbjahr_bounds,
    halbjahr_of,
    is_schoolday,
)


def _cfg() -> SchoolYearConfig:
    return SchoolYearConfig(
        schuljahr="2026/27",
        beginn=date(2026, 9, 14),
        ende=date(2027, 7, 28),
        halbjahreswechsel=date(2027, 2, 8),
        ferien=[
            FerienPeriod(name="Herbst", von=date(2026, 10, 26), bis=date(2026, 10, 30)),
        ],
        feiertage=[date(2026, 11, 1)],
        unterrichtsfreie_tage=[date(2026, 10, 2)],
    )


def test_is_schoolday_normal():
    assert is_schoolday(date(2026, 9, 14), _cfg()) is True  # Montag


def test_is_schoolday_weekend():
    assert is_schoolday(date(2026, 9, 19), _cfg()) is False  # Samstag
    assert is_schoolday(date(2026, 9, 20), _cfg()) is False  # Sonntag


def test_is_schoolday_ferien():
    assert is_schoolday(date(2026, 10, 26), _cfg()) is False
    assert is_schoolday(date(2026, 10, 30), _cfg()) is False
    # Tag nach Ferien wieder Schule
    assert is_schoolday(date(2026, 10, 31), _cfg()) is False  # Allerheiligen aber kein Feiertag in cfg hier
    assert is_schoolday(date(2026, 11, 2), _cfg()) is True  # Montag nach Allerheiligen (nicht in feiertagen)


def test_is_schoolday_feiertag():
    assert is_schoolday(date(2026, 11, 1), _cfg()) is False


def test_is_schoolday_unterrichtsfreier_tag():
    assert is_schoolday(date(2026, 10, 2), _cfg()) is False


def test_is_schoolday_before_schuljahr():
    assert is_schoolday(date(2026, 9, 13), _cfg()) is False


def test_is_schoolday_after_schuljahr():
    assert is_schoolday(date(2027, 7, 29), _cfg()) is False


def test_halbjahr_of_hj1():
    cfg = _cfg()
    assert halbjahr_of(date(2026, 9, 14), cfg) == 1
    # letzter Tag HJ1
    assert halbjahr_of(date(2027, 2, 7), cfg) == 1


def test_halbjahr_of_hj2():
    cfg = _cfg()
    # erster Tag HJ2
    assert halbjahr_of(date(2027, 2, 8), cfg) == 2
    assert halbjahr_of(date(2027, 7, 28), cfg) == 2


def test_halbjahr_bounds_hj1():
    cfg = _cfg()
    start, end = halbjahr_bounds(1, cfg)
    assert start == date(2026, 9, 14)
    assert end == date(2027, 2, 7)  # halbjahreswechsel - 1


def test_halbjahr_bounds_hj2():
    cfg = _cfg()
    start, end = halbjahr_bounds(2, cfg)
    assert start == date(2027, 2, 8)
    assert end == date(2027, 7, 28)


def test_validation_order_error():
    with pytest.raises(ValueError, match="beginn < halbjahreswechsel"):
        SchoolYearConfig(
            schuljahr="2026/27",
            beginn=date(2027, 2, 8),
            ende=date(2027, 7, 28),
            halbjahreswechsel=date(2026, 9, 14),
        )


def test_named_and_bare_days_coexist():
    """Feiertage/unterrichtsfreie Tage akzeptieren bloßes Datum und {name, datum}."""
    cfg = SchoolYearConfig(
        schuljahr="2026/27",
        beginn=date(2026, 9, 14),
        ende=date(2027, 7, 28),
        halbjahreswechsel=date(2027, 2, 8),
        feiertage=[
            {"name": "Allerheiligen", "datum": date(2026, 11, 1)},
            date(2026, 12, 25),  # Kurzform ohne Namen
        ],
        unterrichtsfreie_tage=[
            {"name": "Pädagogischer Tag", "datum": date(2026, 10, 2)},
        ],
    )
    # Namen bleiben erhalten
    assert cfg.feiertage[0].name == "Allerheiligen"
    assert cfg.feiertage[1].name is None
    assert cfg.unterrichtsfreie_tage[0].name == "Pädagogischer Tag"
    # Sets enthalten die Daten unabhängig von der Schreibweise
    assert cfg.feiertage_set == {date(2026, 11, 1), date(2026, 12, 25)}
    assert cfg.unterrichtsfrei_set == {date(2026, 10, 2)}
    assert is_schoolday(date(2026, 12, 25), cfg) is False
    assert is_schoolday(date(2026, 10, 2), cfg) is False


def test_namedday_coerces_iso_string():
    """YAML kann ein Datum als String liefern; NamedDay muss es akzeptieren."""
    day = NamedDay.model_validate("2026-10-03")
    assert day.datum == date(2026, 10, 3)
    assert day.name is None


def test_validation_ferien_outside():
    with pytest.raises(ValueError, match="außerhalb"):
        SchoolYearConfig(
            schuljahr="2026/27",
            beginn=date(2026, 9, 14),
            ende=date(2027, 7, 28),
            halbjahreswechsel=date(2027, 2, 8),
            ferien=[FerienPeriod(name="Zu früh", von=date(2026, 8, 1), bis=date(2026, 8, 5))],
        )


# ── A-/B-Wochen ──────────────────────────────────────────────────────────────


def _jahr(ab_zaehlung: str, ferien: list[FerienPeriod]) -> SchoolYearConfig:
    """Schuljahr ab Montag, 14.09.2026 — ohne Feiertage, damit nur die Ferien wirken."""
    return SchoolYearConfig(
        schuljahr="2026/27",
        beginn=date(2026, 9, 14),
        ende=date(2027, 7, 28),
        halbjahreswechsel=date(2027, 2, 8),
        ferien=ferien,
        ab_zaehlung=ab_zaehlung,
    )


EINE_WOCHE = [FerienPeriod(name="Herbst", von=date(2026, 10, 26), bis=date(2026, 10, 30))]
ZWEI_WOCHEN = [FerienPeriod(name="Herbst", von=date(2026, 10, 26), bis=date(2026, 11, 6))]
ZWEI_WOCHEN_SPAETER = [
    FerienPeriod(name="Weihnachten", von=date(2026, 12, 21), bis=date(2027, 1, 1))
]


def test_erste_unterrichtswoche_ist_phase_null():
    """Der Nullpunkt, den beide Seiten teilen — ohne konfiguriertes Ankerdatum."""
    for regel in ("unterrichtswoche", "kalenderwoche"):
        phasen = ab_phasen(_jahr(regel, EINE_WOCHE))
        assert phasen[date(2026, 9, 14)] == 0
        assert phasen[date(2026, 9, 21)] == 1


def test_ferienwoche_bekommt_keine_phase():
    """Sie ist keine Unterrichtswoche — ein Slot kann dort nicht liegen."""
    phasen = ab_phasen(_jahr("unterrichtswoche", EINE_WOCHE))
    assert date(2026, 10, 26) not in phasen


def test_unterrichtswochen_zaehlen_ueber_eine_einwoechige_luecke_hinweg():
    """Die Beobachtung am GGD: vor den einwöchigen Herbstferien B, danach A."""
    phasen = ab_phasen(_jahr("unterrichtswoche", EINE_WOCHE))
    assert phasen[date(2026, 10, 19)] == 1
    assert phasen[date(2026, 11, 2)] == 0


def test_kalenderwochen_zaehlen_die_ferienwoche_mit():
    """Dieselbe Lücke, andere Regel: vor den Ferien B — und danach wieder B."""
    phasen = ab_phasen(_jahr("kalenderwoche", EINE_WOCHE))
    assert phasen[date(2026, 10, 19)] == 1
    assert phasen[date(2026, 11, 2)] == 1


def test_bei_gerader_ferienlaenge_sind_beide_regeln_gleich():
    """Deshalb fällt der Unterschied so selten auf — und dann umso teurer."""
    nach_ferien = date(2026, 11, 9)
    uw = ab_phasen(_jahr("unterrichtswoche", ZWEI_WOCHEN))
    kw = ab_phasen(_jahr("kalenderwoche", ZWEI_WOCHEN))
    assert uw[nach_ferien] == kw[nach_ferien]


def test_vorgabe_ist_die_unterrichtswoche():
    """Bestehende Dateien ohne das Feld laufen weiter — mit der Zählweise des GGD."""
    cfg = SchoolYearConfig(
        schuljahr="2026/27",
        beginn=date(2026, 9, 14),
        ende=date(2027, 7, 28),
        halbjahreswechsel=date(2027, 2, 8),
    )
    assert cfg.ab_zaehlung == "unterrichtswoche"


def test_unbekannte_zaehlweise_wird_abgelehnt():
    """Ein Tippfehler darf nicht als „dann eben die Vorgabe" durchgehen — die Stunden
    lägen danach eine Woche daneben, ohne dass irgendwo etwas meldet."""
    with pytest.raises(ValueError):
        SchoolYearConfig(
            schuljahr="2026/27",
            beginn=date(2026, 9, 14),
            ende=date(2027, 7, 28),
            halbjahreswechsel=date(2027, 2, 8),
            ab_zaehlung="unterrichtswochen",
        )


def test_unterrichtswochen_wechseln_das_ganze_schuljahr_hindurch():
    """Zwei aufeinanderfolgende Unterrichtswochen haben nie dieselbe Phase.

    Das ist genau das, was „Unterrichtswoche" bedeutet: Ein 14-tägiger Termin fällt in
    jede zweite Unterrichtswoche, egal wie viele Ferien dazwischenliegen. Die Zählweise
    `kalenderwoche` hat diese Eigenschaft bewusst **nicht** — dort teilen sich nach einer
    ungeraden Lücke zwei aufeinanderfolgende Unterrichtswochen eine Phase.
    """
    phasen = ab_phasen(_jahr("unterrichtswoche", EINE_WOCHE + ZWEI_WOCHEN_SPAETER))
    wochen = sorted(phasen)
    assert len(wochen) > 30
    for vorher, nachher in zip(wochen, wochen[1:]):
        assert phasen[vorher] != phasen[nachher], f"{vorher} → {nachher}"


# ── Schultage nach A-/B-Woche ────────────────────────────────────────────────


def _jahr_mit_feiertag() -> SchoolYearConfig:
    """Wie `_jahr`, aber mit einem Feiertag am Montag, 05.10.2026 (3. Unterrichtswoche)."""
    return SchoolYearConfig(
        schuljahr="2026/27",
        beginn=date(2026, 9, 14),
        ende=date(2027, 7, 28),
        halbjahreswechsel=date(2027, 2, 8),
        ferien=EINE_WOCHE,
        feiertage=[NamedDay(name="Testfeiertag", datum=date(2026, 10, 5))],
    )


def test_feiertag_erscheint_in_keiner_der_beiden_listen():
    """Ein Feiertag nimmt einen **einzelnen** Termin heraus, ohne die Woche zu berühren.

    Genau deshalb liefert die Funktion Tage und nicht Wochenanfänge: Aus einem Wochenanfang
    ließe sich der ausgefallene Montag nicht ablesen, und die Oberfläche verspräche einen
    Termin, den der Generator nicht anlegt.
    """
    a_woche, b_woche = ab_schultage(1, _jahr_mit_feiertag())
    assert date(2026, 10, 5) not in a_woche
    assert date(2026, 10, 5) not in b_woche
    # Die übrige Woche steht weiterhin drin.
    assert date(2026, 10, 6) in a_woche + b_woche


def test_ferien_und_wochenenden_erscheinen_nicht():
    a_woche, b_woche = ab_schultage(1, _jahr("unterrichtswoche", EINE_WOCHE))
    alle = set(a_woche + b_woche)
    assert date(2026, 10, 26) not in alle          # Ferienmontag
    assert not any(t.weekday() >= 5 for t in alle)  # Samstag/Sonntag


def test_die_beiden_listen_sind_disjunkt_und_vollstaendig():
    """Jeder Schultag des Halbjahres gehört zu genau einer der beiden Wochen."""
    cfg = _jahr("unterrichtswoche", EINE_WOCHE)
    a_woche, b_woche = ab_schultage(1, cfg)
    assert not set(a_woche) & set(b_woche)
    start, ende = halbjahr_bounds(1, cfg)
    erwartet = {
        start + timedelta(days=n)
        for n in range((ende - start).days + 1)
        if is_schoolday(start + timedelta(days=n), cfg)
    }
    assert set(a_woche + b_woche) == erwartet


def test_tage_einer_woche_liegen_in_derselben_liste():
    """Die Phase gilt für die Woche, nicht für den Tag — sonst zerfiele ein Muster."""
    a_woche, _ = ab_schultage(1, _jahr("unterrichtswoche", EINE_WOCHE))
    erste_woche = [t for t in a_woche if date(2026, 9, 14) <= t <= date(2026, 9, 18)]
    assert len(erste_woche) == 5
