"""Reine Funktionen der Gate-Messung „Assistent vorschlagen“, Stufe 2 (Päckchen C2, Schritt 1)."""
import importlib.util
import sys
from pathlib import Path

_SKRIPTE = Path(__file__).resolve().parents[2] / "scripts"
_spec = importlib.util.spec_from_file_location("assistent_vorschlag_klassifikator",
                                               _SKRIPTE / "assistent_vorschlag_klassifikator.py")
K = importlib.util.module_from_spec(_spec)
sys.modules["assistent_vorschlag_klassifikator"] = K
_spec.loader.exec_module(K)
Abstand = K.C1.Abstand


def test_im_band_naechster_zuerst():
    ab = {"a": Abstand(0.45, 1), "b": Abstand(0.38, 1), "c": Abstand(0.55, 1)}
    assert K.im_band(ab, 0.50) == ["b", "a"]


def test_lies_antwort_robust():
    erlaubt = {1: "specific", 2: "specific", 3: "fallback"}
    assert K.lies_antwort('```json\n{"spezifisch": [1, "2", 2, 9], "rueckfall": [3, 1]}\n```', erlaubt) == ([1, 2], [3])
    assert K.lies_antwort("keiner passt", erlaubt) == ([], [])
    assert K.lies_antwort('{"spezifisch": [3]}', erlaubt) == ([], [])     # falsche Art


def test_auswahl_rueckfall_aus_fallbacks_sonst_klassifikator():
    erlaubt = {1: "specific", 2: "specific", 5: "fallback", 6: "fallback"}
    assert K.auswahl([1], [6], {1: [5]}, erlaubt) == [1, 5]               # fallbacks des Treffers
    assert K.auswahl([], [6, 5], {}, erlaubt) == [6, 5]                    # nur Rückfall
    assert K.auswahl([1, 2], [], {1: [7]}, erlaubt) == [1, 2]              # 7 ist kein Kandidat


def test_bewerte():
    art = {"S": "specific", "R": "fallback"}
    faelle = [{"art": "positiv", "soll": ["S"], "nicht": [], "gewaehlt": ["S", "R"], "kennung": "p"}] * 5 + [
        {"art": "positiv", "soll": ["R"], "nicht": [], "gewaehlt": ["R"], "kennung": "r"}] * 5 + [
        {"art": "alltag", "soll": [], "nicht": [], "gewaehlt": [], "kennung": "a"},
        {"art": "nachbar", "soll": [], "nicht": ["S"], "gewaehlt": ["S"], "kennung": "n"}]
    e = K.bewerte(faelle, art)
    assert (e["K1"], e["K2"], e["K3"], e["K4"]) == (True, True, True, True)
    e = K.bewerte(faelle + [{"art": "begriff", "soll": [], "nicht": [], "gewaehlt": ["R"], "kennung": "b"}], art)
    assert not e["K3"] and e["stoer"] == ["b"]
