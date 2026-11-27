"""Rahmenangaben am Curriculum (0.46, Päckchen AP Teil B, Schritt 4; E19, E20)."""
import pytest

from app.context.curriculum_rahmen import (
    rahmen_abschnitte,
    rahmen_normalisieren,
    stufen,
    verplanbar,
    wochenstunden_text,
)
from app.context.schemas import CurriculumDraftConfirmed


def test_stufen_eines_bands():
    assert stufen("7/8") == [7, 8]
    assert stufen("8-10") == [8, 9, 10]
    assert stufen("9") == [9]
    assert stufen("") == [] and stufen(None) == []


def test_normalisieren_bereinigt():
    aus = rahmen_normalisieren({
        "wochenstunden": {"8": "2,5", 7: 2, "9": ""},
        "lehrwerk": "  Elemente Chemie ", "beschluesse": "", "schwerpunkte": None, "fremd": "x",
    })
    assert aus == {"wochenstunden": {"7": 2, "8": 2.5}, "lehrwerk": "Elemente Chemie"}
    assert list(aus["wochenstunden"]) == ["7", "8"]
    assert rahmen_normalisieren(None) == {} and rahmen_normalisieren({}) == {}


@pytest.mark.parametrize("rahmen", [
    {"wochenstunden": {"7": "zwei"}},
    {"wochenstunden": {"7": 11}},
    {"wochenstunden": {"7": -1}},
    {"wochenstunden": {"7": 1.25}},
    {"wochenstunden": {"7": True}},
    {"wochenstunden": {"Kl. 7": 2}},
    {"wochenstunden": [2, 2]},
    {"lehrwerk": ["A"]},
    "Lehrwerk",
])
def test_normalisieren_weist_unbrauchbares_ab(rahmen):
    with pytest.raises(ValueError):
        rahmen_normalisieren(rahmen)


def test_verplanbar_dreissig_je_wochenstunde():
    assert verplanbar({"wochenstunden": {"7": 2, "8": 2}}, "7/8") == 120
    assert verplanbar({"wochenstunden": {"9": 2.5}}, "9") == 75
    assert verplanbar({"wochenstunden": {"7": 2, "8": 0}}, "7/8") == 60


def test_verplanbar_erst_wenn_jede_stufe_eine_angabe_hat():
    assert verplanbar({"wochenstunden": {"7": 2}}, "7/8") is None
    assert verplanbar({}, "7/8") is None
    assert verplanbar({"wochenstunden": {"7": 2}}, "") is None


def test_wochenstunden_text():
    assert wochenstunden_text({"wochenstunden": {"7": 2, "8": 1.5}}, "7/8") == (
        "Kl. 7: 2 · Kl. 8: 1,5 — verplanbar: 105 Std. (30 je Wochenstunde)")
    assert wochenstunden_text({"wochenstunden": {"7": 2}}, "7/8") == "Kl. 7: 2"
    assert wochenstunden_text({}, "7/8") == ""


def test_abschnitte_in_fester_reihenfolge():
    abschnitte = rahmen_abschnitte({"absprachen": "A", "lehrwerk": "L", "wochenstunden": {"9": 2}}, "9")
    assert [label for label, _ in abschnitte] == ["Wochenstunden", "Lehrwerk", "Absprachen in der Fachschaft"]
    assert rahmen_abschnitte(None, "9") == []


def _draft(**kw):
    return dict(schule="S", fach_code="CH", schulart="G", jahrgangsstufe="9", bp_version="2016",
                kapitel=[], **kw)


def test_zwischenformat_normalisiert_und_prueft():
    d = CurriculumDraftConfirmed(**_draft(rahmen={"wochenstunden": {"9": "2"}, "lehrwerk": " X "}))
    assert d.rahmen == {"wochenstunden": {"9": 2}, "lehrwerk": "X"}
    assert CurriculumDraftConfirmed(**_draft()).rahmen is None
    with pytest.raises(ValueError):
        CurriculumDraftConfirmed(**_draft(rahmen={"wochenstunden": {"9": 99}}))


async def test_pdf_abschnitt():
    from app.context.curriculum_export import _build_pdf_rahmen

    aus = await _build_pdf_rahmen({"jahrgangsstufe": "9",
                                   "rahmen": {"wochenstunden": {"9": 2}, "beschluesse": "- Lektüre A\n- Lektüre B"}})
    assert aus[0] == {"label": "Wochenstunden", "text": "Kl. 9: 2 — verplanbar: 60 Std. (30 je Wochenstunde)"}
    assert aus[1]["label"] == "Beschlüsse der Fachschaft" and "<li>" in aus[1]["html"]
    assert await _build_pdf_rahmen({"jahrgangsstufe": "9"}) == []
