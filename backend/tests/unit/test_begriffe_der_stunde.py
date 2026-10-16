"""Begriffe der Stunde (0.17, A1, Schritt 1): Vergleichstext und Vektor-Wächter.

Die Auswahl selbst prüft `tests/integration/test_begriffe_der_stunde.py` an der Datenbank.
"""
import pytest

from app.context.embedding import eingabe_ohne_aliase, vektor_veraltet
from app.db.models import ContextNode
from app.planning.assistant_tools import _BESCHREIBUNG_MAX, _vergleichstext
from app.planning.schemas import BEGRIFF_TYPEN


def _stunde(titel="Aromaten", **meta) -> ContextNode:
    return ContextNode(category="artifact", content_type="unterrichtsstunde", title=titel,
                       metadata_=meta, embedding=[0.1, 0.2])


class TestVergleichstext:
    def test_leere_stunde_ist_ihr_titel(self):
        assert _vergleichstext(_stunde("Neue Stunde"), {}, {}) == "Neue Stunde"

    def test_ohne_phasen_titel_ziel_einheit_kapitel(self):
        zusammenhang = {"einheit": {"titel": "2 Aromaten"}, "kapitel": {"titel": "Benzol und Aromaten"}}
        text = _vergleichstext(_stunde(), {"stundenziel": "Mesomerie erklären"}, zusammenhang)
        assert text.split("\n") == ["Aromaten", "Mesomerie erklären", "2 Aromaten", "Benzol und Aromaten"]

    def test_phasen_mit_gekuerzter_beschreibung(self):
        lang = "x" * (_BESCHREIBUNG_MAX + 50)
        meta = {"phasen": [{"name": "Einstieg", "beschreibung": lang}, {"name": "Sicherung"}]}
        assert _vergleichstext(_stunde(), meta, {}).split("\n") == [
            "Aromaten", "Einstieg", "x" * _BESCHREIBUNG_MAX, "Sicherung"]

    def test_unbrauchbares_fallt_weg(self):
        """Leere Felder, `null`, Nicht-Texte und Phasen, die keine Objekte sind."""
        meta = {"stundenziel": "  ", "phasen": ["kaputt", {"name": None, "beschreibung": 7}]}
        assert _vergleichstext(_stunde(), meta, {"einheit": None, "kapitel": None}) == "Aromaten"


class TestVektorVeraltet:
    def test_gleicher_text_behaelt_den_vektor(self):
        n = _stunde(refs=[{"titel": "Mesomerie"}])
        vorher = eingabe_ohne_aliase(n)
        n.metadata_ = {**n.metadata_, "phasen": [{"name": "Neu"}]}   # Phasen stehen nicht im Vektor
        assert vektor_veraltet(n, vorher) is False
        assert n.embedding == [0.1, 0.2]

    def test_neuer_begriff_verwirft_den_vektor(self):
        n = _stunde(refs=[{"titel": "Mesomerie"}])
        vorher = eingabe_ohne_aliase(n)
        n.metadata_ = {**n.metadata_, "refs": [{"titel": "Mesomerie"}, {"titel": "Benzol"}]}
        assert vektor_veraltet(n, vorher) is True
        assert n.embedding is None

    def test_ohne_substanz_kein_alter_vektor(self):
        """Alle Begriffe weg: Danach gibt es keinen Eingabetext — und keinen alten Vektor."""
        n = _stunde(refs=[{"titel": "Mesomerie"}])
        vorher = eingabe_ohne_aliase(n)
        n.metadata_ = {"refs": []}
        assert eingabe_ohne_aliase(n) is None
        assert vektor_veraltet(n, vorher) is True
        assert n.embedding is None

    def test_typ_mit_aliasen_wird_abgewiesen(self):
        methode = ContextNode(category="knowledge", content_type="methode", title="Placemat", metadata_={})
        with pytest.raises(ValueError, match="Aliase"):
            eingabe_ohne_aliase(methode)


def test_begriff_typen_sind_konzepte_mit_vektor():
    """Jeder Typ der Liste ist ein `concept` mit Vektor — sonst fände die Auswahl ihn nie."""
    from app.context.embedding import EMBEDDING_CONTENT_TYPES
    from app.context.taxonomy import CONTENT_TYPE_TO_CATEGORY

    for typ in BEGRIFF_TYPEN:
        assert CONTENT_TYPE_TO_CATEGORY[typ] == "concept"
        assert typ in EMBEDDING_CONTENT_TYPES


def test_frontend_kennt_dieselben_typen():
    """Die Leiste sucht mit ihrer eigenen Liste (`frontend/src/lib/begriffe_der_stunde.js`).
    Liefe sie auseinander, böte die Suche Knoten an, die das Werkzeug beim Schreiben abweist —
    oder verschwiege welche, die es annimmt."""
    import re
    from pathlib import Path

    js = (Path(__file__).resolve().parents[3] / "frontend/src/lib/begriffe_der_stunde.js").read_text(encoding="utf-8")
    liste = re.search(r"export const BEGRIFF_TYPEN = \[([^\]]*)\]", js)
    assert liste, "BEGRIFF_TYPEN nicht gefunden"
    assert tuple(re.findall(r"'([a-z_]+)'", liste.group(1))) == BEGRIFF_TYPEN
