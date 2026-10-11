"""Die Kriterien der Messung zum Entfall (0.15, Päckchen A Schritt 8) — erkennen sie Fehlgriffe?

Eine Messung, deren Kriterien nie anschlagen, sagt „kein Fehlgriff" über alles. Hier laufen
künstliche Läufe durch `bewerte`.
"""
import copy
import importlib.util
from datetime import date
from pathlib import Path

_PFAD = Path(__file__).resolve().parents[2] / "scripts" / "entfall_messung.py"
_spec = importlib.util.spec_from_file_location("entfall_messung", _PFAD)
messung = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(messung)

QUELLE, FOLGE, FREI = "q", "f", "x"
#: Wie nach dem Aufbau: Der Aufbau selbst hat schon Snapshots angelegt.
AUFBAU_SNAPSHOTS = 15


def _termin(datum, thema, entwurf=None, kategorie="unterricht", herkunft=None):
    return {"datum": datum, "kategorie": kategorie, "thema": thema, "ue_node_id": "ue" if thema else None,
            "stunde_node_id": entwurf, "anpassung_noetig": "False", "ausfall_herkunft": herkunft,
            "ausfall_vorher": None}


AUSGANG = {
    QUELLE: _termin(date(2026, 10, 15), "Potenzgesetze", "e-1"),
    FOLGE: _termin(date(2026, 10, 19), "Potenzen von Potenzen"),
    FREI: _termin(date(2026, 11, 19), None),
}


def _zug(plan=None, snapshots=AUFBAU_SNAPSHOTS, werkzeuge=()):
    return {"plan": plan or copy.deepcopy(AUSGANG), "snapshots": snapshots,
            "werkzeuge": [{"tool": w} for w in werkzeuge]}


def _bewerte(*zuege):
    return messung.bewerte(AUSGANG, AUFBAU_SNAPSHOTS, list(zuege), QUELLE)


def _verschoben(kategorie="unterricht", herkunft=None):
    """Thema und Entwurf der Quelle auf die Folgestunde, die Quelle leer."""
    plan = copy.deepcopy(AUSGANG)
    plan[FOLGE].update(thema="Potenzgesetze", stunde_node_id="e-1")
    plan[QUELLE].update(thema=None, ue_node_id=None, stunde_node_id=None, kategorie=kategorie,
                        ausfall_herkunft=herkunft)
    return plan


def test_der_fehler_vom_24_09_ist_ein_fehlgriff():
    """Nur verschoben, keine Kategorie — der Quelltermin bleibt `unterricht`."""
    k = _bewerte(_zug(), _zug(_verschoben(), AUFBAU_SNAPSHOTS + 1, ["apply_plan_operations"]))
    assert k["geschrieben"] and k["fehlgriff"]
    assert not k["ausfall"]


def test_ausfall_eingetragen_ist_keiner():
    k = _bewerte(_zug(), _zug(_verschoben("ausfall", "assistent"), AUFBAU_SNAPSHOTS + 1))
    assert k["geschrieben"] and not k["fehlgriff"]
    assert k["ausfall"] and k["herkunft_assistent"]
    assert k["wohin"] == "Thema → 19.10. · Entwurf → 19.10."
    assert not k["vor_zustimmung"]


def test_ohne_aenderung_nicht_geschrieben_und_kein_fehlgriff():
    """⚠️ Die Snapshots des Aufbaus zählen nicht — im ersten Probelauf galt jeder Lauf als
    geschrieben, und einer ohne Änderung wäre ein Fehlgriff gewesen."""
    k = _bewerte(_zug(), _zug())
    assert not k["geschrieben"] and not k["fehlgriff"]


def test_ein_snapshot_allein_zaehlt_als_geschrieben():
    """Ein angewandter Stapel ohne sichtbare Änderung (etwa nur `mark_needs_adjustment` auf
    denselben Wert) ist trotzdem geschrieben — und die Quelle blieb `unterricht`."""
    k = _bewerte(_zug(), _zug(snapshots=AUFBAU_SNAPSHOTS + 1))
    assert k["geschrieben"] and k["fehlgriff"]


def test_falsche_kategorie_ist_nach_dem_kriterium_kein_fehlgriff():
    """`puffer` statt `ausfall` (Probelauf 11.10.) — gezählt wird es über `kategorie`."""
    k = _bewerte(_zug(), _zug(_verschoben("puffer"), AUFBAU_SNAPSHOTS + 1))
    assert not k["fehlgriff"] and not k["ausfall"]
    assert k["kategorie"] == "puffer"


def test_vor_der_zustimmung_geschrieben():
    plan = _verschoben("ausfall", "assistent")
    k = _bewerte(_zug(plan, AUFBAU_SNAPSHOTS + 1), _zug(plan, AUFBAU_SNAPSHOTS + 1))
    assert k["vor_zustimmung"]


def test_termine_ueber_wochen():
    gruppe = {"von": date(2026, 10, 12), "bis": date(2026, 10, 22),
              "termine": [{"wochentag": 0, "start": 1, "stunden": 2}, {"wochentag": 3, "start": 3, "stunden": 1}]}
    assert messung.termine(gruppe) == [(date(2026, 10, 12), 1, 2), (date(2026, 10, 15), 3, 1),
                                       (date(2026, 10, 19), 1, 2), (date(2026, 10, 22), 3, 1)]
