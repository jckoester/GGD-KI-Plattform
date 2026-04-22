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


def get_budget_for(roles: list[str], grade: Optional[int]) -> tuple[Optional[float], str]:
    """
    Gibt (max_budget_eur, budget_duration) zurück.

    Logik:
    - Wenn "teacher" in roles → Lehrer-Budget (gilt auch für teacher+admin)
    - Wenn "student" in roles → Tier aus tiers anhand grade
    - Keine Rolle erkannt → niedrigstes Tier als sicherer Fallback
    """
    tiers_config = _load_budget_tiers()

    # grade kann als String ankommen (z.B. aus SSO-Claims) — normalisieren
    if grade is not None:
        try:
            grade = int(grade)
        except (ValueError, TypeError):
            grade = None
    
    # Lehrer (inkl. teacher+admin, teacher+budget, etc.)
    if "teacher" in roles:
        teacher_config = tiers_config.get("roles", {}).get("teacher", {})
        max_budget = teacher_config.get("max_budget_eur")
        duration = teacher_config.get("budget_duration", "1mo")
        return (max_budget, duration)
    
    # Schüler - Suche passendes Tier anhand grade
    if "student" in roles and grade is not None:
        tiers = tiers_config.get("tiers", [])
        for tier in tiers:
            if grade in tier.get("grades", []):
                return (tier.get("max_budget_eur"), tier.get("budget_duration", "1mo"))
        
        # Kein passender Tier gefunden - niedrigstes Tier als Fallback
        if tiers:
            lowest_tier = min(tiers, key=lambda t: min(t.get("grades", [999])))
            logger.warning(
                "Kein Budget-Tier für grade=%s gefunden. Verwende Fallback: %s",
                grade, lowest_tier.get("name", "unknown")
            )
            return (lowest_tier.get("max_budget_eur"), lowest_tier.get("budget_duration", "1mo"))
    
    # Fallback: niedrigstes Tier
    tiers = tiers_config.get("tiers", [])
    if tiers:
        lowest_tier = min(tiers, key=lambda t: min(t.get("grades", [999])))
        logger.warning("Keine bekannte Rolle in %s. Verwende Fallback-Tier: %s", roles, lowest_tier.get("name", "unknown"))
        return (lowest_tier.get("max_budget_eur"), lowest_tier.get("budget_duration", "1mo"))
    
    # Letzter Fallback
    logger.error("Keine Budget-Tiers konfiguriert und keine Rolle erkannt für roles=%s, grade=%s", roles, grade)
    return (1.00, "1mo")
