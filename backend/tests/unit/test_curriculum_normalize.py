"""Unit-Tests für curriculum_normalize.py (Komponente 4b, Revision 2).

Deckt die beiden Revision-1-Bugs ab:
- Bug 1: IK-Referenzformat "3.1.1.(1)" statt "3.1.1. 1"
- Bug 2: Hinweise-Text abgeschnitten (→ MINT statt Volltext)
"""

import pytest

from app.context.curriculum_normalize import (
    _extract_ik_items,
    _extract_lp_codes_from_text,
    _extract_pk_items,
    normalize_raw_extraction,
)

# Zeilentrenner wie er aus der Serialisierung kommt (U+21B5)
SEP = "↵"


# ── _extract_ik_items ─────────────────────────────────────────────────────────


class TestExtractIkItems:
    def test_single_item(self):
        items = _extract_ik_items("(1) Prinzipien des Stellenwertsystems beschreiben")
        assert items == [("1", False)]

    def test_multiple_items_sep(self):
        """Mehrere Items mit ↵-Trenner (Serialisierungs-Format)."""
        text = SEP.join([
            "(1) Prinzipien",
            "(2) natürliche Zahlen",
            "(18) Zahlenwerte",
            "(6) Zahlen vergleichen",
        ])
        items = _extract_ik_items(text)
        assert [num for num, _ in items] == ["1", "2", "18", "6"]
        assert all(not partial for _, partial in items)

    def test_multiple_items_newline(self):
        """Mehrere Items mit echtem \\n-Trenner."""
        text = "\n".join([
            "(1) Prinzipien",
            "(2) natürliche Zahlen",
            "(18) Zahlenwerte",
        ])
        items = _extract_ik_items(text)
        assert [num for num, _ in items] == ["1", "2", "18"]

    def test_ellipsis_in_text_not_partial(self):
        """Auslassungszeichen [...] im Fließtext markiert Items NICHT als partiell.

        Bug-Regression: '(6) [...] Zahlen...' darf nicht alle Items partial machen.
        """
        text = SEP.join([
            "(1) Text A",
            "(6) [...] Zahlen und Punkte auf der Zahlengeraden",
        ])
        items = _extract_ik_items(text)
        nums = {num: partial for num, partial in items}
        assert nums["1"] is False
        assert nums["6"] is False

    def test_bracket_around_item_number_is_partial(self):
        """[(N) Text] — Klammer direkt vor der Nummer → partiell."""
        text = SEP.join([
            "(1) normaler Text",
            "[(18) partieller Text]",
        ])
        items = _extract_ik_items(text)
        nums = {num: partial for num, partial in items}
        assert nums["1"] is False
        assert nums["18"] is True

    def test_empty_text(self):
        assert _extract_ik_items("") == []
        assert _extract_ik_items(None) == []  # type: ignore[arg-type]


# ── _extract_pk_items ─────────────────────────────────────────────────────────


class TestExtractPkItems:
    def test_single_group_multiple_items(self):
        pk_raw = SEP.join([
            "2.4 Mit symbolischen Elementen umgehen",
            "1. zwischen Sprachen wechseln",
            "3. zwischen Darstellungen wechseln",
            "5. Routineverfahren anwenden",
        ])
        refs = _extract_pk_items(pk_raw)
        assert refs == ["2.4.1", "2.4.3", "2.4.5"]

    def test_multiple_groups_sep(self):
        """Zwei Gruppen mit ↵-Trenner."""
        pk_raw = SEP.join([
            "2.5 Kommunizieren",
            "1. Einsichten schriftlich dokumentieren",
            "2.4 Mit symbolischen Elementen umgehen",
            "1. zwischen Sprachen wechseln",
            "3. zwischen Darstellungen wechseln",
            "5. Routineverfahren anwenden",
        ])
        refs = _extract_pk_items(pk_raw)
        assert refs == ["2.5.1", "2.4.1", "2.4.3", "2.4.5"]

    def test_multiple_groups_newline(self):
        """Zwei Gruppen mit echtem \\n-Trenner."""
        pk_raw = "\n".join([
            "2.5 Kommunizieren",
            "1. Einsichten dokumentieren",
            "2.4 Umgehen",
            "3. Darstellungen wechseln",
        ])
        refs = _extract_pk_items(pk_raw)
        assert refs == ["2.5.1", "2.4.3"]

    def test_empty(self):
        assert _extract_pk_items("") == []
        assert _extract_pk_items(None) == []  # type: ignore[arg-type]

    def test_group_without_items_produces_no_refs(self):
        pk_raw = "2.4 Mit symbolischen Elementen umgehen"
        assert _extract_pk_items(pk_raw) == []


# ── _extract_lp_codes_from_text ───────────────────────────────────────────────


class TestExtractLpCodes:
    def test_l_bo(self):
        codes = _extract_lp_codes_from_text("Hinweis. L BO Fachspezifische Zugaenge")
        assert "BO" in codes

    def test_l_btv_in_parentheses(self):
        codes = _extract_lp_codes_from_text("(L) BTV Bezug zur Demokratieerziehung")
        assert "BTV" in codes

    def test_multiple_codes(self):
        text = "L BO und L MB und (L) BNE"
        codes = _extract_lp_codes_from_text(text)
        assert "BO" in codes
        assert "MB" in codes
        assert "BNE" in codes

    def test_empty(self):
        assert _extract_lp_codes_from_text("") == []
        assert _extract_lp_codes_from_text(None) == []


# ── normalize_raw_extraction (Integration) ───────────────────────────────────


def _make_raw(ik_raw, pk_raw, hinweise="Hinweis", konkretisierung="Klass",
              ik_abschnitt="3.1.1", pk_merged=False):
    return {
        "kapitel": {
            "titel": "Natuerliche Zahlen",
            "std": "18 Std.",
            "lernsequenzen": [
                {
                    "bp_titel": "3.1.1 Zahlbereiche erkunden",
                    "ik_abschnitt": ik_abschnitt,
                    "eintraege": [
                        {
                            "ik_raw": ik_raw,
                            "pk_raw": pk_raw,
                            "pk_merged_from_above": pk_merged,
                            "konkretisierung": konkretisierung,
                            "hinweise": hinweise,
                        }
                    ],
                }
            ],
        }
    }


class TestNormalizeRawExtraction:
    def test_ik_schluessel_format(self):
        """Verhindert Revision-1-Bug '3.1.1. 1' — muss '3.1.1.(1)' sein."""
        raw = _make_raw(
            ik_raw=SEP.join(["(1) Prinzipien", "(2) Zahlen lesen", "(18) Runden"]),
            pk_raw=SEP.join(["2.5 Kommunizieren", "1. Einsichten dokumentieren"]),
        )
        chapters = normalize_raw_extraction(raw)
        entries = chapters[0].lernsequenzen[0].eintraege
        assert len(entries) == 3
        assert entries[0].ik == "3.1.1.(1)"
        assert entries[1].ik == "3.1.1.(2)"
        assert entries[2].ik == "3.1.1.(18)"

    def test_pk_referenzen(self):
        raw = _make_raw(
            ik_raw="(1) Text",
            pk_raw=SEP.join([
                "2.5 Kommunizieren",
                "1. Einsichten dokumentieren",
                "2.4 Umgehen",
                "1. zwischen Sprachen",
                "3. Darstellungen",
                "5. Routinen",
            ]),
        )
        chapters = normalize_raw_extraction(raw)
        entry = chapters[0].lernsequenzen[0].eintraege[0]
        assert entry.pk == ["2.5.1", "2.4.1", "2.4.3", "2.4.5"]

    def test_hinweise_volltext_erhalten(self):
        """Verhindert Revision-1-Bug '→ MINT' — Hinweise muessen vollstaendig sein."""
        hinweise = SEP.join([
            "Hinweis auf den Grundschulbildungsplan",
            "Prinzipien in Analogie zum Dualsystem herausarbeiten",
            "MINT: Umrechnung vom Binaersystem ins Hexadezimalsystem und umgekehrt",
        ])
        raw = _make_raw(
            ik_raw="(1) Text",
            pk_raw=SEP.join(["2.4 Umgehen", "1. Item"]),
            hinweise=hinweise,
        )
        chapters = normalize_raw_extraction(raw)
        for entry in chapters[0].lernsequenzen[0].eintraege:
            assert entry.hinweise == hinweise

    def test_hinweise_auf_alle_eintraege_kopiert(self):
        """Bei Fan-out (4 IK-Items) bekommen alle Eintraege denselben Hinweise-Volltext."""
        hinweise = "Langer Hinweistext mit MINT und Grundschulverweis"
        raw = _make_raw(
            ik_raw=SEP.join(["(1) A", "(2) B", "(18) C", "(6) D"]),
            pk_raw=SEP.join(["2.4 Umgehen", "1. Item"]),
            hinweise=hinweise,
        )
        chapters = normalize_raw_extraction(raw)
        entries = chapters[0].lernsequenzen[0].eintraege
        assert len(entries) == 4
        assert all(e.hinweise == hinweise for e in entries)

    def test_merged_pk_kein_crash(self):
        """pk_merged_from_above=True darf nicht crashen."""
        raw = {
            "kapitel": {
                "titel": "Test",
                "lernsequenzen": [
                    {
                        "bp_titel": "3.1.1 Test",
                        "ik_abschnitt": "3.1.1",
                        "eintraege": [
                            {
                                "ik_raw": "(1) Text",
                                "pk_raw": SEP.join(["2.4 Umgehen", "1. Item"]),
                                "pk_merged_from_above": False,
                                "konkretisierung": None,
                                "hinweise": None,
                            },
                            {
                                "ik_raw": "(2) Text",
                                "pk_raw": None,
                                "pk_merged_from_above": True,
                                "konkretisierung": None,
                                "hinweise": None,
                            },
                        ],
                    }
                ],
            }
        }
        chapters = normalize_raw_extraction(raw)
        entries = chapters[0].lernsequenzen[0].eintraege
        assert entries[0].pk == ["2.4.1"]
        assert isinstance(entries[1].pk, list)  # kein Crash

    def test_fehlendes_ik_abschnitt_warnung(self):
        raw = _make_raw(
            ik_raw="(1) Text",
            pk_raw=SEP.join(["2.4 Umgehen", "1. Item"]),
            ik_abschnitt=None,
        )
        chapters = normalize_raw_extraction(raw)
        entry = chapters[0].lernsequenzen[0].eintraege[0]
        assert entry.ik is None
        assert any("IK-Abschnitt" in w for w in entry.warnings)

    def test_lp_codes_extrahiert_hinweise_ungekuerzt(self):
        hinweise = "L BO Fachspezifische Zugaenge zur Arbeitswelt. Weitere Hinweise folgen hier."
        raw = _make_raw(
            ik_raw="(1) Text",
            pk_raw=SEP.join(["2.4 Umgehen", "1. Item"]),
            hinweise=hinweise,
        )
        chapters = normalize_raw_extraction(raw)
        entry = chapters[0].lernsequenzen[0].eintraege[0]
        assert "BO" in entry.lp
        assert entry.hinweise == hinweise  # Volltext erhalten, nicht durch LP-Code ersetzt

    def test_ellipsis_nicht_partiell(self):
        """Regression: (6) [...] Text darf item 6 NICHT als partiell markieren."""
        ik_raw = SEP.join([
            "(1) Prinzipien",
            "(6) [...] Zahlen und Punkte auf der Zahlengeraden",
        ])
        raw = _make_raw(
            ik_raw=ik_raw,
            pk_raw=SEP.join(["2.4 Umgehen", "1. Item"]),
        )
        chapters = normalize_raw_extraction(raw)
        entries = chapters[0].lernsequenzen[0].eintraege
        assert entries[0].ik == "3.1.1.(1)"
        assert entries[0].ik_partiell is False
        assert entries[1].ik == "3.1.1.(6)"
        assert entries[1].ik_partiell is False
