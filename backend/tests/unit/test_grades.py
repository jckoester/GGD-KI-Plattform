"""Unit-Tests für app.context.grades (Jahrgangs-/Stufenband-Parser)."""

import pytest

from app.context.grades import parse_class_grade, parse_grade_band


@pytest.mark.parametrize(
    "value,expected",
    [
        ("8", (8, 8)),
        ("5/6", (5, 6)),
        ("7/8/9/10", (7, 10)),
        ("5-6", (5, 6)),
        ("5–6", (5, 6)),  # Gedankenstrich
        (" 5 / 6 ", (5, 6)),
        ("", (None, None)),
        (None, (None, None)),
        ("EF", (None, None)),  # keine Ziffer → kein Band
    ],
)
def test_parse_grade_band(value, expected):
    assert parse_grade_band(value) == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("8a", 8),
        ("10C", 10),
        ("5b", 5),
        ("EF", None),
        ("Q1", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_class_grade(name, expected):
    assert parse_class_grade(name) == expected
