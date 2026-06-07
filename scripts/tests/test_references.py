"""Unit-Tests fuer scripts/scraper/references.py."""

import pytest
from scripts.scraper.references import classify_reference, strip_soft_hyphens


class TestStripSoftHyphens:
    def test_removes_soft_hyphen(self):
        assert strip_soft_hyphens("Saeu\u00adre") == "Saeure"

    def test_no_soft_hyphen(self):
        assert strip_soft_hyphens("Saeure") == "Saeure"

    def test_multiple_occurrences(self):
        assert strip_soft_hyphens("Er\u00adkennt\u00adnis") == "Erkenntnis"

    def test_empty_string(self):
        assert strip_soft_hyphens("") == ""


class TestClassifyReference:
    def test_develops_pk_kompetenz(self):
        result = classify_reference("BP2016BW_ALLG_GYM_CH_PK_01_06")
        assert result is not None
        assert result['type'] == 'develops'
        assert result['target_bp_id'] == "BP2016BW_ALLG_GYM_CH_PK_01_06"

    def test_develops_pk_gruppe(self):
        result = classify_reference("BP2016BW_ALLG_GYM_M_PK_01")
        assert result is not None
        assert result['type'] == 'develops'

    def test_related_to_ik_same_fach(self):
        result = classify_reference("BP2016BW_ALLG_GYM_CH_IK_5-6_01_02")
        assert result is not None
        assert result['type'] == 'related_to'
        assert result['target_bp_id'] == "BP2016BW_ALLG_GYM_CH_IK_5-6_01_02"

    def test_related_to_ik_other_fach(self):
        result = classify_reference("BP2016BW_ALLG_GYM_BNT_IK_5-6_02_00")
        assert result is not None
        assert result['type'] == 'related_to'

    def test_references_lp_bne(self):
        result = classify_reference("BNE_01")
        assert result is not None
        assert result['type'] == 'references'
        assert result['target_bp_id'] == "BNE_01"

    def test_references_lp_mb(self):
        result = classify_reference("MB_05")
        assert result is not None
        assert result['type'] == 'references'

    def test_references_all_lp_kuerzel(self):
        for kuerzel in ['BNE', 'BTV', 'PG', 'BO', 'MB', 'VB', 'LFDB']:
            result = classify_reference(f"{kuerzel}_03")
            assert result is not None, f"Kuerzel {kuerzel} nicht erkannt"
            assert result['type'] == 'references'

    def test_unknown_token_returns_none(self):
        assert classify_reference("UNKNOWN_TOKEN") is None

    def test_empty_token_returns_none(self):
        assert classify_reference("") is None

    def test_whitespace_stripped(self):
        result = classify_reference("  BNE_01  ")
        assert result is not None
        assert result['type'] == 'references'
