"""Der Deckel für Namensträger in `scripts/search_eval.py` (0.14, 07.10.2026).

Der Wächter soll verhindern, dass eine **thematische** Anfrage von Namensträgern
überschwemmt wird. Bis 07.10. galt jeder Fall mit `fach:` als thematisch — und der
Deckel riss bei „Elektronenpaarbindung", einer Frage, die einen Knoten beim Namen nennt.
"""
import importlib.util
from pathlib import Path

SKRIPT = Path(__file__).resolve().parents[2] / "scripts" / "search_eval.py"


def _laden():
    """Über den Dateipfad laden — `backend/scripts/` ist bewusst kein Paket."""
    spec = importlib.util.spec_from_file_location("search_eval", SKRIPT)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


M = _laden()


def _treffer(titel):
    return M.Treffer(id=titel, titel=titel, content_type="begriff", fach="Chemie", nr="", sim=0.0)


def test_namensfrage_ist_nicht_thematisch():
    namen = [_treffer(t) for t in ("Elektronenpaarbindung", "Elektronenpaarbindung",
                                    "polare Elektronenpaarbindung",
                                    "Polare und unpolare Elektronenpaarbindung")]
    fall = M.Fall(frage="Elektronenpaarbindung", fach="Chemie")
    assert not M.ist_thematisch(fall, namen)


def test_auch_in_frageform():
    """Die Suchschicht liest den Begriff aus der Frage heraus — der Prüfsatz ebenso."""
    fall = M.Fall(frage="Was ist eine Elektronenpaarbindung?", fach="Chemie")
    assert not M.ist_thematisch(fall, [_treffer("Elektronenpaarbindung")])


def test_thematische_frage_bleibt_thematisch():
    """Teiltreffer im Titel, aber kein Knoten heißt so — genau der Fall des Wächters."""
    fall = M.Fall(frage="Wie berechnet man den Flächeninhalt eines Kreises?", fach="Mathematik")
    assert M.ist_thematisch(fall, [_treffer("Flächeninhalt"), _treffer("Kreis")])


def test_ohne_fach_nie_thematisch():
    assert not M.ist_thematisch(M.Fall(frage="Kreis"), [])
