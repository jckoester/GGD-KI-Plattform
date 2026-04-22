import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.litellm.teams import (
    TEACHER_TEAM_ID,
    get_target_team_id,
    is_phase1_team,
    normalize_grade,
)


def test_normalize_grade():
    assert normalize_grade(7) == 7
    assert normalize_grade("11") == 11
    assert normalize_grade("x") is None
    assert normalize_grade(None) is None


def test_get_target_team_id_teacher_priority():
    assert get_target_team_id(["teacher"], grade=None) == TEACHER_TEAM_ID
    assert get_target_team_id(["teacher", "admin"], grade=10) == TEACHER_TEAM_ID
    assert get_target_team_id(["student", "teacher"], grade=8) == TEACHER_TEAM_ID


def test_get_target_team_id_student():
    assert get_target_team_id(["student"], grade=7) == "jahrgang-7"
    assert get_target_team_id(["student"], grade="11") == "jahrgang-11"


def test_get_target_team_id_invalid_inputs():
    with pytest.raises(ValueError):
        get_target_team_id(["student"], grade=None)
    with pytest.raises(ValueError):
        get_target_team_id(["student"], grade=4)
    with pytest.raises(ValueError):
        get_target_team_id(["student"], grade=13)
    with pytest.raises(ValueError):
        get_target_team_id(["admin"], grade=None)


def test_is_phase1_team():
    assert is_phase1_team("jahrgang-5") is True
    assert is_phase1_team("jahrgang-12") is True
    assert is_phase1_team("lehrkraefte") is True
    assert is_phase1_team("jahrgang-4") is False
    assert is_phase1_team("jahrgang-13") is False
    assert is_phase1_team("fachschaft-mathe") is False
