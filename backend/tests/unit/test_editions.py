"""Unit-Tests für den Editions-Fahrplan-Loader (app.context.editions)."""

from pathlib import Path

import pytest
import yaml

from app.context.editions import (
    Edition,
    aktive_edition,
    load_edition_schedule,
    obergrenze,
    parse_schuljahr_start,
)


def _cfg(editionen):
    return {"bildungsplan_default": {"bp_basis": "BP2016BW", "editionen": editionen}}


# Fahrplan wie in der echten subjects.yaml — Basis · V2 (vollständig) · V3 (wächst).
_SCHEDULE = load_edition_schedule(
    _cfg(
        [
            {"suffix": ""},
            {"suffix": ".V2", "ab_schuljahr": "2016/17", "einstieg_stufen": [5, 13]},
            {"suffix": ".V3", "ab_schuljahr": "2026/27",
             "einstieg_stufen": [5, 7], "wachstum": "nach_oben"},
        ]
    )
)


def test_parse_schuljahr_start():
    assert parse_schuljahr_start("2026/27") == 2026
    assert parse_schuljahr_start("2016/17") == 2016
    with pytest.raises(ValueError):
        parse_schuljahr_start("kein-jahr")


def test_load_schedule_order_and_bp_version():
    # Reihenfolge im YAML bewusst durcheinander → Loader sortiert alt→neu.
    eds = load_edition_schedule(
        _cfg(
            [
                {"suffix": ".V3", "ab_schuljahr": "2026/27",
                 "einstieg_stufen": [5, 7], "wachstum": "nach_oben"},
                {"suffix": ""},
                {"suffix": ".V2", "ab_schuljahr": "2016/17",
                 "einstieg_stufen": [5, 13]},
            ]
        )
    )
    assert [e.suffix for e in eds] == ["", ".V2", ".V3"]
    assert [e.bp_version for e in eds] == ["2016", "2016.V2", "2016.V3"]
    assert eds[0].ab_jahr is None  # Basis = immer gültiger Fallback
    v3 = eds[2]
    assert v3.ab_jahr == 2026
    assert (v3.einstieg_min, v3.einstieg_max) == (5, 7)
    assert v3.wachstum == "nach_oben"
    assert eds[1].wachstum == "keine"  # Default


def test_fallback_to_global_suffix_when_no_schedule():
    eds = load_edition_schedule(
        {"bildungsplan_default": {"bp_basis": "BP2016BW", "suffix": ""}}
    )
    assert len(eds) == 1
    assert eds[0] == Edition("", "2016", None, None, None, "keine")


@pytest.mark.parametrize(
    "bad",
    [
        [{"suffix": "V2"}],                                  # Suffix ohne Punkt
        [{"suffix": ".V2"}, {"suffix": ".V2"}],              # Duplikat
        [{"suffix": ".V3", "einstieg_stufen": [7, 5]}],      # min > max
        [{"suffix": ".V3", "einstieg_stufen": [5]}],         # falsche Länge
        [{"suffix": ".V3", "wachstum": "seitwärts"}],        # unbekanntes wachstum
    ],
)
def test_validation_errors(bad):
    with pytest.raises(ValueError):
        load_edition_schedule(_cfg(bad))


def test_real_subjects_yaml_parses():
    p = Path(__file__).resolve().parents[3] / "config" / "subjects.yaml"
    if not p.exists():
        pytest.skip("config/subjects.yaml nicht gefunden")
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    by_suffix = {e.suffix: e for e in load_edition_schedule(cfg)}
    assert {"", ".V2", ".V3"} <= set(by_suffix)
    assert by_suffix[".V3"].ab_jahr == 2026
    assert (by_suffix[".V3"].einstieg_min, by_suffix[".V3"].einstieg_max) == (5, 7)
    assert by_suffix[".V2"].bp_version == "2016.V2"


@pytest.mark.parametrize(
    "jahr,stufe,erwartet",
    [
        (2026, 5, "2016.V3"),   # V3-Einstieg
        (2026, 7, "2016.V3"),   # oberer Rand des V3-Einstiegs
        (2026, 8, "2016.V2"),   # über der V3-Frontier → V2
        (2027, 8, "2016.V3"),   # Frontier ein Jahr gewachsen → 8 jetzt V3
        (2031, 12, "2016.V3"),  # V3 hat alle Stufen erreicht
        (2016, 5, "2016.V2"),   # V2 in Kraft, V3 noch nicht
        (2015, 5, "2016"),      # vor V2 → Basis-Fallback
    ],
)
def test_aktive_edition_jahrestabelle(jahr, stufe, erwartet):
    assert aktive_edition(_SCHEDULE, stufe, jahr).bp_version == erwartet


def test_frontier_waechst_nicht_unter_einstieg():
    # Untere Grenze bleibt 5; eine (hypothetische) Stufe 4 fällt auf Basis zurück.
    assert aktive_edition(_SCHEDULE, 4, 2030).bp_version == "2016"


def test_inhalts_fallback():
    # V3 laut Fahrplan in Kraft (2026, Stufe 5), aber noch NICHT importiert:
    verf = {"2016", "2016.V2"}
    assert aktive_edition(_SCHEDULE, 5, 2026, verf).bp_version == "2016.V2"
    # sobald die V3-Knoten da sind, schaltet es selbsttätig um:
    assert aktive_edition(_SCHEDULE, 5, 2026, verf | {"2016.V3"}).bp_version == "2016.V3"


def test_obergrenze_waechst_jahrgangsweise():
    v3 = next(e for e in _SCHEDULE if e.suffix == ".V3")
    assert obergrenze(v3, 2026) == 7
    assert obergrenze(v3, 2027) == 8
    assert obergrenze(v3, 2031) == 12
    base = next(e for e in _SCHEDULE if e.suffix == "")
    assert obergrenze(base, 2026) is None  # Basis ist unbeschränkt


def test_keine_edition_wenn_liste_leer():
    assert aktive_edition([], 5, 2026) is None
