"""
Tests für app.budget.tiers - get_budget_for und invalidate_budget_tiers_cache
"""
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")
os.environ.setdefault("BUDGET_TIERS_PATH", "config/budget_tiers.yaml")

from app.budget.tiers import get_budget_for, invalidate_budget_tiers_cache, _budget_tiers_cache


# Test-YAML-Konfiguration
_TEST_CONFIG = {
    "roles": {
        "teacher": {
            "max_budget_eur": 5.00,
            "budget_duration": "1mo"
        }
    },
    "grades": {
        5: {"max_budget_eur": 1.00, "budget_duration": "1mo"},
        10: {"max_budget_eur": 2.00, "budget_duration": "1mo"},
        11: {"max_budget_eur": 3.00, "budget_duration": "1mo"},
    }
}


def _with_tiers(cfg: dict):
    """Hilfsfunktion: patcht _load_budget_tiers mit einem Dict-Literal"""
    def load_mock():
        return cfg
    return patch("app.budget.tiers._load_budget_tiers", side_effect=load_mock)


# ========== get_budget_for Tests ==========


def test_student_gets_correct_grade_budget():
    """Eingabe: roles=["student"], grade=10 → Erwartet: (2.00, "1mo")"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["student"], 10)
        assert result == (2.00, "1mo")


def test_student_unknown_grade_falls_back_to_lowest():
    """Eingabe: roles=["student"], grade=99 → Erwartet: Budget des niedrigsten konfigurierten Jahrgangs (5)"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["student"], 99)
        assert result == (1.00, "1mo")


def test_student_grade_none_falls_back_to_lowest():
    """Eingabe: roles=["student"], grade=None → Erwartet: Fallback-Budget"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["student"], None)
        assert result == (1.00, "1mo")


def test_teacher_gets_teacher_budget():
    """Eingabe: roles=["teacher"], grade=None → Erwartet: Lehrer-Budget"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["teacher"], None)
        assert result == (5.00, "1mo")


def test_teacher_admin_combination_gets_teacher_budget():
    """Eingabe: roles=["teacher", "admin"], grade=None → Erwartet: Lehrer-Budget (teacher hat Vorrang)"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["teacher", "admin"], None)
        assert result == (5.00, "1mo")


def test_unknown_role_falls_back_to_lowest_grade():
    """Eingabe: roles=["review"], grade=None → Erwartet: Fallback-Budget (kein Hard-Fail)"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["review"], None)
        assert result == (1.00, "1mo")


def test_grade_as_string_is_normalised():
    """Eingabe: roles=["student"], grade="10" (String statt Int) → Erwartet: (2.00, "1mo")"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["student"], "10")
        assert result == (2.00, "1mo")


def test_empty_grades_config_uses_last_fallback():
    """Leere grades-Konfiguration → Fallback auf (1.00, "1mo")"""
    config = {"roles": {"teacher": {"max_budget_eur": 5.00}}, "grades": {}}
    with _with_tiers(config):
        result = get_budget_for(["student"], 10)
        assert result == (1.00, "1mo")


def test_teacher_with_grade_still_gets_teacher_budget():
    """Lehrer mit Jahrgang bekommt trotzdem Lehrer-Budget"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["teacher"], 10)
        assert result == (5.00, "1mo")


def test_budget_duration_fallback():
    """Fehlende budget_duration wird auf "1mo" gesetzt"""
    config = {
        "roles": {"teacher": {"max_budget_eur": 5.00}},
        "grades": {10: {"max_budget_eur": 2.00}}
    }
    with _with_tiers(config):
        result = get_budget_for(["student"], 10)
        assert result == (2.00, "1mo")


# ========== invalidate_budget_tiers_cache Tests ==========


def test_invalidate_cache_clears_cached_config():
    """Testet, dass invalidate_budget_tiers_cache den Cache löscht"""
    import app.budget.tiers as tiers_module
    
    # Starte mit gefülltem Cache
    old_config = {"grades": {10: {"max_budget_eur": 1.00, "budget_duration": "1mo"}}}
    tiers_module._budget_tiers_cache = old_config
    
    # Invalidate
    invalidate_budget_tiers_cache()
    
    # Cache sollte jetzt None sein
    assert tiers_module._budget_tiers_cache is None


def test_get_budget_for_uses_cache():
    """Testet, dass get_budget_for den Cache verwendet"""
    import app.budget.tiers as tiers_module
    
    # Cache mit Test-Konfig füllen
    test_config = {
        "grades": {10: {"max_budget_eur": 2.50, "budget_duration": "1mo"}},
        "roles": {}
    }
    tiers_module._budget_tiers_cache = test_config
    
    # get_budget_for sollte den Cache verwenden
    result = get_budget_for(["student"], 10)
    assert result == (2.50, "1mo")


def test_get_budget_for_refills_cache_after_invalidation():
    """Testet, dass nach Cache-Invalidation neues Laden funktioniert"""
    import app.budget.tiers as tiers_module
    
    # Cache mit alter Config füllen
    old_config = {"grades": {10: {"max_budget_eur": 1.00, "budget_duration": "1mo"}}}
    tiers_module._budget_tiers_cache = old_config
    
    # Invalidate
    invalidate_budget_tiers_cache()
    
    # Neue Config über Patch - hier muss die Funktion auch den Cache setzen
    new_config = {"grades": {10: {"max_budget_eur": 3.00, "budget_duration": "1mo"}}}
    
    def mock_load():
        tiers_module._budget_tiers_cache = new_config
        return new_config
    
    with patch("app.budget.tiers._load_budget_tiers", side_effect=mock_load):
        result = get_budget_for(["student"], 10)
        assert result == (3.00, "1mo")
        assert tiers_module._budget_tiers_cache == new_config
