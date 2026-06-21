"""Tests für app.crisis.detector.

Schwerpunkt: ein Treffer je Kategorie + **False-Positive-Disziplin** auf harmlosem
Schultext, dazu Normalisierung, Severity-Vorrang und YAML-Reihenfolge-Tie-Break.
"""

import os
import unicodedata

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.crisis.config import invalidate_crisis_cache
from app.crisis.detector import CrisisHit, scan


@pytest.fixture(autouse=True)
def _clear_cache():
    invalidate_crisis_cache()
    yield
    invalidate_crisis_cache()


# ========== Positivfälle je Kategorie ==========


@pytest.mark.parametrize(
    "text, category, severity",
    [
        ("Ich will mich umbringen.", "suizidalitaet", "alert"),
        ("Ich möchte nicht mehr leben.", "suizidalitaet", "alert"),
        ("Manchmal möchte ich nicht mehr leben.", "suizidalitaet", "alert"),
        ("Ich will einfach nicht mehr leben.", "suizidalitaet", "alert"),
        ("Ich ritze mich.", "selbstverletzung", "alert"),
        ("Mein Vater schlägt mich.", "haeusliche_gewalt", "alert"),
        ("Ich bin zu dick.", "essverhalten", "warning"),
        ("Niemand mag mich in der Klasse.", "mobbing", "warning"),
    ],
)
def test_scan_detects_category(text, category, severity):
    hit = scan(text)
    assert isinstance(hit, CrisisHit)
    assert hit.category == category
    assert hit.severity == severity
    assert hit.help_topic  # nicht leer
    assert hit.trigger_rule == f"crisis_triggers:{category}"
    assert hit.coreviewer_role == "review"


# ========== False-Positive-Disziplin auf harmlosem Schultext ==========


@pytest.mark.parametrize(
    "text",
    [
        "Wie löse ich diese quadratische Gleichung?",
        "Kannst du mir den Zweiten Weltkrieg erklären?",
        "Ich schreibe morgen eine Klassenarbeit in Mathe.",
        "Erkläre mir bitte die Photosynthese.",
        "Ich finde die Englisch-Vokabeln schwer.",
        "Gib mir Tipps für ein gesundes Frühstück.",
    ],
)
def test_scan_ignores_benign_text(text):
    assert scan(text) is None


# ========== Leereingaben ==========


def test_scan_empty_returns_none():
    assert scan("") is None
    assert scan("   ") is None


# ========== Normalisierung (Case + Unicode) ==========


def test_scan_is_case_insensitive():
    hit = scan("ICH WILL MICH UMBRINGEN")
    assert hit is not None
    assert hit.category == "suizidalitaet"


def test_scan_normalizes_decomposed_umlaut():
    # Zerlegungsform (NFD: u + kombinierendes Trema) zur Laufzeit erzeugen;
    # NFKC im Detektor muss sie an die komponierte Pattern-Form angleichen.
    decomposed = unicodedata.normalize("NFD", "Alle lachen über mich.")
    assert decomposed != "Alle lachen über mich."  # wirklich zerlegt
    hit = scan(decomposed)
    assert hit is not None
    assert hit.category == "mobbing"


# ========== Severity-Vorrang & Tie-Break ==========


def test_highest_severity_wins():
    # essverhalten (warning) + suizidalitaet (alert) → alert gewinnt
    hit = scan("Ich bin zu dick und will mich umbringen.")
    assert hit is not None
    assert hit.category == "suizidalitaet"
    assert hit.severity == "alert"


def test_tie_break_follows_yaml_order():
    # selbstverletzung + suizidalitaet sind beide alert;
    # suizidalitaet steht in der YAML zuerst → gewinnt bei Gleichstand
    hit = scan("Ich ritze mich und will sterben.")
    assert hit is not None
    assert hit.category == "suizidalitaet"
