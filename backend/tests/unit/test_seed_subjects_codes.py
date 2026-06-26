"""Unit-Tests für die Fachcode-Ableitung beim Seed (subjects.fach_code/fach_codes)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

from scripts.seed_subjects import _all_fach_codes, _resolve_fach_code


# -- _resolve_fach_code: Primär-Code für die skalare Spalte --------------------


def test_resolve_scalar_uppercased():
    assert _resolve_fach_code({"fach_code": "m"}) == "M"


def test_resolve_multi_picks_lowest_band():
    fach = {"fach_codes": {"11-12": "NWTBFO", "8-10": "NWT"}}
    assert _resolve_fach_code(fach) == "NWT"


def test_resolve_none_without_code():
    assert _resolve_fach_code({"slug": "deutsch"}) is None


# -- _all_fach_codes: vollständige Code-Liste für die Array-Spalte -------------


def test_all_scalar():
    assert _all_fach_codes({"fach_code": "ch"}) == ["CH"]


def test_all_multi_in_band_order():
    fach = {"fach_codes": {"8-10": "NWT", "11-12": "NWTBFO"}}
    assert _all_fach_codes(fach) == ["NWT", "NWTBFO"]


def test_all_multi_dedup_case_insensitive():
    fach = {"fach_codes": {"8-10": "NWT", "9-10": "nwt"}}
    assert _all_fach_codes(fach) == ["NWT"]


def test_all_none_without_code():
    assert _all_fach_codes({"slug": "deutsch"}) == []
