"""Titelvorschlag beim Speichern (0.41, Päckchen AN, Schritt 2) — reine Regeln."""
from datetime import date

from app.artifacts import titel

HEUTE = date(2026, 11, 13)


# ── kürzen ────────────────────────────────────────────────────────────────────

def test_kurz_bleibt_wie_es_ist():
    assert titel.kuerzen("Ein roter Fuchs im Schnee") == "Ein roter Fuchs im Schnee"


def test_lang_wird_an_einer_wortgrenze_gekuerzt():
    text = "Eine detailreiche Illustration eines Wasserkreislaufs mit Verdunstung, Wolken und Regen über einem See"
    ergebnis = titel.kuerzen(text)
    assert len(ergebnis) <= titel.LAENGE
    assert ergebnis.endswith("…")
    assert not ergebnis[:-1].endswith(" ")
    assert text.startswith(ergebnis[:-1])


def test_umlaute_und_leerraum():
    assert titel.kuerzen("  Größenordnung\tder   Übergänge\n\nzweite Zeile") == "Größenordnung der Übergänge"


def test_ein_ueberlanges_wort_wird_hart_geschnitten():
    ergebnis = titel.kuerzen("x" * 200)
    assert len(ergebnis) == titel.LAENGE and ergebnis.endswith("…")


def test_leer_bleibt_leer():
    assert titel.kuerzen(None) == ""
    assert titel.kuerzen("   \n  ") == ""


def test_anfuehrungszeichen_fallen_weg():
    assert titel.kuerzen("„Ein Titel“") == "Ein Titel"


# ── Bild ──────────────────────────────────────────────────────────────────────

def test_bild_aus_dem_prompt():
    assert titel.bild("Ein Fuchs", HEUTE) == "Ein Fuchs"


def test_bild_ohne_prompt_mit_datum():
    assert titel.bild(None, HEUTE) == "Bild vom 13.11.2026"


# ── Mermaid ───────────────────────────────────────────────────────────────────

def test_mermaid_frontmatter():
    quelle = "---\ntitle: \"Stickstoffkreislauf\"\n---\nflowchart TD\n A-->B"
    assert titel.titel_aus_mermaid(quelle) == "Stickstoffkreislauf"


def test_mermaid_title_anweisung():
    assert titel.titel_aus_mermaid("gantt\n    title Projektplan\n    section A") == "Projektplan"
    assert titel.titel_aus_mermaid("pie title Anteile der Gase\n \"N2\" : 78") == "Anteile der Gase"


def test_mermaid_classdef_ist_kein_titel():
    assert titel.titel_aus_mermaid("flowchart TD\n classDef title fill:#fff\n A-->B") is None


def test_mermaid_ohne_titel():
    assert titel.titel_aus_mermaid("flowchart TD\n A-->B") is None


# ── Funktionsgraph ────────────────────────────────────────────────────────────

def test_plot_erste_funktion():
    assert titel.titel_aus_plot("functions:\n  - f(x) = x^2\n") == "Graph von f(x) = x^2"


def test_plot_mehrere_funktionen():
    assert titel.titel_aus_plot("functions:\n  - f(x) = x^2\n  - g(x) = 2*x\n") == "Graph von f(x) = x^2 u. a."


def test_plot_unlesbar():
    assert titel.titel_aus_plot("::: kein yaml") is None


# ── Diagramm: Reihenfolge ─────────────────────────────────────────────────────

def test_quelle_vor_frage():
    assert titel.diagramm("mermaid", "pie title Gase\n A: 1", "Mach ein Diagramm", HEUTE) == "Gase"


def test_frage_wenn_die_quelle_keinen_titel_hat():
    assert titel.diagramm("circuit", "\\draw", "Zwei Lampen in Reihe", HEUTE) == "Zwei Lampen in Reihe"


def test_zuletzt_art_und_datum():
    assert titel.diagramm("smiles", "CCO", None, HEUTE) == "Strukturformel vom 13.11.2026"
    assert titel.diagramm("circuit", "\\draw", "   ", HEUTE) == "Schaltplan vom 13.11.2026"
