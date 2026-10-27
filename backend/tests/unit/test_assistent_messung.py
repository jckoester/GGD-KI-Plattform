"""Allgemeines Messskript für Schüler-Assistenten (`scripts/assistent_messung.py`, 26.10.2026)."""
import importlib.util
from pathlib import Path

import pytest

_SKRIPTE = Path(__file__).resolve().parents[2] / "scripts"
_spec = importlib.util.spec_from_file_location("assistent_messung", _SKRIPTE / "assistent_messung.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

SZENARIEN = sorted((_SKRIPTE / "szenarien").glob("*.yaml"))
MIT_KOPF = [p for p in SZENARIEN if p.name in ("stoechiometrie.yaml", "reaktionsgleichung.yaml", "nw_aufgaben.yaml")]


@pytest.mark.parametrize("datei", MIT_KOPF, ids=lambda p: p.name)
def test_kopf_vollstaendig_und_prompt_vorhanden(datei):
    profil, faelle = M.profil_laden(datei)
    assert profil["prompt"].is_file()
    assert profil["min_grade"] <= profil["max_grade"]
    assert faelle
    # Jede Stufe eines Falls liegt in den Stufen des Assistenten — sonst misst der Fall nur,
    # dass die Klassenstufen-Regel (C1) greift.
    assert all(profil["min_grade"] <= f["stufe"] <= profil["max_grade"] for f in faelle)


def test_pruefwerte_sind_text(tmp_path):
    datei = tmp_path / "s.yaml"
    datei.write_text(
        "assistent: {name: X, prompt: config/prompts/stoechiometrie_assistent.md}\n"
        "faelle:\n- id: a\n  titel: t\n  stufe: 9\n  stufenfremd: [Elektron]\n"
        "  zuege:\n  - schueler: s\n    verboten: [36, 0.5]\n",
        encoding="utf-8",
    )
    profil, faelle = M.profil_laden(datei)
    assert faelle[0]["zuege"][0]["verboten"] == ["36", "0.5"]
    assert profil["ohne"] == M.VORGABE_OHNE and profil["modell"] == M.VORGABE_MODELL


def test_kopf_ohne_name_bricht_ab(tmp_path):
    datei = tmp_path / "s.yaml"
    datei.write_text("assistent: {prompt: x.md}\nfaelle: []\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="name"):
        M.profil_laden(datei)


def test_stufenvorgriff_trifft_zusammensetzungen():
    assert M.vorgriffe("Magnesium gibt Elektronen ab.", ["Elektron"])
    assert not M.vorgriffe("Der elektrische Strom.", ["Elektron"])


def test_kostenzusammenfassung_und_promptanteil():
    zuege = [("a", {"kosten": {"ein": 6000, "aus": 200, "usd": 0.006}}),
             ("a", {"kosten": {"ein": 4000, "aus": 100, "usd": 0.004}})]
    text = "\n".join(M.kosten_zusammenfassung({"prompt_tokens": 2000}, zuege))
    assert "0.0100 USD für 2 Züge" in text
    assert "Mittel 5000" in text
    assert "etwa 40%" in text


def test_kosten_ohne_angaben():
    assert "keine Angaben" in M.kosten_zusammenfassung({}, [("a", {})])[0]
