"""Gespeichertes Format von `begriffe` und `fachmethoden` am Curriculum-Eintrag (0.44, AQ)."""
from app.context.curriculum_begriffe import (
    NAME_LAENGE, NAMEN_JE_EINTRAG, eintrag_felder, namen_normalisieren,
)


def test_texte_und_objekte():
    assert namen_normalisieren(["Oxidation", {"name": "Reduktion", "fassung": " Elektronen "}]) == [
        {"name": "Oxidation"}, {"name": "Reduktion", "fassung": "Elektronen"}]


def test_leerraum_leere_und_unbrauchbares():
    assert namen_normalisieren(["  Redox   reihe ", "", "   ", None, 3, {"fassung": "x"}, {"name": ""}]) == [
        {"name": "Redox reihe"}]
    assert namen_normalisieren("Oxidation") == []
    assert namen_normalisieren(None) == []


def test_dubletten_nach_schluessel_und_fassung():
    """Groß-/Kleinschreibung und Bindestrich-Varianten sind derselbe Name; eine Fassung macht ihn neu."""
    roh = ["Arenium-Ion", "arenium‑ion", {"name": "Arenium-Ion", "fassung": "A"}, {"name": "Arenium-Ion", "fassung": "a"}]
    assert namen_normalisieren(roh) == [{"name": "Arenium-Ion"}, {"name": "Arenium-Ion", "fassung": "A"}]


def test_fassung_bei_fachmethoden_faellt_weg():
    assert namen_normalisieren([{"name": "Titration", "fassung": "x"}], mit_fassung=False) == [{"name": "Titration"}]


def test_grenzen():
    assert len(namen_normalisieren([f"B{i}" for i in range(NAMEN_JE_EINTRAG + 10)])) == NAMEN_JE_EINTRAG
    (lang,) = namen_normalisieren(["x" * (NAME_LAENGE + 50)])
    assert len(lang["name"]) == NAME_LAENGE


def test_eintrag_felder_nur_was_belegt_ist():
    assert eintrag_felder([], None) == {}
    assert eintrag_felder(["A"], []) == {"begriffe": [{"name": "A"}]}
    assert eintrag_felder(None, ["M"]) == {"fachmethoden": [{"name": "M"}]}
