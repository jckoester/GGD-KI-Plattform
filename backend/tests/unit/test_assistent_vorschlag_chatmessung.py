"""Reine Funktionen der Chat-Messung „Assistent vorschlagen“ (Päckchen C2, Schritt 7)."""
import importlib.util
import sys
from pathlib import Path

_SKRIPTE = Path(__file__).resolve().parents[2] / "scripts"
_spec = importlib.util.spec_from_file_location("assistent_vorschlag_chatmessung",
                                               _SKRIPTE / "assistent_vorschlag_chatmessung.py")
M = importlib.util.module_from_spec(_spec)
sys.modules["assistent_vorschlag_chatmessung"] = M
_spec.loader.exec_module(M)


def test_ergebnis_im_assistenten():
    namen = {17: "Reaktionsgleichungen"}
    assert M.ergebnis_im_assistenten(None, namen) == ("bleiben", None)
    assert M.ergebnis_im_assistenten([{"assistant_id": 0, "art": "beenden"}], namen) == ("beenden", None)
    assert M.ergebnis_im_assistenten([{"assistant_id": 17, "art": "specific"}], namen) == (
        "wechsel", "Reaktionsgleichungen")


def test_rechtzeitig():
    faelle = [
        {"debug": {"klassifikator": "{}"}, "t_message": 5.0, "t_vorschlag": 6.5},
        {"debug": {"abgebrochen": "Zeitlimit"}, "t_message": 3.0, "t_vorschlag": None},
        {"debug": {"band": []}, "t_message": 2.0, "t_vorschlag": None},       # kein Aufruf
        {"debug": None},
    ]
    r = M.rechtzeitig(faelle)
    assert (r["aufrufe"], r["zeitlimit"], r["anteil_rechtzeitig"], r["nach_antwort"]) == (2, 1, 0.5, [1.5])


def test_verweis_im_ersten_satz():
    assert M.verweist("Dafür gibt es den Assistenten für Lernen und Prüfungsvorbereitung. Trotzdem …",
                      "Lernen und Prüfungsvorbereitung")
    assert not M.verweist("Gute Frage. Der Assistent für Lernen und Prüfungsvorbereitung hilft.",
                          "Lernen und Prüfungsvorbereitung")
