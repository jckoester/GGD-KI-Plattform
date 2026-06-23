"""Unit-Tests für app.pii.scanner (Phase 14, Schritt 2).

Schwerpunkt: False-Positive-Disziplin (Themen-Nennungen warnen NICHT) und Abdeckung
der warn-würdigen Fälle (Name via Cue/Vollname, Wohnort via Adresse/Wohn-Cue).
Lädt das spaCy-Modell (de_core_news_md muss in der venv installiert sein).
"""

import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.pii.scanner import scan


def _cats(text):
    return {s.category for s in scan(text)}


# ── MUST NOT WARN: Themen-/Sach-Nennungen (Präzision) ───────────────────────

@pytest.mark.parametrize("text", [
    "Erklär mir die Photosynthese in einfachen Worten.",
    "Wie löse ich quadratische Gleichungen mit der pq-Formel?",
    "Die Hauptstadt von Frankreich ist Paris.",            # Ort als Faktum
    "Goethe hat den Faust geschrieben.",                   # einzelner Eigenname
    "Frankfurt am Main ist eine wichtige Finanzstadt.",    # Ort als Thema
    "Im Schwarzwald gibt es viele Wanderwege.",            # Region als Thema
    "schreib mir ein gedicht über den herbst",
    "Was ist der Unterschied zwischen Akkusativ und Dativ?",
    "Nenne drei Sehenswürdigkeiten in Berlin.",            # Ort als Thema, kein Wohn-Cue
    "Wie funktioniert ein Verbrennungsmotor?",
    "Fasse das Buch Die Welle kurz zusammen.",
    "Wer hat den Zweiten Weltkrieg begonnen?",
    "Welche Mannschaft hat 2014 die Weltmeisterschaft gewonnen?",
])
def test_must_not_warn(text):
    assert scan(text) == [], f"Fehlwarnung bei: {text!r}"


# ── MUST WARN: Name ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "Ich heiße Lena Hoffmann und brauche Hilfe in Mathe.",  # Cue + Vollname
    "Mein Name ist Jonas und ich bin in der 8b.",           # Cue
    "mein kumpel tim versteht das auch nicht",              # Cue, kleingeschrieben
    "ich heiße sophie müller",                              # Cue, kleingeschrieben
    "Schreib einen Steckbrief über meine Schwester Marie Becker.",  # Beziehungs-Cue
    "ich bin der lukas aus der 7a",                        # Selbst-Cue, kleingeschrieben
    "Kannst du meinem Freund Paul Weber helfen?",          # Beziehungs-Cue + Vollname
])
def test_must_warn_name(text):
    assert "name" in _cats(text), f"Name nicht erkannt: {text!r}"


# ── MUST WARN: Wohnort ──────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "Ich wohne in der Lindenstraße 4 in Reutlingen.",   # Adresse (Straße+Nr.)
    "Meine Adresse ist Am Bach 12, 72760 Reutlingen.",  # PLZ + Ort
    "Wir ziehen nächsten Monat nach Kornwestheim um.",  # Wohn-Cue + LOC
    "ich komme aus tübingen",                           # Wohn-Cue + LOC klein
    "Ich wohne in München.",                            # Wohn-Cue + LOC
    "Wir sind letztes Jahr nach Stuttgart gezogen.",    # Umzugs-Cue getrennt + LOC
])
def test_must_warn_wohnort(text):
    assert "wohnort" in _cats(text), f"Wohnort nicht erkannt: {text!r}"


# ── Kombiniert + Span-Ebene ─────────────────────────────────────────────────

def test_name_and_wohnort_combined():
    cats = _cats("Schreibe eine Bewerbung für Lisa Schneider, wohnhaft in Heilbronn.")
    assert "name" in cats and "wohnort" in cats


def test_name_span_points_at_name():
    spans = scan("Ich heiße Lena Hoffmann.")
    name_spans = [s for s in spans if s.category == "name"]
    assert name_spans
    assert "Lena" in " ".join(s.text for s in name_spans)


def test_address_span_is_wohnort():
    spans = scan("Meine Adresse ist Am Bach 12, 72760 Reutlingen.")
    assert any(s.category == "wohnort" and "Reutlingen" in s.text for s in spans)


# ── D-C: strukturierte PII NICHT serverseitig (client-seitig, Schritt 4) ────

@pytest.mark.parametrize("text", [
    "Meine Telefonnummer ist 0151 23456789.",
    "Erreichbar unter info@beispielschule.de",
])
def test_structured_pii_not_flagged_here(text):
    assert scan(text) == [], f"Strukturierte PII gehört nicht in den Endpoint: {text!r}"


# ── Bewusst akzeptiertes Restrisiko (D-B): Vollname = Warnung ───────────────

def test_known_fullname_warns_even_for_public_figure():
    # Dokumentiert die D-B-Abwägung: ein Vor+Nachname warnt — auch "Angela Merkel".
    # Bewusst akzeptiert (selten in Schüler-Prompts; wegklickbarer Nudge).
    assert "name" in _cats("Vergleiche Angela Merkel und Helmut Kohl als Kanzler.")
