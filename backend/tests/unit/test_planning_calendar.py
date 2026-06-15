"""Unit-Tests für app.planning.calendar."""

from datetime import date, timedelta

import pytest

from app.planning.calendar import (
    FerienPeriod,
    NamedDay,
    SchoolYearConfig,
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
