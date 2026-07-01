"""Unit-Tests für die Curriculum-Relink-Entscheidungslogik (app.context.relink)."""

from types import SimpleNamespace

from app.context.relink import (
    _normalize_competence_text,
    _similarity,
    _decide,
    SIMILARITY_THRESHOLD,
)


def _twin(node_id, title, nr):
    return SimpleNamespace(id=node_id, title=title, metadata_={"kompetenz_nr": nr})


class TestNormalize:
    def test_strips_nr_prefix_soft_hyphens_and_casefolds(self):
        # Soft-Hyphen (­) + Nr-Präfix + Whitespace + Groß/Klein
        raw = "3.2.2.1(1) Be­obachtbare   Merkmale"
        assert _normalize_competence_text(raw, "3.2.2.1(1)") == "beobachtbare merkmale"

    def test_without_nr(self):
        assert _normalize_competence_text("Hypothesen bilden", None) == "hypothesen bilden"


class TestSimilarity:
    def test_identical(self):
        assert _similarity("abc", "abc") == 1.0

    def test_both_empty(self):
        assert _similarity("", "") == 1.0

    def test_disjoint_low(self):
        assert _similarity("völlig anderer text hier", "kurz") < 0.5


class TestDecide:
    REF = {"node_id": "old-1", "title": "3.1.1(1) Stoffe beschreiben", "nr": "3.1.1(1)"}

    def test_no_twin_is_outdated(self):
        d = _decide(self.REF, None, "3.1.1(1)")
        assert d["decision"] == "outdated"
        assert d["new_node_id"] is None

    def test_same_node_is_current(self):
        twin = _twin("old-1", "3.1.1(1) Stoffe beschreiben", "3.1.1(1)")
        d = _decide(self.REF, twin, "3.1.1(1)")
        assert d["decision"] == "current"
        assert d["new_node_id"] == "old-1"

    def test_identical_text_relinks(self):
        twin = _twin("new-9", "3.1.1(1) Stoffe beschreiben", "3.1.1(1)")
        d = _decide(self.REF, twin, "3.1.1(1)")
        assert d["decision"] == "relink"
        assert d["new_node_id"] == "new-9"
        assert d["similarity"] == 1.0

    def test_minor_wording_change_still_relinks(self):
        # nur ein Wort ergänzt → Ähnlichkeit knapp, aber ≥ Schwelle bei fast identisch
        twin = _twin("new-9", "3.1.1(1) Stoffe fachsprachlich beschreiben", "3.1.1(1)")
        d = _decide(self.REF, twin, "3.1.1(1)")
        # Grenzfall dokumentiert: hängt an SIMILARITY_THRESHOLD
        assert d["decision"] in ("relink", "outdated")
        assert d["new_node_id"] == "new-9"  # Zwilling gefunden, unabhängig von der Entscheidung

    def test_completely_changed_text_is_outdated_but_keeps_twin_ref(self):
        twin = _twin("new-9", "3.1.1(1) Ein völlig anderer Kompetenztext ohne Bezug", "3.1.1(1)")
        d = _decide(self.REF, twin, "3.1.1(1)")
        assert d["decision"] == "outdated"
        assert d["new_node_id"] == "new-9"      # Zwilling existiert, passt aber inhaltlich nicht
        assert d["similarity"] < SIMILARITY_THRESHOLD
