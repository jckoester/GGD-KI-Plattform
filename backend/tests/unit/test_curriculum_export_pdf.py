"""Unit-Tests für die PDF-Aufbereitung des Curriculum-Exports (KS-Phase-6 Schritt 5).

Reine Funktionen ohne DB/weasyprint: Volltext-Mapping und Markdown-Rendering.
"""

from app.context.curriculum_export import _build_pdf_kapitel, _render_markdown


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
    def test_ik_pk_volltext_from_refs(self):
        """IK/PK werden über node_id auf den Knoten-Volltext (title) gemappt."""
        tree = _tree_with_entry(
            entry={
                "ik": [{"node_id": "ik1", "nr": "3.1.1", "partiell": True}],
                "pk": [{"node_id": "pk1", "pk_id": "PK_05.1"}],
            },
            ik_refs=[{"node_id": "ik1", "title": "3.1.1 Zahlen vergleichen", "nr": "3.1.1"}],
            pk_refs=[{"node_id": "pk1", "title": "2.2.1 Begründen", "pk_id": "PK_05.1"}],
        )
        e = _build_pdf_kapitel(tree)[0]["lernsequenzen"][0]["eintraege"][0]
        assert e["ik_items"] == [{"text": "3.1.1 Zahlen vergleichen", "partiell": True}]
        assert e["pk_items"] == [{"text": "2.2.1 Begründen"}]

    def test_fallback_to_nr_and_pk_id(self):
        """Ohne passenden Ref-Titel fällt der Text auf nr bzw. pk_id zurück."""
        tree = _tree_with_entry(
            entry={
                "ik": [{"node_id": "x", "nr": "3.1.1", "partiell": False}],
                "pk": [{"node_id": "y", "pk_id": "PK_05.1"}],
            },
        )
        e = _build_pdf_kapitel(tree)[0]["lernsequenzen"][0]["eintraege"][0]
        assert e["ik_items"] == [{"text": "3.1.1", "partiell": False}]
        assert e["pk_items"] == [{"text": "PK_05.1"}]


class TestRenderMarkdown:
    def test_list_becomes_ul(self):
        html = _render_markdown("- Farbe\n- Geruch\n- Dichte")
        assert "<ul>" in html and html.count("<li>") == 3
        assert "Farbe" in html

    def test_empty_is_empty(self):
        assert _render_markdown("") == ""
        assert _render_markdown(None) == ""

    def test_raw_html_escaped(self):
        """Roh-HTML in der Quelle wird escaped (html=False), kein Injection."""
        html = _render_markdown("<script>alert(1)</script>")
        assert "<script>" not in html
