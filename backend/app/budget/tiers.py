import logging
import yaml
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Modul-Level-Cache für die geladenen Budget-Tiers
_budget_tiers_cache: Optional[dict] = None


def _load_budget_tiers() -> dict:
    """Lädt die budget_tiers.yaml einmalig beim ersten Aufruf."""
    global _budget_tiers_cache
    if _budget_tiers_cache is not None:
        return _budget_tiers_cache
    
    config_path = Path(settings.budget_tiers_path)
    if not config_path.exists():
        logger.error("budget_tiers.yaml nicht gefunden unter %s", config_path)
        raise FileNotFoundError(f"budget_tiers.yaml nicht gefunden: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        _budget_tiers_cache = yaml.safe_load(f) or {}
    
    logger.info("Budget-Tiers geladen von %s", config_path)
    return _budget_tiers_cache


def invalidate_budget_tiers_cache() -> None:
    """Invalidiert den Cache für Budget-Tiers. Wird nach YAML-Änderungen aufgerufen."""
    global _budget_tiers_cache
    _budget_tiers_cache = None


def get_budget_for(roles: list[str], grade: Optional[int]) -> tuple[Optional[float], str]:
    """
    Gibt (max_budget_eur, budget_duration) zurück.
    
    Logik:
    - Wenn "teacher" in roles → Lehrer-Budget (gilt auch für teacher+admin)
    - Wenn "student" in roles → Budget aus grades-Dict anhand grade
    - Keine Rolle erkannt → niedrigstes Budget als sicherer Fallback
    """
    config = _load_budget_tiers()

    # grade kann als String ankommen (z.B. aus SSO-Claims) — normalisieren
    if grade is not None:
        try:
            grade = int(grade)
        except (ValueError, TypeError):
            grade = None

    # Lehrer (inkl. teacher+admin, teacher+budget, etc.)
    if "teacher" in roles:
        teacher_config = config.get("roles", {}).get("teacher", {})
        max_budget = teacher_config.get("max_budget_eur")
        duration = teacher_config.get("budget_duration", "1mo")
        return (max_budget, duration)

    # Schüler - direkte Grade-Lookup
    if "student" in roles and grade is not None:
        grade_config = config.get("grades", {}).get(grade)
        if grade_config:
            return (grade_config.get("max_budget_eur"), grade_config.get("budget_duration", "1mo"))
        
        # Fallback: niedrigstes konfiguriertes Jahrgangsbudget
        grades = config.get("grades", {})
        if grades:
            lowest = grades[min(grades.keys())]
            logger.warning(
                "Kein Budget für grade=%s, Fallback auf Jahrgang %s",
                grade, min(grades.keys())
            )
            return (lowest.get("max_budget_eur"), lowest.get("budget_duration", "1mo"))

    # Fallback: niedrigstes Budget aus grades
    grades = config.get("grades", {})
    if grades:
        lowest = grades[min(grades.keys())]
        logger.warning("Keine bekannte Rolle in %s. Verwende Fallback-Jahrgang: %s", roles, min(grades.keys()))
        return (lowest.get("max_budget_eur"), lowest.get("budget_duration", "1mo"))

    # Letzter Fallback
    logger.error("Kein Budget ermittelbar für roles=%s grade=%s", roles, grade)
    return (1.00, "1mo")
