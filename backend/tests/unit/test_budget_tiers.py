"""
Tests für app.budget.tiers - get_budget_for und invalidate_budget_tiers_cache
"""
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")
os.environ.setdefault("BUDGET_TIERS_PATH", "config/budget_tiers.yaml")

from app.budget.tiers import get_budget_for, invalidate_budget_tiers_cache, _budget_tiers_cache


# Test-YAML-Konfiguration. Beträge je **Unterrichtswoche** — das Monatsmodell ist
# 08/2026 ersatzlos entfallen (harter Schnitt in den Sommerferien).
_TEST_CONFIG = {
    "roles": {"teacher": {"wochenbudget_eur": 5.00}},
    "grades": {
        5: {"wochenbudget_eur": 1.00},
        10: {"wochenbudget_eur": 2.00},
        11: {"wochenbudget_eur": 3.00},
    },
}


def _with_tiers(cfg: dict):
    """Hilfsfunktion: patcht _load_budget_tiers mit einem Dict-Literal"""
    def load_mock():
        return cfg
    return patch("app.budget.tiers._load_budget_tiers", side_effect=load_mock)


# ========== get_budget_for Tests ==========


def test_student_gets_correct_grade_budget():
    """Eingabe: roles=["student"], grade=10 → Erwartet: 2,00 € je Unterrichtswoche"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["student"], 10)
        assert result == 2.00


def test_student_unknown_grade_falls_back_to_lowest():
    """Eingabe: roles=["student"], grade=99 → Erwartet: Budget des niedrigsten konfigurierten Jahrgangs (5)"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["student"], 99)
        assert result == 1.00


def test_student_grade_none_falls_back_to_lowest():
    """Eingabe: roles=["student"], grade=None → Erwartet: Fallback-Budget"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["student"], None)
        assert result == 1.00


def test_teacher_gets_teacher_budget():
    """Eingabe: roles=["teacher"], grade=None → Erwartet: Lehrer-Budget"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["teacher"], None)
        assert result == 5.00


def test_teacher_admin_combination_gets_teacher_budget():
    """Eingabe: roles=["teacher", "admin"], grade=None → Erwartet: Lehrer-Budget (teacher hat Vorrang)"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["teacher", "admin"], None)
        assert result == 5.00


def test_unknown_role_falls_back_to_lowest_grade():
    """Eingabe: roles=["review"], grade=None → Erwartet: Fallback-Budget (kein Hard-Fail)"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["review"], None)
        assert result == 1.00


def test_grade_as_string_is_normalised():
    """Eingabe: roles=["student"], grade="10" (String statt Int) → Erwartet: 2,00 €"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["student"], "10")
        assert result == 2.00


def test_empty_grades_config_uses_last_fallback():
    """Leere grades-Konfiguration → kein Budget ermittelbar.

    Früher wurde hier stillschweigend 1,00 € vergeben. Ein erfundener Betrag aus einer
    leeren Konfiguration ist die schlechtere Auskunft: Er sieht nach Absicht aus.
    """
    config = {"roles": {"teacher": {"wochenbudget_eur": 5.00}}, "grades": {}}
    with _with_tiers(config):
        assert get_budget_for(["student"], 10) is None


def test_teacher_with_grade_still_gets_teacher_budget():
    """Lehrer mit Jahrgang bekommt trotzdem Lehrer-Budget"""
    with _with_tiers(_TEST_CONFIG):
        result = get_budget_for(["teacher"], 10)
        assert result == 5.00


def test_altes_monatsschema_wird_nicht_mehr_gelesen():
    """Eine nicht umgestellte Datei liefert kein Budget — und einen Fehler im Log.

    Den Monatsbetrag stillschweigend als Wochenbetrag zu deuten wäre eine Kürzung auf
    etwa ein Viertel: kein Fehler, kein Hinweis, sichtbar erst an ratlosen Nutzer:innen.
    """
    config = {
        "roles": {"teacher": {"max_budget_eur": 5.00, "budget_duration": "1mo"}},
        "grades": {10: {"max_budget_eur": 2.00, "budget_duration": "1mo"}},
    }
    with _with_tiers(config):
        assert get_budget_for(["student"], 10) is None
        assert get_budget_for(["teacher"], None) is None


# ========== invalidate_budget_tiers_cache Tests ==========


def test_invalidate_cache_clears_cached_config():
    """Testet, dass invalidate_budget_tiers_cache den Cache löscht"""
    import app.budget.tiers as tiers_module
    
    # Starte mit gefülltem Cache
    old_config = {"grades": {10: {"wochenbudget_eur": 1.00}}}
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
        "grades": {10: {"wochenbudget_eur": 2.50}},
        "roles": {}
    }
    tiers_module._budget_tiers_cache = test_config
    
    # get_budget_for sollte den Cache verwenden
    result = get_budget_for(["student"], 10)
    assert result == 2.50


def test_get_budget_for_refills_cache_after_invalidation():
    """Testet, dass nach Cache-Invalidation neues Laden funktioniert"""
    import app.budget.tiers as tiers_module
    
    # Cache mit alter Config füllen
    old_config = {"grades": {10: {"wochenbudget_eur": 1.00}}}
    tiers_module._budget_tiers_cache = old_config
    
    # Invalidate
    invalidate_budget_tiers_cache()
    
    # Neue Config über Patch - hier muss die Funktion auch den Cache setzen
    new_config = {"grades": {10: {"wochenbudget_eur": 3.00}}}
    
    def mock_load():
        tiers_module._budget_tiers_cache = new_config
        return new_config
    
    with patch("app.budget.tiers._load_budget_tiers", side_effect=mock_load):
        result = get_budget_for(["student"], 10)
        assert result == 3.00
        assert tiers_module._budget_tiers_cache == new_config


# ========== Wochenmodell ==========
#
# `wochenbudget_eur` heißt bewusst anders als `max_budget_eur`, statt dessen Bedeutung
# still von Monat auf Woche zu drehen. Wer den Code aktualisiert, die Konfiguration aber
# nicht, bekäme sonst jedes Budget lautlos auf etwa ein Viertel gekürzt.

_WOCHEN_CONFIG = {
    "vorsprung_wochen": 4,
    "roles": {"teacher": {"wochenbudget_eur": 0.30}},
    "grades": {
        5: {"wochenbudget_eur": 0.04},
        10: {"wochenbudget_eur": 0.08},
    },
}


def test_vorsprung_wochen_aus_der_konfiguration():
    from app.budget.tiers import VORSPRUNG_WOCHEN_DEFAULT, vorsprung_wochen

    with _with_tiers(_WOCHEN_CONFIG):
        assert vorsprung_wochen() == 4
    with _with_tiers(_TEST_CONFIG):
        assert vorsprung_wochen() == VORSPRUNG_WOCHEN_DEFAULT, "Default, wenn nicht gesetzt"


def test_vorsprung_wochen_faellt_bei_unsinn_auf_den_default():
    from app.budget.tiers import VORSPRUNG_WOCHEN_DEFAULT, vorsprung_wochen

    with _with_tiers({"vorsprung_wochen": "drei"}):
        assert vorsprung_wochen() == VORSPRUNG_WOCHEN_DEFAULT
    with _with_tiers({"vorsprung_wochen": 0}):
        assert vorsprung_wochen() == 1, "mindestens eine Woche Vorsprung"
