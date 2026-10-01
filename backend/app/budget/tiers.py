import logging
import yaml
from pathlib import Path
from typing import Optional

from app.config import settings
from app.core.paths import aufloesen

logger = logging.getLogger(__name__)

# Modul-Level-Cache für die geladenen Budget-Tiers
_budget_tiers_cache: Optional[dict] = None

#: Wie viele Wochenbeträge die Obergrenze dem Verbrauch vorauseilen darf.
#: Deckt Ferien (2 Wochen) plus eine dichte Klassenarbeitsphase; größer wäre auch die
#: Menge, die an einem Nachmittag verbraucht werden kann.
VORSPRUNG_WOCHEN_DEFAULT = 3

#: 1 Einheit = 1/10 000 € = ein Hundertstelcent. Siehe einheiten_je_euro().
EINHEITEN_JE_EURO_DEFAULT = 10_000




def _load_budget_tiers() -> dict:
    """Lädt die budget_tiers.yaml einmalig beim ersten Aufruf."""
    global _budget_tiers_cache
    if _budget_tiers_cache is not None:
        return _budget_tiers_cache
    
    config_path = aufloesen(settings.budget_tiers_path)
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


def einheiten_je_euro() -> int:
    """Wie viele **Einheiten** ein Euro sind. Vorgabe 10 000 — ein Hundertstelcent.

    **Warum es diese Einheit gibt.** Ein Euro ist für den Gegenstand zu grob: Eine
    Nachricht kostet rund 0,0007 € (gemessen 29.09.2026 an der medianen
    Nachrichtengröße). Die Anzeige wich deshalb unter einem Cent auf „< 0,01 €" aus —
    und **97,7 % aller erfassten Nachrichten zeigten denselben Text**. Eine Angabe, die
    0,001 € nicht von 0,009 € unterscheidet, ist keine Auskunft.

    **Warum 10 000 und nicht 1 000.** Bei 1 000 lägen die meistgenutzten Modelle
    *unter* einer Einheit (`chat-schnell` 0,43, `chat-standard` 0,75) — derselbe Fehler,
    eine Kommastelle weiter rechts. Bei 10 000 kostet eine normale Nachricht 4–8
    Einheiten, ein Wochenbudget liegt bei 400–3 100. Größer wäre unleserlich: Die
    Spreizung zwischen günstigstem und teuerstem Modell beträgt heute 81-fach.

    **Warum konfigurierbar.** Werden Modelle deutlich billiger, rutscht die Skala nach
    unten. Weil der Faktor hier steht und **nie gespeichert wird** (gerechnet wird in
    USD, die Einheit ist reine Anzeige), ist das Nachziehen eine Zeile — und verfälscht
    keine alten Zahlen. `scripts/check_litellm_config.py` meldet, wenn es so weit ist.
    """
    wert = _load_budget_tiers().get("einheiten_je_euro", EINHEITEN_JE_EURO_DEFAULT)
    try:
        zahl = int(wert)
    except (TypeError, ValueError):
        logger.warning(
            "einheiten_je_euro=%r unbrauchbar, nutze %d", wert, EINHEITEN_JE_EURO_DEFAULT
        )
        return EINHEITEN_JE_EURO_DEFAULT
    if zahl < 1:
        logger.warning(
            "einheiten_je_euro=%r muss mindestens 1 sein, nutze %d",
            wert, EINHEITEN_JE_EURO_DEFAULT,
        )
        return EINHEITEN_JE_EURO_DEFAULT
    return zahl


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
