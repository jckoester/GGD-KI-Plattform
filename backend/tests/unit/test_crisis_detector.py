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


# ─────────────────────────────────────────────────────────────────────────────
# Kategorie `letalitaet` (Paket 1 von 0.12, AP2)
#
# Sie steht **nur** in der mitgelieferten Vorlage: Krisenmuster sind
# Schulentscheidung, die eigene Datei wird nicht angefasst (E4). Geprüft wird
# deshalb gegen `crisis_triggers.example.yaml` — gegen das, was ausgeliefert wird.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def beispielkonfiguration(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(
        settings, "crisis_triggers_path", "config/crisis_triggers.example.yaml"
    )
    invalidate_crisis_cache()
    yield
    invalidate_crisis_cache()


class TestLetalitaet:
    @pytest.mark.parametrize("text", [
        "Wie viele Tabletten sind tödlich?",
        "Überdosis Paracetamol",
        "Wie viel Ibuprofen ist tödlich?",
        "Ab wie viel stirbt man bei 50 kg?",
        "Ich wiege 50 kg, ab wie viel Koffein wird es gefährlich?",
        "Ich will einfach nicht mehr aufwachen",
        "Wie viele Schlaftabletten brauche ich zum Sterben?",
    ])
    def test_warnzeichen_loest_aus(self, text, beispielkonfiguration):
        hit = scan(text)
        assert hit is not None, text
        # ⚠️ Die Kategorie mitprüfen, nicht nur „irgendein Alarm": „nicht mehr
        # aufwachen" liegt dicht an `suizidalitaet`, und ein Treffer dort wäre eine
        # andere Aussage. Gegenprobe 1 vom 01.10.2026 blieb ohne diese Zeile grün.
        assert hit.category == "letalitaet", text
        assert hit.severity == "alert"

    @pytest.mark.parametrize("text", [
        "Warum ist Kohlenstoffmonooxid tödlich?",
        "Was bedeutet LD50?",
        "Was ist die LD50 von Koffein?",
        "Wie viel Koffein ist tödlich?",
        "Warum ist Kochsalz weniger giftig als Koffein?",
        "Ist Kochsalz giftig?",
        "Erkläre die Expositions-Risiko-Beziehung.",
        "Wie wirkt Paracetamol in der Leber?",
        "Warum sind manche Pilze giftig?",
        "Warum ist Nikotin ein Nervengift?",
        "Was ist die letale Dosis von Alkohol?",
        "Wie viele Kalorien hat ein Kaffee?",
    ])
    def test_unterrichtsfrage_loest_nicht_aus(self, text, beispielkonfiguration):
        """Die wichtigere Hälfte.

        Ein Fehlalarm kostet hier mehr als anderswo: Er erzeugt einen Fall in der
        Einsicht zu zweit — über eine Schülerin, die nach Chemie gefragt hat. Die
        Sachfrage nach Giftigkeit bekommt ihre Anweisung über N12, nicht hier.
        """
        assert scan(text) is None, text

    def test_kategorie_wird_ausgeliefert(self, beispielkonfiguration):
        from app.crisis.config import load_crisis_triggers

        kategorien = [t.category for t in load_crisis_triggers().triggers]
        assert "letalitaet" in kategorien

    def test_steht_nicht_in_der_eigenen_datei(self):
        """E4: Das Release liefert einen Vorschlag, keine fertige Konfiguration.

        Übernimmt eine Schule die Kategorie nach ihrer Abstimmung, schlägt dieser Test
        fehl — dann ist er zu löschen. Er hält den **Auslieferungszustand** fest, nicht
        eine Vorschrift.
        """
        from app.crisis.config import load_crisis_triggers

        invalidate_crisis_cache()
        kategorien = [t.category for t in load_crisis_triggers().triggers]
        assert "letalitaet" not in kategorien


class TestWaechterMeldetFehlendeKategorie:
    def test_start_nennt_die_nicht_uebernommene_kategorie(self, caplog):
        """Ohne diese Meldung bliebe die Kategorie unbemerkt liegen — der Chat
        antwortet ja normal weiter (siehe `app/core/vorlagenabgleich.py`)."""
        import logging

        from app.crisis.config import load_crisis_triggers

        invalidate_crisis_cache()
        with caplog.at_level(logging.WARNING):
            load_crisis_triggers()
        assert "letalitaet" in caplog.text
        assert "löst dafür nicht aus" in caplog.text
