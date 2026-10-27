"""Reine Funktionen von `scripts/assistent_vorschlag_messung.py` (C1 Schritt 5, 27.10.2026)."""
import importlib.util
import sys
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location(
    "assistent_vorschlag_messung", Path(__file__).resolve().parents[2] / "scripts/assistent_vorschlag_messung.py")
M = importlib.util.module_from_spec(_spec)
# `@dataclass` sucht sein Modul in sys.modules — beim Laden über den Pfad vorher eintragen.
sys.modules[_spec.name] = M
_spec.loader.exec_module(M)

A = M.Abstand
ART = {"stoe": "specific", "rg": "specific", "nw": "fallback"}


def test_kosinus_distanz():
    d = M.kosinus_distanz(np.array([1.0, 0.0]), np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]))
    assert np.allclose(d, [0.0, 1.0, 2.0])
    assert M.kosinus_distanz(np.array([1.0]), np.empty((0, 1))).size == 0


def test_gegenbeispiel_regel():
    a = A(bsp=0.40, gegen=0.30)
    assert M.trifft(a, 0.45, gegen_regel=False)
    assert not M.trifft(a, 0.45, gegen_regel=True)


def test_auswahl_hoechstens_zwei_je_art_bester_zuerst_ohne_aktuellen():
    ab = {"stoe": A(0.40, 1), "rg": A(0.30, 1), "nw": A(0.50, 1)}
    assert M.auswahl(ab, ART, 0.45, 0.55, False) == ["rg", "stoe", "nw"]
    assert M.auswahl(ab, ART, 0.45, 0.45, False) == ["rg", "stoe"]
    assert M.auswahl(ab, ART, 0.45, 0.55, False, ohne="rg") == ["stoe", "nw"]


def _fall(art, soll=(), nicht=(), **ab):
    return {"art": art, "soll": list(soll), "nicht": list(nicht), "kennung": art,
            "abstaende": {k: A(v, 1.0) for k, v in ab.items()}}


def test_bewertung_k1_k3_k4():
    faelle = ([_fall("positiv", ["stoe"], stoe=0.3)] * 4 + [_fall("positiv", ["stoe"], stoe=0.6)]
              + [_fall("positiv", ["rg"], rg=0.3)] * 5
              + [_fall("nachbar", ["rg"], ["stoe"], stoe=0.6, rg=0.3)] * 5
              + [_fall("nachbar", ["stoe"], ["rg"], stoe=0.3, rg=0.6)] * 5)
    assert M.bewerte_spezifisch(faelle, 0.4, False, ART)["ok"]
    # Eine Begriffsfrage über der Schwelle kippt K3.
    stoer = M.bewerte_spezifisch(faelle + [_fall("begriff", stoe=0.35)], 0.4, False, ART)
    assert not stoer["ok"] and not stoer["k_stoer"]
    # Zwei Nachbar-Fehltreffer bei fünf Nachbarn kippen K4.
    zwei = [_fall("nachbar", ["rg"], ["stoe"], stoe=0.35, rg=0.3)] * 2
    assert not M.bewerte_spezifisch(faelle[:-5] + zwei + faelle[-3:], 0.4, False, ART)["k_nachbar"]


def test_entscheidung_im_assistenten():
    kw = dict(s_spez=0.45, s_rueck=0.0, gegen_regel=False, s_beenden=0.5)
    nah = {"stoe": A(0.40, 1), "rg": A(0.20, 1), "nw": A(0.6, 1)}
    assert M.entscheidung_im_assistenten(nah, ART, "stoe", marge=0.1, **kw) == ("wechsel", "rg")
    assert M.entscheidung_im_assistenten(nah, ART, "stoe", marge=0.25, **kw) == ("bleiben", None)
    weit = {"stoe": A(0.60, 1), "rg": A(0.55, 1), "nw": A(0.6, 1)}
    assert M.entscheidung_im_assistenten(weit, ART, "stoe", marge=0.0, **kw) == ("beenden", None)


def test_bereiche():
    werte = [{"schwelle": s, "ok": ok} for s, ok in ((0.3, False), (0.31, True), (0.32, True), (0.33, False), (0.34, True))]
    assert M.bereiche(werte) == [(0.31, 0.32), (0.34, 0.34)]
