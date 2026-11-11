"""Unit-Tests für die PDF-Aufbereitung des Curriculum-Exports (KS-Phase-6 Schritt 5).

Reine Funktionen ohne DB/weasyprint: Volltext-Mapping und Markdown-Rendering.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.context.curriculum_export import _build_pdf_kapitel

# Der Sidecar laeuft im Unit-Test nicht; sein SVG wird gestellt.
_MATH_SVG = '<svg class="mathjax"><path d="M0"/></svg>'


def _tree_with_entry(entry: dict, ik_refs=None, pk_refs=None) -> dict:
    return {
        "kapitel": [
            {
                "title": "Kapitel 1",
                "metadata": {"std": "10"},
                "lernsequenzen": [
                    {
                        "title": "LS 1",
                        "metadata": {"std": "5", "eintraege": [entry]},
                        "ik_refs": ik_refs or [],
                        "pk_refs": pk_refs or [],
                        "leitperspektive_refs": [],
                    }
                ],
            }
        ]
    }


class TestBuildPdfKapitel:
    @pytest.mark.asyncio
    async def test_ik_pk_volltext_from_refs(self):
        """IK/PK werden über node_id auf den Knoten-Volltext (title) gemappt."""
        tree = _tree_with_entry(
            entry={
                "ik": [{"node_id": "ik1", "nr": "3.1.1", "partiell": True}],
                "pk": [{"node_id": "pk1", "pk_id": "PK_05.1"}],
            },
            ik_refs=[{"node_id": "ik1", "title": "3.1.1 Zahlen vergleichen", "nr": "3.1.1"}],
            pk_refs=[{"node_id": "pk1", "title": "2.2.1 Begründen", "pk_id": "PK_05.1"}],
        )
        e = (await _build_pdf_kapitel(tree))[0]["lernsequenzen"][0]["eintraege"][0]
        assert e["ik_items"] == [{"html": "3.1.1 Zahlen vergleichen", "partiell": True}]
        assert e["pk_items"] == [{"html": "2.2.1 Begründen"}]

    @pytest.mark.asyncio
    async def test_fallback_to_nr_and_pk_id(self):
        """Ohne passenden Ref-Titel fällt der Text auf nr bzw. pk_id zurück."""
        tree = _tree_with_entry(
            entry={
                "ik": [{"node_id": "x", "nr": "3.1.1", "partiell": False}],
                "pk": [{"node_id": "y", "pk_id": "PK_05.1"}],
            },
        )
        e = (await _build_pdf_kapitel(tree))[0]["lernsequenzen"][0]["eintraege"][0]
        assert e["ik_items"] == [{"html": "3.1.1", "partiell": False}]
        assert e["pk_items"] == [{"html": "PK_05.1"}]


class TestFormelnImPdf:
    """Bildungsplan-Kompetenzen tragen Formeln im Titel — auch im PDF.

    Die Notation ist `\\(…\\)`, nicht `$…$`. Ohne eigene Regel greift nicht nur das
    Mathe-Rendering nicht: Die CommonMark-Escape-Regel frisst den Backslash, und im PDF
    stuende `(\\pi)`.
    """

    ECHTER_TITEL = r"3.1.2(10) die Zahl \(\pi\) als Verhältnis von Umfang erklären"

    @pytest.mark.asyncio
    async def test_ik_titel_wird_zu_svg(self):
        tree = _tree_with_entry(
            entry={"ik": [{"node_id": "ik1", "nr": "3.1.2(10)", "partiell": False}]},
            ik_refs=[{"node_id": "ik1", "title": self.ECHTER_TITEL, "nr": "3.1.2(10)"}],
        )
        with patch("app.render.sidecar.render_math", new=AsyncMock(return_value=_MATH_SVG)):
            e = (await _build_pdf_kapitel(tree))[0]["lernsequenzen"][0]["eintraege"][0]
        html = e["ik_items"][0]["html"]
        assert "<svg" in html
        assert "\\(" not in html and "\\pi" not in html
        assert "als Verhältnis von Umfang erklären" in html

    @pytest.mark.asyncio
    async def test_pk_titel_ebenso(self):
        tree = _tree_with_entry(
            entry={"pk": [{"node_id": "pk1", "pk_id": "2.1.1"}]},
            pk_refs=[{"node_id": "pk1", "title": r"2.1.1 Größen \(m \cdot g\) berechnen",
                      "pk_id": "2.1.1"}],
        )
        with patch("app.render.sidecar.render_math", new=AsyncMock(return_value=_MATH_SVG)):
            e = (await _build_pdf_kapitel(tree))[0]["lernsequenzen"][0]["eintraege"][0]
        assert "<svg" in e["pk_items"][0]["html"]

    @pytest.mark.asyncio
    async def test_konkretisierung_versteht_klammer_notation(self):
        """Nicht nur die Titel — auch der Freitext des Curriculums."""
        tree = _tree_with_entry(entry={"konkretisierung": r"Fläche \(A = \pi r^2\) herleiten"})
        with patch("app.render.sidecar.render_math", new=AsyncMock(return_value=_MATH_SVG)):
            e = (await _build_pdf_kapitel(tree))[0]["lernsequenzen"][0]["eintraege"][0]
        assert "<svg" in e["konkretisierung_html"]

    @pytest.mark.asyncio
    async def test_ohne_formel_bleibt_der_titel_unveraendert(self):
        tree = _tree_with_entry(
            entry={"ik": [{"node_id": "ik1", "nr": "3.1.1", "partiell": False}]},
            ik_refs=[{"node_id": "ik1", "title": "3.1.1 Zahlen vergleichen", "nr": "3.1.1"}],
        )
        e = (await _build_pdf_kapitel(tree))[0]["lernsequenzen"][0]["eintraege"][0]
        assert e["ik_items"][0]["html"] == "3.1.1 Zahlen vergleichen"

    @pytest.mark.asyncio
    async def test_titel_ohne_fremdes_html(self):
        """Das Template gibt mit `| safe` aus — der Renderer darf kein fremdes Tag durchlassen.
        Seit 0.39 fällt es weg, statt als Text zu erscheinen (Plan F5); der Text bleibt."""
        tree = _tree_with_entry(
            entry={"ik": [{"node_id": "ik1", "nr": "x", "partiell": False}]},
            ik_refs=[{"node_id": "ik1", "title": "<script>alert(1)</script>", "nr": "x"}],
        )
        e = (await _build_pdf_kapitel(tree))[0]["lernsequenzen"][0]["eintraege"][0]
        assert "<script>" not in e["ik_items"][0]["html"]
        assert e["ik_items"][0]["html"] == "alert(1)"
