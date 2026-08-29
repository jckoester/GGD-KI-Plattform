import logging
import yaml
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Modul-Level-Cache für die geladenen Budget-Tiers
_budget_tiers_cache: Optional[dict] = None

#: Wie viele Wochenbeträge die Obergrenze dem Verbrauch vorauseilen darf.
#: Deckt Ferien (2 Wochen) plus eine dichte Klassenarbeitsphase; größer wäre auch die
#: Menge, die an einem Nachmittag verbraucht werden kann.
VORSPRUNG_WOCHEN_DEFAULT = 3




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


def vorsprung_wochen() -> int:
    """Erlaubter Vorsprung der Obergrenze vor dem Verbrauch, in Wochenbeträgen."""
    wert = _load_budget_tiers().get("vorsprung_wochen", VORSPRUNG_WOCHEN_DEFAULT)
    try:
        return max(1, int(wert))
    except (TypeError, ValueError):
        logger.warning("vorsprung_wochen=%r unbrauchbar, nutze %d", wert, VORSPRUNG_WOCHEN_DEFAULT)
        return VORSPRUNG_WOCHEN_DEFAULT


def _stufe(eintrag: dict) -> Optional[float]:
    """Wochenbetrag einer Stufe.

    ``max_budget_eur`` + ``budget_duration`` war bis 08/2026 das Monatsmodell und wird
    **nicht mehr gelesen** — der Umstieg war ein harter Schnitt (Sommerferien, ein
    Produktivsystem). Wer eine alte Datei mitschleppt, bekommt hier ``None`` und im Log
    die Aufforderung, sie umzustellen; stillschweigend als Wochenbetrag zu deuten wäre
    eine Kürzung auf etwa ein Viertel.
    """
    betrag = eintrag.get("wochenbudget_eur")
    if betrag is None and eintrag.get("max_budget_eur") is not None:
        logger.error(
            "budget_tiers.yaml führt noch `max_budget_eur` (Monatsmodell, entfallen 08/2026). "
            "Auf `wochenbudget_eur` umstellen — Vorlage: config/budget_tiers.example.yaml."
        )
    return betrag


def get_budget_for(roles: list[str], grade: Optional[int]) -> Optional[float]:
    """
    Gibt den Wochenbetrag in Euro zurück (``None``, wenn keiner ermittelbar ist).

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
        return _stufe(config.get("roles", {}).get("teacher", {}))

    # Schüler - direkte Grade-Lookup
    if "student" in roles and grade is not None:
        grade_config = config.get("grades", {}).get(grade)
        if grade_config:
            return _stufe(grade_config)

        # Fallback: niedrigstes konfiguriertes Jahrgangsbudget
        grades = config.get("grades", {})
        if grades:
            logger.warning(
                "Kein Budget für grade=%s, Fallback auf Jahrgang %s",
                grade, min(grades.keys())
            )
            return _stufe(grades[min(grades.keys())])

    # Fallback: niedrigstes Budget aus grades
    grades = config.get("grades", {})
    if grades:
        logger.warning("Keine bekannte Rolle in %s. Verwende Fallback-Jahrgang: %s", roles, min(grades.keys()))
        return _stufe(grades[min(grades.keys())])

    # Letzter Fallback
    logger.error("Kein Budget ermittelbar für roles=%s grade=%s", roles, grade)
    return None
