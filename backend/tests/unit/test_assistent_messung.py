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
    assert "Mittel 0.0050 USD/Zug aus 2 vollständigen Zügen, zusammen 0.0100 USD" in text
    assert "Mittel 5000" in text
    assert "etwa 40%" in text


def test_kosten_laut_litellm_steht_zuerst():
    zuege = [("a", {"kosten": {"ein": 6000, "aus": 200, "usd": 0.006}}), ("a", {})]
    zeilen = M.kosten_zusammenfassung({"kosten_litellm": 0.012}, zuege)
    assert zeilen[0].startswith("- **Kosten laut LiteLLM**") and "0.0060 USD/Zug" in zeilen[0]


def test_kosten_teilwerte_zaehlen_nicht_ins_mittel():
    """Lauf 2, E1: Ein Teilwert („unvollstaendig“) verzerrt das Mittel nicht; hochgerechnet wird."""
    zuege = [("a", {"kosten": {"ein": 6000, "aus": 200, "usd": 0.006}}),
             ("a", {"kosten": {"ein": 6000, "aus": 200, "usd": 0.0001, "status": "unvollstaendig"}}),
             ("a", {"kosten": {"ein": 6000, "aus": 200, "usd": None, "status": "unvollstaendig"}})]
    text = "\n".join(M.kosten_zusammenfassung({}, zuege))
    assert "Mittel 0.0060 USD/Zug aus 1 vollständigen Zügen; 2 unvollständig — hochgerechnet 0.0180 USD" in text


def test_ton_zaehlen():
    assert M.ton_zaehlen("Du musst teilen. Was musst du tun? **fett** und __auch__. Möchtest du weiter?") == {
        "musst": 2, "anhaengsel": 1, "fett": 2}
    # Lauf 3, A2: „du … musst“ im selben Satz; „Möchtest du“ nur am Ende der Antwort.
    assert M.ton_zaehlen("Was du jetzt noch tun musst, ist teilen. Möchtest du das? Dann los.")["musst"] == 1
    assert M.ton_zaehlen("Möchtest du das? Dann los.")["anhaengsel"] == 0
    assert M.ton_zaehlen("") == {"musst": 0, "anhaengsel": 0, "fett": 0}


def test_kosten_ohne_angaben():
    assert "keine Angaben" in M.kosten_zusammenfassung({}, [("a", {})])[0]


def test_operator_zusammenfassung():
    """Päckchen AF: erkannt gegen Soll; `[]` heißt „keiner erwartet“."""
    zuege = [
        ("O1", {"nr": 1, "operator": {"operatoren": ["erläutern"]}, "operator_soll": ["erläutern"]}),
        ("S7", {"nr": 1, "operator": None, "operator_soll": []}),
        ("S6", {"nr": 2, "operator": None, "operator_soll": ["begründen"]}),
        ("R2", {"nr": 1, "operator": None}),
    ]
    assert M.operator_zusammenfassung(zuege) == [
        "- **Operator-Abschnitt:** in 1 Zügen",
        "- **Operator erkannt wie Soll:** 2 von 3 — abweichend: S6 Zug 2",
    ]
    assert M.operator_zusammenfassung([("R2", {"nr": 1})]) == []


def test_operator_soll_wird_text(tmp_path):
    datei = tmp_path / "s.yaml"
    datei.write_text("assistent:\n  name: N\n  prompt: config/prompts/nw_aufgaben_assistent.md\n"
                     "  operator_faecher: [biologie]\nfaelle:\n- id: A\n  titel: T\n  stufe: 7\n"
                     "  zuege:\n  - schueler: x\n    operator: [erläutern]\n", encoding="utf-8")
    profil, faelle = M.profil_laden(datei)
    assert profil["operator_faecher"] == ["biologie"]
    assert faelle[0]["zuege"][0]["operator"] == ["erläutern"]


def test_planung_im_fall_und_im_protokollkopf(tmp_path):
    """Feld `planung` (29.10.2026): Themen werden Text, der Fallkopf nennt die Planungsdaten."""
    datei = tmp_path / "s.yaml"
    datei.write_text(
        "assistent: {name: X, prompt: config/prompts/stoechiometrie_assistent.md}\n"
        "faelle:\n- id: a\n  titel: t\n  stufe: 9\n"
        "  planung: {fach: chemie, einheit: Stoffmenge, themen: [Mol, 2024], klassenarbeit_in_tagen: 5}\n"
        "  zuege:\n  - schueler: s\n",
        encoding="utf-8",
    )
    _, faelle = M.profil_laden(datei)
    planung = faelle[0]["planung"]
    assert planung["themen"] == ["Mol", "2024"]
    zeile = M.planung_text(planung)
    assert "Einheit „Stoffmenge“" in zeile and "Mol · 2024" in zeile and "in 5 Tagen" in zeile
    kopf = {"name": "X", "lauf": "1", "datum": "heute", "modell": "m", "assistent": 1, "fach": "chemie",
            "min_grade": 8, "max_grade": 10, "prompt_datei": "p.md", "prompt": "abc", "import": "—", "ohne": []}
    fall = {"id": "a", "titel": "t", "stufe": 9, "referenz": None, "zuege": [], "planung": planung,
            "planung_block": "## Aktueller Unterricht (X)\n- Klassenarbeit: Mo 3.11. — Umfang: Stoffmenge"}
    text = M.protokoll(kopf, [fall])
    assert "*Planung (Messgruppe mit Gruppenbezug):* " + zeile in text
    assert "Umfang: Stoffmenge" in text
    # Ohne `planung` bleibt der Fallkopf, wie er war.
    assert "Planung" not in M.protokoll(kopf, [fall | {"planung": None, "planung_block": None}])
