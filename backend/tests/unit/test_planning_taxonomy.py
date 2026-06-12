"""Unit-Tests für Taxonomie-Ergänzungen (Schritt 3)."""

import pytest

from app.context.taxonomy import (
    SCHULJAHRESENDE_CONTENT_TYPES,
    validate_unterrichtsstunde_metadata,
)


def test_schuljahresende_types_enthalten_unterrichtsstunde():
    assert "unterrichtsstunde" in SCHULJAHRESENDE_CONTENT_TYPES


def test_schuljahresende_types_enthalten_unterrichtseinheit():
    assert "unterrichtseinheit" in SCHULJAHRESENDE_CONTENT_TYPES


def test_validate_leer_ok():
    validate_unterrichtsstunde_metadata({})


def test_validate_keine_phasen_ok():
    validate_unterrichtsstunde_metadata({"stundenziel": "Mathe", "phasen": []})


def test_validate_phase_vollstaendig_ok():
    validate_unterrichtsstunde_metadata({
        "phasen": [{
            "id": "p1",
            "titel": "Einstieg",
            "dauer_min": 10,
            "prio": "kern",
            "status": "geplant",
        }]
    })


def test_validate_phase_mit_methode_text():
    validate_unterrichtsstunde_metadata({
        "phasen": [{
            "id": "p1", "titel": "E", "dauer_min": 5,
            "prio": "kern", "status": "geplant",
            "methode": {"text": "Unterrichtsgespräch"},
        }]
    })


def test_validate_phase_mit_methode_node_id():
    validate_unterrichtsstunde_metadata({
        "phasen": [{
            "id": "p1", "titel": "E", "dauer_min": 5,
            "prio": "kern", "status": "geplant",
            "methode": {"node_id": "00000000-0000-0000-0000-000000000001"},
        }]
    })


def test_validate_methode_beides_fehler():
    with pytest.raises(ValueError, match="text.*node_id|node_id.*text"):
        validate_unterrichtsstunde_metadata({
            "phasen": [{
                "id": "p1", "titel": "E", "dauer_min": 5,
                "prio": "kern", "status": "geplant",
                "methode": {"text": "X", "node_id": "abc"},
            }]
        })


def test_validate_methode_keines_fehler():
    with pytest.raises(ValueError, match="text.*node_id|node_id.*text"):
        validate_unterrichtsstunde_metadata({
            "phasen": [{
                "id": "p1", "titel": "E", "dauer_min": 5,
                "prio": "kern", "status": "geplant",
                "methode": {},
            }]
        })


def test_validate_ungueltige_prio():
    with pytest.raises(ValueError, match="prio"):
        validate_unterrichtsstunde_metadata({
            "phasen": [{
                "id": "p1", "titel": "E", "dauer_min": 5,
                "prio": "wichtig",
                "status": "geplant",
            }]
        })


def test_validate_ungueltigerstatus():
    with pytest.raises(ValueError, match="status"):
        validate_unterrichtsstunde_metadata({
            "phasen": [{
                "id": "p1", "titel": "E", "dauer_min": 5,
                "prio": "kern",
                "status": "abgesagt",
            }]
        })


def test_validate_dauer_null_fehler():
    with pytest.raises(ValueError, match="dauer_min"):
        validate_unterrichtsstunde_metadata({
            "phasen": [{
                "id": "p1", "titel": "E", "dauer_min": 0,
                "prio": "kern", "status": "geplant",
            }]
        })


def test_validate_pflichtfeld_fehlt():
    with pytest.raises(ValueError, match="titel"):
        validate_unterrichtsstunde_metadata({
            "phasen": [{
                "id": "p1", "dauer_min": 10,
                "prio": "kern", "status": "geplant",
            }]
        })
