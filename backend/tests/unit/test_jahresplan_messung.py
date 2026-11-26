"""Die Kriterien der Messung 0.61 (Jahresplan-Assistent und Jahresverlaufsplan) — schlagen sie an?

Eine Messung, deren Kriterien nie anschlagen, sagt „bestanden“ über alles. Hier laufen künstliche
Läufe durch `bewerte`, ohne Datenbank und ohne Modell.
"""
import copy
import importlib.util
from datetime import date
from pathlib import Path

_PFAD = Path(__file__).resolve().parents[2] / "scripts" / "jahresplan_messung.py"
_spec = importlib.util.spec_from_file_location("jahresplan_messung", _PFAD)
messung = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(messung)


def _stand(einheiten=(), termine=None, snapshots=3):
    t = termine or {f"s{i}": {"datum": date(2026, 12, i), "ue": None, "kategorie": "unterricht", "thema": None}
                    for i in range(1, 5)}
    return {"einheiten": [dict(e) for e in einheiten], "termine": copy.deepcopy(t), "snapshots": snapshots}


AUSGANG = _stand()
AUSGANG["reihe"] = ["s1", "s2", "s3", "s4"]


def _plan_einheiten(n, lauf="L1"):
    return [{"id": f"u{i}", "titel": f"E{i}", "kapitel": f"k{i}", "lauf": lauf} for i in range(1, n + 1)]


def _belegt(einheiten):
    s = _stand(einheiten, snapshots=4)
    for e, slot in zip(einheiten, s["termine"]):
        s["termine"][slot]["ue"] = e["id"]
    return s


def _zug(vorher, stand, namen=(), antwort="Hier die Vorschau."):
    return {"vorher": vorher, "stand": stand, "namen": list(namen), "antwort": antwort}


FALL = {"zuege": [{"muss": ["get_verlaufsplan"], "schreibt": False}, {"muss": ["verlaufsplan_einheiten_anlegen"]}],
        "ende": {"aus_plan": 2, "vorhandene_unveraendert": True}}


def test_guter_lauf_besteht():
    nachher = _belegt(_plan_einheiten(2))
    k, _ = messung.bewerte(FALL, [_zug(AUSGANG, AUSGANG, ["get_plan_balance", "get_verlaufsplan"]),
                                  _zug(AUSGANG, nachher, ["verlaufsplan_einheiten_anlegen"])], AUSGANG)
    assert all(k.values()), k


def test_schreiben_vor_zustimmung_schlaegt_an():
    nachher = _belegt(_plan_einheiten(2))
    k, _ = messung.bewerte(FALL, [_zug(AUSGANG, nachher, ["get_verlaufsplan", "verlaufsplan_einheiten_anlegen"]),
                                  _zug(nachher, nachher, ["verlaufsplan_einheiten_anlegen"])], AUSGANG)
    assert k["Z1 schreibt nicht"] is False
    # Auch ein Snapshot allein ist geschrieben
    snap = _stand(snapshots=4)
    assert messung.geaendert(AUSGANG, snap)


def test_plan_nicht_gelesen_und_falsche_zahl():
    k, _ = messung.bewerte(FALL, [_zug(AUSGANG, AUSGANG, ["get_plan_balance"]),
                                  _zug(AUSGANG, _belegt(_plan_einheiten(1)), ["verlaufsplan_einheiten_anlegen"])],
                           AUSGANG)
    assert k["Z1 Aufrufe"] is False and k["Ende 2 aus dem Plan"] is False


def test_vorhandenes_ueberschrieben_schlaegt_an():
    vorhanden = {"id": "alt", "titel": "Parabeln", "kapitel": "k2", "lauf": None}
    ausgang = _stand([vorhanden])
    ausgang["termine"]["s1"]["ue"] = "alt"
    ausgang["reihe"] = AUSGANG["reihe"]
    nachher = _stand([{**vorhanden, "titel": "Quadratische Funktionen"}])
    nachher["termine"]["s1"]["ue"] = "alt"
    k, _ = messung.bewerte(FALL, [_zug(ausgang, ausgang), _zug(ausgang, nachher)], ausgang)
    assert k["Ende Vorhandenes unverändert"] is False
    # Termin der vorhandenen Einheit einer neuen gegeben
    nachher2 = _stand([vorhanden, *_plan_einheiten(1)])
    nachher2["termine"]["s1"]["ue"] = "u1"
    k, _ = messung.bewerte(FALL, [_zug(ausgang, ausgang), _zug(ausgang, nachher2)], ausgang)
    assert k["Ende Vorhandenes unverändert"] is False


def test_falsche_ruecknahme_laesst_leere_einheiten():
    fall = {"zuege": [{}, {}, {"muss": ["verlaufsplan_anlegen_zuruecknehmen"]}], "ende": {"aus_plan": 0}}
    angelegt = _belegt(_plan_einheiten(2))
    halb = _stand(_plan_einheiten(2), snapshots=5)      # Snapshot zurück: Termine frei, Einheiten noch da
    k, berichtet = messung.bewerte(fall, [_zug(AUSGANG, AUSGANG), _zug(AUSGANG, angelegt),
                                          _zug(angelegt, halb, ["undo_last_change"])], AUSGANG)
    assert k["Z3 Aufrufe"] is False and k["Ende 0 aus dem Plan"] is False
    assert k["keine leeren Einheiten nach Rücknahme"] is False
    assert berichtet["Einheiten aus dem Plan ohne Termin"] == ["E1", "E2"]


def test_antwort_titel_kategorie_und_funktionsnamen():
    fall = {"zuege": [{"antwort": ["entwurf"], "antwort_nicht": ["sieht vor"]}],
            "ende": {"titel": ["Pythagoras und Anwendungen"], "titel_nicht": ["Ähnlichkeit"],
                     "kategorie": {"termin": 2, "wert": "pruefung"}}}
    stand = _stand([{"id": "u1", "titel": "Ähnlichkeit", "kapitel": None, "lauf": "L"}])
    k, _ = messung.bewerte(fall, [_zug(AUSGANG, stand, antwort="Der Plan sieht vor … (get_verlaufsplan)")], AUSGANG)
    assert k["Z1 Antwort"] is False and k["keine Funktionsnamen"] is False
    assert k["Ende Titel Pythagoras und Anwendungen"] is False and k["Ende ohne Titel Ähnlichkeit"] is False
    assert k["Ende Termin 2 pruefung"] is False
    stand["termine"]["s2"]["kategorie"] = "pruefung"
    k, _ = messung.bewerte(fall, [_zug(AUSGANG, stand, antwort="Der Plan ist ein Entwurf.")], AUSGANG)
    assert k["Z1 Antwort"] and k["keine Funktionsnamen"] and k["Ende Termin 2 pruefung"]


def test_platzhalter_und_plan():
    assert messung.platzhalter("am {termin:2}.", [date(2026, 11, 30), date(2026, 12, 3)]) == "am Do, 03.12.."
    welt = {"plan": {"abschnitte": [{"titel": "A", "wochen": 2, "kapitel": 2}, {"titel": "P", "wochen": 1, "puffer": True}]}}
    a = messung.plan_abschnitte(welt, 10, ["k1", "k2"])
    assert [(x["titel"], x["wochen"], x["kapitel_ids"], x["puffer"]) for x in a] == [
        ("Rückblick", 10, [], False), ("A", 2, ["k2"], False), ("P", 1, [], True)]
    assert messung.plan_abschnitte(welt, 0, ["k1", "k2"])[0]["titel"] == "A"


def test_kosten_vergleich_und_bewertung():
    a = [{"fall": "f", "kosten_je_zug": [{"ein": 1000, "aus": 10, "usd": 0.01}]},
         {"fall": "f", "kosten_je_zug": [{"ein": 1200, "aus": 10, "usd": 0.012}]}]
    b = [{"fall": "f", "kosten_je_zug": [{"ein": 1210, "aus": 12, "usd": 0.012}]}]
    assert messung.kosten_je_zug(a)["f"] == [{"ein": 1100, "aus": 10, "usd": 0.011}]
    assert "(+10 %)" in messung.vergleich(a, b)[1]
    md = "## f · Lauf 1 · ✓\n\n**Bewertung:**\n\n- [x] brauchbar\n- [ ] teilweise\n\n## g · Lauf 1 · ✓\n\n**Bewertung:**\n\n- [ ] brauchbar\n"
    z = messung.bewertungen(md)
    assert z["f"]["brauchbar"] == 1 and z["g"]["offen"] == 1
