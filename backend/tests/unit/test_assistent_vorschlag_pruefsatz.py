"""Prüfsatz `scripts/szenarien/assistent_vorschlag.yaml` (Päckchen C1, Schritt 0, 27.10.2026).

Hält fest, was das Kriterium F6 voraussetzt: genug Fälle je Art, gültige Assistenten-Namen,
auflösbare Quellen — und **dass kein Prüftext unter den eingebetteten Beispielen steht**, sonst
misst Schritt 5 Abstand null.
"""
from pathlib import Path

import pytest
import yaml

WURZEL = Path(__file__).resolve().parents[3]
SZENARIEN = WURZEL / "backend/scripts/szenarien"
SATZ = yaml.safe_load((SZENARIEN / "assistent_vorschlag.yaml").read_text(encoding="utf-8"))
SEED = {e["name"]: e for e in yaml.safe_load(
    (WURZEL / "config/assistants.example.yaml").read_text(encoding="utf-8"))["assistants"]}
SPEZ = SATZ["assistenten"]["spezifisch"]
RUECK = SATZ["assistenten"]["rueckfall"]
ALLE = set(SPEZ) | set(RUECK)


def _text(fall: dict) -> str:
    if "text" in fall:
        return fall["text"]
    datei, fid = fall["quelle"].split("#")
    faelle = yaml.safe_load((SZENARIEN / datei).read_text(encoding="utf-8"))["faelle"]
    return next(f for f in faelle if f["id"] == fid)["zuege"][0]["schueler"]


def test_assistenten_stehen_im_seed_mit_passender_art():
    for name in SPEZ:
        assert SEED[name]["suggest"] == "specific"
    for name in RUECK:
        assert SEED[name]["suggest"] == "fallback"


@pytest.mark.parametrize("fall", SATZ["faelle"], ids=lambda f: f.get("quelle") or f["text"][:30])
def test_fall_ist_wohlgeformt(fall):
    assert _text(fall).strip()
    for feld in ("soll", "darf", "nicht"):
        assert set(fall.get(feld) or []) <= ALLE, feld
    assert not set(fall.get("soll") or []) & set(fall.get("nicht") or [])
    assert not set(fall.get("darf") or []) & set(fall.get("nicht") or [])
    assert fall["art"] in {"positiv", "nachbar", "begriff", "alltag", "fachfremd"}
    assert isinstance(fall["stufe"], int)


def test_mengen_nach_f6():
    faelle = SATZ["faelle"]
    for name in SPEZ + RUECK:
        positiv = [f for f in faelle if f["art"] == "positiv" and name in f["soll"]]
        assert len(positiv) >= 5, name
        gegen = [f for f in faelle if f["art"] in ("nachbar", "fachfremd") and name in (f.get("nicht") or [])]
        assert len(gegen) >= 5, name
    assert len([f for f in faelle if f["art"] in ("begriff", "alltag")]) >= 10


def test_kein_pruefsatz_text_unter_den_eingebetteten_beispielen():
    eingebettet = {t.strip() for e in SEED.values()
                   for t in (e.get("trigger_examples") or []) + (e.get("trigger_counterexamples") or [])}
    texte = [_text(f).strip() for f in SATZ["faelle"]] + [f["text"].strip() for f in SATZ["in_assistent"]]
    assert not set(texte) & eingebettet


def test_in_assistent():
    arten = {"bleiben": 0, "wechsel": 0, "beenden": 0}
    for f in SATZ["in_assistent"]:
        assert f["aktuell"] in ALLE
        arten[f["erwartet"]] += 1
        assert ("wechsel_zu" in f) == (f["erwartet"] == "wechsel")
        if "wechsel_zu" in f:
            assert f["wechsel_zu"] in ALLE and f["wechsel_zu"] != f["aktuell"]
    # K5-neu (29.10.2026): „beenden“ wird nicht mehr erwartet, höchstens erlaubt (`darf`).
    assert arten["bleiben"] >= 3 and arten["wechsel"] >= 3
    for f in SATZ["in_assistent"]:
        assert set(f.get("darf") or []) <= {"beenden", "wechsel"}
