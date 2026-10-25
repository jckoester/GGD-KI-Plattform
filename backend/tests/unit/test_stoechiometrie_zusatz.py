"""Zusatzauswertung der Stöchiometrie-Messläufe (`scripts/stoechiometrie_zusatz.py`)."""
import importlib.util
import json
from pathlib import Path

_SKRIPTE = Path(__file__).resolve().parents[2] / "scripts"
_spec = importlib.util.spec_from_file_location("stoechiometrie_zusatz", _SKRIPTE / "stoechiometrie_zusatz.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


def test_frage_am_ende_ohne_frage_davor():
    f = M.frageform("Die Stoffmenge stimmt. Welche Masse ergibt sich daraus?")
    assert (f["fragezeichen"], f["letzter_satz_frage"], f["frage_davor"]) == (1, True, False)


def test_zwei_fragen_und_frage_nicht_am_ende():
    f = M.frageform("Wie viele O-Atome stehen links? Stimmen die überein? Zähl nach.")
    assert (f["fragezeichen"], f["letzter_satz_frage"], f["frage_davor"]) == (2, False, True)


def test_zahlen_normalisiert():
    assert M._zahlen("$M = 40{,}3\\,\\mathrm{g/mol}$ und 8.06 g") == {"40,3", "8,06"}


def _protokoll(tmp_path, faelle):
    js, md = tmp_path / "v.json", tmp_path / "v.md"
    js.write_text(json.dumps({"faelle": faelle}), encoding="utf-8")
    md.write_text("# Kopf\n\n- **Importstand:** x\n", encoding="utf-8")
    return js, md


def test_e1_gegeben_allein_ist_keine_erneute_frage(tmp_path, monkeypatch):
    """Lauf 6/7: „8,02 g Calcium gegeben“ wurde als erneute Frage nach gegeben/gesucht gemeldet."""
    zuege = [{"nr": i, "schueler": "?", "antwort": "Was ist die Reaktionsgleichung?"} for i in (1, 2, 3)]
    zuege.append({"nr": 4, "schueler": "Ok, also 2 Ca + O2 → 2 CaO?",
                  "antwort": "Die Gleichung stimmt. Du hast 8,02 g Calcium gegeben. Welche Größe berechnest du zuerst?"})
    js, md = _protokoll(tmp_path, [{"id": "E1-ratlos-stufen", "zuege": zuege}])
    monkeypatch.setattr("sys.argv", ["x", str(js), str(md)])
    M.main()
    assert "fragt wieder nach gegeben/gesucht" not in md.read_text(encoding="utf-8")


def test_d5_fremde_zahl_und_kopfzeile(tmp_path, monkeypatch):
    z = {"nr": 1, "schueler": "n = 4,86/24,3 = 0,2 mol, m = 0,2 · 40 = 8 g",
         "antwort": "Stimmt. Genau wären es 40,3 g/mol. Wie lautet dein Antwortsatz?"}
    js, md = _protokoll(tmp_path, [{"id": "D5-frueh-gerundet", "zuege": [z]}])
    monkeypatch.setattr("sys.argv", ["x", str(js), str(md), "- **Dokument:** angehängt"])
    M.main()
    text = md.read_text(encoding="utf-8")
    assert "**D5-frueh-gerundet Zug 1:** 40,3" in text
    assert text.index("- **Dokument:** angehängt") < text.index("- **Importstand:**")
