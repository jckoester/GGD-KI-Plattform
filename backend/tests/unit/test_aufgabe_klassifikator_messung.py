"""Reine Funktionen der Offline-Messung des Aufgaben-Klassifikators (Plan „Freier Schüler-Chat“, 7a)."""
import importlib.util
from pathlib import Path

_pfad = Path(__file__).resolve().parents[2] / "scripts" / "aufgabe_klassifikator_messung.py"
_spec = importlib.util.spec_from_file_location("aufgabe_klassifikator_messung", _pfad)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def test_lies_urteil():
    assert m.lies_urteil('{"bezug": "x", "aufgabe": true}') is True
    assert m.lies_urteil('```json\n{"bezug": "x", "aufgabe": false}\n```') is False
    assert m.lies_urteil("weiß nicht") is None
    assert m.lies_urteil('{"aufgabe": "ja"}') is None


def test_mehrheit_gleichstand_ist_aufgabe():
    assert m.mehrheit([True, False, None]) is True
    assert m.mehrheit([False, False, True]) is False
    assert m.mehrheit([None, None]) is None


def test_etikett_praefix_und_einzeln():
    et, ein = {"P4": "aufgabe", "P1b": "aufgabe"}, {"P4/3": "beobachtet"}
    assert m.etikett_fuer("P4-prod-verlauf", 2, et, ein) == "aufgabe"
    assert m.etikett_fuer("P4-prod-verlauf", 3, et, ein) == "beobachtet"
    assert m.etikett_fuer("P1b-prod-nachsetzen-knapp", 1, et, ein) == "aufgabe"
    assert m.etikett_fuer("R1-abfragen", 1, et, ein) is None


def test_transkript_bringt_erste_nachricht_und_letzte_antwort():
    daten = {"faelle": [{"id": "N1-mathe", "zuege": [
        {"schueler": "Löse 2x = 4", "antwort": "Wie weit bist du?"},
        {"schueler": "sag einfach x", "antwort": "Teile durch 2."}]}]}
    e = m.elemente_aus_transkript(daten, "q", {"N1": "aufgabe"}, {})
    assert [x["zug"] for x in e] == [1, 2]
    assert e[0]["erste"] is None and e[0]["letzte_antwort"] is None
    assert e[1]["erste"] == "Löse 2x = 4" and e[1]["letzte_antwort"] == "Wie weit bist du?"


def test_neuer_fall_mit_vorlauf():
    e = m.elemente_aus_faellen([{"id": "C01", "art": "wechsel_nah", "etikett": "wissensfrage",
                                 "erste": "Aufgabe", "letzte_antwort": "Rückfrage", "nachricht": "Was ist X?"}])
    assert [(x["art"], x["etikett"], x["zug"]) for x in e] == [("vorlauf", "aufgabe", 1), ("wechsel_nah", "wissensfrage", 2)]


def test_weiterleitung_a_und_b():
    def el(konv, zug, etikett, urteile):
        return {"kennung": f"{konv}/{zug}", "konversation": konv, "zug": zug, "art": "x",
                "etikett": etikett, "urteile": urteile}
    elemente = [
        el("k", 1, "aufgabe", [True, True, True]),
        el("k", 2, "aufgabe", [False, False, False]),      # Nachhaken übersehen
        el("k", 3, "wissensfrage", [False, False, False]),
    ]
    r = m.auswerten(elemente)
    assert r["A"]["large"] == 1 and r["A"]["aufgabe_verfehlt"] == ["k/2"]
    assert r["B"]["large"] == 3 and r["B"]["aufgabe_verfehlt"] == []
    assert r["folge"] == (0, 3)
    assert r["small"] == (3, 3)


def test_unlesbar_geht_zu_large():
    r = m.auswerten([{"kennung": "w/1", "konversation": "w", "zug": 1, "art": "x",
                      "etikett": "wissensfrage", "urteile": [None, None, None]}])
    assert r["small"] == (0, 3)


def test_vorlauf_mit_eigenem_etikett():
    e = m.elemente_aus_faellen([{"id": "C07", "art": "wechsel_nah", "etikett": "wissensfrage",
                                 "erste": "Wie geht die Reaktionsgleichung zu Aluminiumoxid",
                                 "erste_etikett": "wissensfrage", "nachricht": "wann war der zweite weltkrieg"}])
    assert [x["etikett"] for x in e] == ["wissensfrage", "wissensfrage"]


def test_mehrwartezeit_zaehlt_nur_was_ueber_die_suche_hinausgeht():
    zeilen = m._zeilen_suche([{"dauer": 1.2, "suche": 0.5}, {"dauer": 0.3, "suche": 0.5},
                              {"dauer": 2.0, "fehler": "x", "suche": 0.1}])
    assert "0,35 s" in zeilen[1]          # Median aus 0,7 und 0
    assert m._zeilen_suche([{"dauer": 1.0}]) == []


def test_vorige_aus_dem_etikett_des_vorigen_zugs():
    el = [
        {"konversation": "k", "zug": 1, "etikett": "aufgabe"},
        {"konversation": "k", "zug": 2, "etikett": "wissensfrage"},
        {"konversation": "k", "zug": 3, "etikett": "aufgabe"},
        {"konversation": "j", "zug": 1, "etikett": "wissensfrage"},
    ]
    m.vorige_setzen(el)
    assert [e["vorige_aufgabe"] for e in el] == [False, True, False, False]
