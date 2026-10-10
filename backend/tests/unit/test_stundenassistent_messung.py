"""Die Kriterien der Messung zum Stundenassistenten (0.15, Schritt 6) — erkennen sie Fehlgriffe?

Eine Messung, deren Kriterien nie anschlagen, sagt „3/3 bestanden" über alles. Hier laufen
künstliche Läufe durch `bewerte`: je ein richtiger und je ein Fehlgriff pro Kriterium.
"""
import copy
import importlib.util
from pathlib import Path

import pytest

_PFAD = Path(__file__).resolve().parents[2] / "scripts" / "stundenassistent_messung.py"
_spec = importlib.util.spec_from_file_location("stundenassistent_messung", _PFAD)
messung = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(messung)

STUNDE = "s-1"
AUSGANG = {"entwuerfe": {STUNDE: {"titel": "Potenzen", "metadata": {"phasen": [
    {"id": "a", "name": "Einstieg", "dauer_min": 10},
    {"id": "b", "name": "Sicherung wird HA", "dauer_min": None},
]}}}, "slots": {}, "kanten": set()}


def _zug(werkzeuge, *, phasen=None, antwort="Soll ich das so übernehmen?", bezug=None, neu=False):
    stand = copy.deepcopy(AUSGANG)
    if phasen is not None:
        stand["entwuerfe"][STUNDE]["metadata"]["phasen"] = phasen
    if neu:
        stand["entwuerfe"]["s-neu"] = {"titel": "Neue Stunde", "metadata": {"phasen": []}}
    return {"werkzeuge": [{"tool": w} for w in werkzeuge], "stand": stand,
            "antwort": antwort, "bezug": bezug}


FALL = {"id": "x", "stunde": {}, "zuege": ["…", "Ja"], "zustimmung_ab": 2, "neue_phasen_hoechstens": 1}
GUT = [
    {"id": "a", "name": "Einstieg", "dauer_min": 10, "beschreibung": "Neu"},
    {"id": "b", "name": "Sicherung wird HA", "dauer_min": None},
    {"name": "Tafelbild", "dauer_min": 5},
]


def _bewerte(zuege, fall=FALL, **kw):
    return messung.bewerte(fall, AUSGANG, zuege, stunde=kw.pop("stunde", STUNDE), **kw)


def test_ein_guter_lauf_besteht():
    k = _bewerte([_zug(["get_lesson_detail"]), _zug(["update_lesson_phases"], phasen=GUT)])
    assert all(k.values()), k
    assert set(k) == {"zuerst_gelesen", "nicht_ohne_zustimmung", "schreibt_nach_zustimmung",
                      "kennungen_erhalten", "skizze_ohne_dauer"}


@pytest.mark.parametrize("zuege,kriterium", [
    # nicht zuerst gelesen
    ([_zug(["search_context_nodes", "get_lesson_detail"]), _zug(["update_lesson_phases"], phasen=GUT)],
     "zuerst_gelesen"),
    ([_zug([]), _zug(["update_lesson_phases"], phasen=GUT)], "zuerst_gelesen"),
    # vor der Zustimmung geschrieben — am Werkzeug und am Stand
    ([_zug(["get_lesson_detail", "update_lesson_phases"], phasen=GUT), _zug([], phasen=GUT)],
     "nicht_ohne_zustimmung"),
    # einen Entwurf angelegt
    ([_zug(["get_lesson_detail"], neu=True), _zug(["update_lesson_phases"], phasen=GUT)],
     "nicht_ohne_zustimmung"),
    # nach der Zustimmung nicht geschrieben
    ([_zug(["get_lesson_detail"]), _zug(["get_lesson_detail"])], "schreibt_nach_zustimmung"),
    # Kennungen verloren: alles neu
    ([_zug(["get_lesson_detail"]), _zug(["update_lesson_phases"], phasen=[
        {"name": "Einstieg", "dauer_min": 10}, {"name": "Sicherung wird HA", "dauer_min": None}])],
     "kennungen_erhalten"),
    # Minuten für die Skizze erfunden
    ([_zug(["get_lesson_detail"]), _zug(["update_lesson_phases"], phasen=[
        {"id": "a", "name": "Einstieg", "dauer_min": 10}, {"id": "b", "name": "Sicherung wird HA", "dauer_min": 5}])],
     "skizze_ohne_dauer"),
])
def test_fehlgriffe_werden_erkannt(zuege, kriterium):
    assert _bewerte(zuege)[kriterium] is False


def test_ohne_bezug_waehlen_und_nachfragen():
    fall_waehlt = {"id": "w", "zuege": ["…"], "waehlt": {}}
    gut = _bewerte([_zug(["finde_stunde", "waehle_stunde"], bezug="ziel")], fall_waehlt, stunde=None, ziel="ziel")
    assert gut == {"zuerst_gelesen": True, "nicht_ohne_zustimmung": True, "waehlt_den_termin": True}
    falsch = _bewerte([_zug(["finde_stunde", "waehle_stunde"], bezug="anderer")], fall_waehlt,
                      stunde=None, ziel="ziel")
    assert falsch["waehlt_den_termin"] is False

    fall_frage = {"id": "f", "zuege": ["…"], "nachfrage": True}
    assert _bewerte([_zug(["finde_stunde"], antwort="Welche meinst du?")], fall_frage, stunde=None)["fragt_nach"]
    # selbst gewählt statt gefragt
    assert not _bewerte([_zug(["finde_stunde", "waehle_stunde"], bezug="x")], fall_frage, stunde=None)["fragt_nach"]
    # nicht gefragt
    assert not _bewerte([_zug(["finde_stunde"], antwort="Ich habe nichts gefunden.")], fall_frage,
                        stunde=None)["fragt_nach"]
