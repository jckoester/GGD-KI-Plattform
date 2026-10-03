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


# Eine Phase, wie sie im Planer gespeichert wird — gemessen am Dev-Bestand (03.10.2026):
# `name`, `material` als Liste, Verweise als {typ, wert, node_id, titel}, kein `status`.
PLANER_PHASE = {
    "id": "p1", "name": "Einstieg", "dauer_min": 10, "prio": "kern",
    "beschreibung": "Video Zahnräder",
    "sozialform": {"typ": "node", "wert": None,
                   "node_id": "00000000-0000-0000-0000-000000000001", "titel": "Plenum"},
    "methode": None,
    "material": [{"typ": "text", "wert": "AB Übersetzung", "node_id": None, "titel": None}],
}


def _mit(**felder):
    return {"phasen": [{**PLANER_PHASE, **felder}]}


def test_validate_planer_format_ok():
    """Der Fehler bis 0.12.0: Genau diese Phase scheiterte mit 422."""
    validate_unterrichtsstunde_metadata({"phasen": [PLANER_PHASE]})


def test_was_der_planer_speichern_kann_nimmt_der_validator_an():
    """Der Rundweg: eine Feldliste, nicht zwei."""
    from app.planning.schemas import LessonPhaseItem

    phase = LessonPhaseItem(name="Sicherung", dauer_min=5, prio="uebung").model_dump(mode="json")
    validate_unterrichtsstunde_metadata({"phasen": [phase]})


def test_validate_format_des_planungsassistenten_ok():
    """Der Assistent schreibt Roh-Dicts — Pflicht sind dort nur `name` und `dauer_min`."""
    validate_unterrichtsstunde_metadata({"phasen": [{"name": "Erarbeitung", "dauer_min": 20}]})


def test_validate_status_ist_optional_aber_gueltig():
    """Die Nachbereitung schreibt ihn, die Kürzung auch — gesetzt muss er stimmen."""
    validate_unterrichtsstunde_metadata(_mit(status="gestrichen", kuerzung=True))
    with pytest.raises(ValueError, match="status"):
        validate_unterrichtsstunde_metadata(_mit(status="abgesagt"))


def test_validate_ungueltige_prio():
    with pytest.raises(ValueError, match="prio"):
        validate_unterrichtsstunde_metadata(_mit(prio="wichtig"))


def test_validate_dauer_null_fehler():
    with pytest.raises(ValueError, match="dauer_min"):
        validate_unterrichtsstunde_metadata(_mit(dauer_min=0))


def test_validate_name_fehlt():
    phase = {k: v for k, v in PLANER_PHASE.items() if k != "name"}
    with pytest.raises(ValueError, match="name"):
        validate_unterrichtsstunde_metadata({"phasen": [phase]})


def test_validate_phase_muss_objekt_sein():
    with pytest.raises(ValueError, match="Objekt"):
        validate_unterrichtsstunde_metadata({"phasen": ["Einstieg"]})


def test_validate_phasen_muss_liste_sein():
    with pytest.raises(ValueError, match="Liste"):
        validate_unterrichtsstunde_metadata({"phasen": {"name": "Einstieg"}})
