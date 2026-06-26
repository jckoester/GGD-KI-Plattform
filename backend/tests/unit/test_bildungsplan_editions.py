"""Unit-Tests für die Bildungsplan-Editions-Auflösung (Fach-Suffix-Kaskade).

Lädt die Repo-Root-``scripts/``-Module isoliert. Hintergrund: ``backend/scripts``
(Namespace) und ``scripts`` (Repo-Root, reguläres Paket) heißen beide ``scripts``;
der Scraper macht ``from scripts.scraper.parsers import ...``. Damit andere Unit-Tests
(die aus ``backend/scripts`` importieren) unabhängig von der Lade-Reihenfolge intakt
bleiben, wird der ``scripts*``-Zustand in ``sys.modules`` um den Scraper-Import herum
exakt wiederhergestellt.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _scripts_keys() -> list[str]:
    return [k for k in sys.modules if k == "scripts" or k.startswith("scripts.")]


def _load_isolated(name: str, rel_path: str, need_repo_on_path: bool = False):
    path = REPO_ROOT / rel_path
    if not need_repo_on_path:
        # Modul ohne 'scripts.'-Importe — vollständig isolierbar.
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    # Modul mit 'from scripts.scraper...'-Importen: Repo-Root muss auf dem Pfad sein.
    # scripts*-Zustand sichern, leeren (damit Repo-Root sauber auflöst), danach
    # exakt zurückspielen — reihenfolgeunabhängig für andere Tests.
    snapshot = {k: sys.modules[k] for k in _scripts_keys()}
    for k in _scripts_keys():
        del sys.modules[k]
    sys.path.insert(0, str(REPO_ROOT))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(REPO_ROOT))
        for k in _scripts_keys():
            del sys.modules[k]
        sys.modules.update(snapshot)
    return mod


_import_bp = _load_isolated("_import_bildungsplan_uut", "scripts/import_bildungsplan.py")
_scraper = _load_isolated(
    "_bildungsplan_scraper_uut",
    "scripts/scraper/bildungsplan_scraper.py",
    need_repo_on_path=True,
)

validate_subjects_yaml = _import_bp.validate_subjects_yaml
subject_editions = _scraper.subject_editions


def _cfg(*subjects: dict) -> dict:
    return {"schulart": "GYM", "schuljahr": "2026/27", "subjects": list(subjects)}


# -- validate_subjects_yaml: neue bildungsplan_suffix-Regel ---------------------


def test_suffix_with_fach_code_is_valid():
    errors = validate_subjects_yaml(
        _cfg({"slug": "mathematik", "fach_code": "M", "bildungsplan_suffix": ".V2"})
    )
    assert errors == []


def test_suffix_without_fach_code_errors():
    errors = validate_subjects_yaml(
        _cfg({"slug": "deutsch", "bildungsplan_suffix": ".V2"})
    )
    assert any("bildungsplan_suffix" in e and "fach_code" in e for e in errors)


def test_non_string_suffix_errors():
    errors = validate_subjects_yaml(
        _cfg({"slug": "mathematik", "fach_code": "M", "bildungsplan_suffix": [".V2"]})
    )
    assert any("nicht-textuelles bildungsplan_suffix" in e for e in errors)


def test_empty_suffix_needs_no_fach_code():
    errors = validate_subjects_yaml(
        _cfg({"slug": "deutsch", "bildungsplan_suffix": ""})
    )
    assert errors == []


def test_overrides_without_fach_code_still_errors():
    # Regression: bestehende Override-Regel bleibt intakt.
    errors = validate_subjects_yaml(
        _cfg({"slug": "deutsch", "bildungsplan_overrides": {"5-6": ".V2"}})
    )
    assert any("bildungsplan_overrides" in e and "fach_code" in e for e in errors)


# -- subject_editions: Editions-Auflösung pro Fach -----------------------------


def test_subject_suffix_whole_subject():
    fach = {"fach_code": "CH", "bildungsplan_suffix": ".V2"}
    assert subject_editions(fach, default_suffix="") == [("CH", ".V2")]


def test_grade_band_override_on_base_default():
    fach = {"fach_code": "M", "bildungsplan_overrides": {"5-6": ".V2"}}
    assert subject_editions(fach, default_suffix="") == [("M", ""), ("M_V2", ".V2")]


def test_subject_suffix_with_downgrade_override():
    # Ganzes Fach auf .V2, aber Oberstufe noch auf Basis → beide Editionen scrapen.
    fach = {
        "fach_code": "M",
        "bildungsplan_suffix": ".V2",
        "bildungsplan_overrides": {"11-13": ""},
    }
    assert subject_editions(fach, default_suffix="") == [("M", ".V2"), ("M_BASIS", "")]


def test_no_suffix_no_overrides_uses_global_default():
    fach = {"fach_code": "M"}
    assert subject_editions(fach, default_suffix="") == [("M", "")]
    assert subject_editions(fach, default_suffix=".V2") == [("M", ".V2")]


def test_override_equal_to_subject_suffix_not_duplicated():
    fach = {
        "fach_code": "M",
        "bildungsplan_suffix": ".V2",
        "bildungsplan_overrides": {"5-6": ".V2"},
    }
    assert subject_editions(fach, default_suffix="") == [("M", ".V2")]
