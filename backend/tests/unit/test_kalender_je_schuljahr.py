"""Kalender je Schuljahr (Päckchen BD, Schritt 4): laufendes aus `school_year.yaml`,
andere als `school_year_2027-28.yaml` daneben."""
import pytest

from app.planning import calendar as kal

LAUFEND = """schuljahr: "2026/27"
beginn: 2026-09-14
ende: 2027-07-28
halbjahreswechsel: 2027-02-01
"""
KOMMEND = """schuljahr: "2027/28"
beginn: 2027-09-13
ende: 2028-07-26
halbjahreswechsel: 2028-02-07
ferien:
  - {name: Herbstferien, von: 2027-11-02, bis: 2027-11-05}
"""


@pytest.fixture
def ordner(tmp_path, monkeypatch):
    (tmp_path / "school_year.yaml").write_text(LAUFEND)
    monkeypatch.setattr(kal, "_DEFAULT_PATH", tmp_path / "school_year.yaml")
    monkeypatch.setattr(kal, "load_school_year", lambda: kal._lies(tmp_path / "school_year.yaml"))
    return tmp_path


def test_schuljahr_format():
    assert kal.ist_schuljahr("2027/28") and kal.ist_schuljahr("2099/00")
    assert not kal.ist_schuljahr("2027/29") and not kal.ist_schuljahr("2027-28")
    assert not kal.ist_schuljahr(None) and not kal.ist_schuljahr("../x")
    assert kal.naechstes_schuljahr("2026/27") == "2027/28"
    assert kal.naechstes_schuljahr("2099/00") == "2100/01"


def test_laufendes_aus_der_hauptdatei(ordner):
    assert kal.kalender_fuer("2026/27").beginn.isoformat() == "2026-09-14"


def test_anderes_aus_der_jahresdatei(ordner):
    assert kal.kalender_fuer("2027/28") is None
    (ordner / "school_year_2027-28.yaml").write_text(KOMMEND)
    cfg = kal.kalender_fuer("2027/28")
    assert cfg.schuljahr == "2027/28" and cfg.ferien[0].name == "Herbstferien"


def test_falsches_jahr_in_der_datei_gilt_als_fehlend(ordner):
    (ordner / "school_year_2028-29.yaml").write_text(KOMMEND)
    assert kal.kalender_fuer("2028/29") is None


def test_kaputte_datei_gilt_als_fehlend(ordner):
    (ordner / "school_year_2027-28.yaml").write_text("schuljahr: [")
    assert kal.kalender_fuer("2027/28") is None


def test_ungueltige_angabe(ordner):
    assert kal.kalender_fuer("../../etc") is None
