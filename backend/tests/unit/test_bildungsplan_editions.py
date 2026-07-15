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
from unittest.mock import AsyncMock, MagicMock, patch

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
schedule_suffixes = _scraper.schedule_suffixes
scraper_main = _scraper.main


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


# -- subject_editions: Editions-Auflösung pro Fach (Fahrplan-basiert) ----------

# Geordneter Editions-Fahrplan: Basis → V2 → V3.
_SUFFIXES = ["", ".V2", ".V3"]


def test_basis_fach_nur_basis():
    fach = {"fach_code": "M"}
    assert subject_editions(fach, _SUFFIXES, default_suffix="") == [("M", "")]


def test_v2_fach_scrapt_basis_und_v2():
    # Aktuelle Edition .V2 → Basis (als Verweisziel) + V2 (Hauptdatei = fach_code).
    fach = {"fach_code": "CH", "bildungsplan_suffix": ".V2"}
    assert subject_editions(fach, _SUFFIXES, default_suffix="") == [
        ("CH_BASIS", ""),
        ("CH", ".V2"),
    ]


def test_v3_fach_scrapt_alle_bisherigen():
    # Künftig (Fach auf .V3): Basis + V2 + V3.
    fach = {"fach_code": "CH", "bildungsplan_suffix": ".V3"}
    assert subject_editions(fach, _SUFFIXES, default_suffix="") == [
        ("CH_BASIS", ""),
        ("CH_V2", ".V2"),
        ("CH", ".V3"),
    ]


def test_globaler_default_suffix_wird_geerbt():
    # Kein Fach-Suffix, aber globaler Default .V2 → Basis + V2.
    fach = {"fach_code": "M"}
    assert subject_editions(fach, _SUFFIXES, default_suffix=".V2") == [
        ("M_BASIS", ""),
        ("M", ".V2"),
    ]


def test_edition_nicht_im_fahrplan_nur_diese():
    # Fach-Edition, die der Fahrplan nicht kennt → nur sie selbst.
    fach = {"fach_code": "X", "bildungsplan_suffix": ".VX"}
    assert subject_editions(fach, _SUFFIXES, default_suffix="") == [("X", ".VX")]


def test_schedule_suffixes_ordnung():
    bp_default = {
        "suffix": "",
        "editionen": [
            {"suffix": ".V3", "ab_schuljahr": "2026/27"},
            {"suffix": ""},
            {"suffix": ".V2", "ab_schuljahr": "2016/17"},
        ],
    }
    assert schedule_suffixes(bp_default) == ["", ".V2", ".V3"]


def test_schedule_suffixes_fallback_ohne_fahrplan():
    assert schedule_suffixes({"suffix": ""}) == [""]
    assert schedule_suffixes({"suffix": ".V2"}) == [".V2"]


# -- main(): Fehler pro Fach isolieren statt Batch-Abbruch (Todo A1) ------------

def _async_client_cm():
    """Async-Context-Manager-Mock für httpx.AsyncClient(...)."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=MagicMock(name="httpx_client"))
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


_MIN_SUBJECTS_YAML = """\
schulart: GYM
schuljahr: "2026/27"
bildungsplan_default:
  bp_basis: BP2016BW
  suffix: ""
subjects:
  - slug: bad
    fach_code: BAD
  - slug: good
    fach_code: GOOD
"""


def _write_cfg(tmp_path) -> str:
    p = tmp_path / "subjects.yaml"
    p.write_text(_MIN_SUBJECTS_YAML, encoding="utf-8")
    return str(p)


@pytest.mark.asyncio
async def test_main_isolates_failing_fach_and_continues(tmp_path):
    """Ein Fach, das wirft, wird übersprungen; nachfolgende Fächer laufen weiter."""
    def _sf(client, label, *a, **k):
        if label == "BAD":
            raise RuntimeError("ungültige Quell-URL")
        return (1, 0, 0)

    fake_scrape_fach = AsyncMock(side_effect=_sf)
    with patch.object(_scraper, "scrape_leitperspektiven", AsyncMock(return_value=[])), \
         patch.object(_scraper, "scrape_fach", fake_scrape_fach), \
         patch.object(_scraper.httpx, "AsyncClient", return_value=_async_client_cm()):
        skipped = await scraper_main(_write_cfg(tmp_path), str(tmp_path))

    # BAD übersprungen, GOOD trotzdem gescrapt (Reihenfolge-unabhängig).
    assert [slug for slug, _ in skipped] == ["bad"]
    assert "RuntimeError" in skipped[0][1]
    called_labels = {c.args[1] for c in fake_scrape_fach.call_args_list}
    assert called_labels == {"BAD", "GOOD"}


@pytest.mark.asyncio
async def test_main_writes_skip_summary_file(tmp_path):
    """Übersprungene Fächer werden in eine scrape_skipped-Datei geschrieben."""
    fake_scrape_fach = AsyncMock(side_effect=RuntimeError("kaputt"))
    with patch.object(_scraper, "scrape_leitperspektiven", AsyncMock(return_value=[])), \
         patch.object(_scraper, "scrape_fach", fake_scrape_fach), \
         patch.object(_scraper.httpx, "AsyncClient", return_value=_async_client_cm()):
        skipped = await scraper_main(_write_cfg(tmp_path), str(tmp_path))

    assert {slug for slug, _ in skipped} == {"bad", "good"}
    skip_files = list(tmp_path.glob("scrape_skipped_*.log"))
    assert len(skip_files) == 1
    body = skip_files[0].read_text(encoding="utf-8")
    assert "bad" in body and "good" in body


@pytest.mark.asyncio
async def test_main_no_skips_returns_empty(tmp_path):
    """Läuft alles durch, ist die skipped-Liste leer und keine Datei entsteht."""
    with patch.object(_scraper, "scrape_leitperspektiven", AsyncMock(return_value=[])), \
         patch.object(_scraper, "scrape_fach", AsyncMock(return_value=(1, 0, 0))), \
         patch.object(_scraper.httpx, "AsyncClient", return_value=_async_client_cm()):
        skipped = await scraper_main(_write_cfg(tmp_path), str(tmp_path))

    assert skipped == []
    assert list(tmp_path.glob("scrape_skipped_*.log")) == []
