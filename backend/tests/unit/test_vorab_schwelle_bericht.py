"""Die Auswertung von `scripts/vorab_schwelle.py` (0.14, Schritt 6).

Bis 06.10.2026 druckte das Skript nur die Distanzen; welche davon die Grenzen sind und
ob `VORAB_SCHWELLE` dazwischen liegt, rechnete der Leser selbst aus. Jetzt steht es am
Ende, und ein Exit-Code sagt es auch einem Prüflauf.
"""
import importlib.util
from pathlib import Path

SKRIPT = Path(__file__).resolve().parents[2] / "scripts" / "vorab_schwelle.py"


def _laden():
    """Über den Dateipfad laden — `backend/scripts/` ist bewusst kein Paket."""
    spec = importlib.util.spec_from_file_location("vorab_schwelle", SKRIPT)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


M = _laden()
FACHLICH = [M.Messwert("Oxidation?", "Oxidation", 0.249),
            M.Messwert("Flamme?", "Flamme (GHS02)", 0.433)]
BEILAEUFIG = [M.Messwert("Danke!", "Donator-Akzeptor-Prinzip", 0.608),
              M.Messwert("Bewerbung", "Operatorenblatt", 0.481)]


def test_grenzen_sind_der_groesste_erwuenschte_und_der_kleinste_unerwuenschte():
    g = M.grenzen(FACHLICH, BEILAEUFIG, 0.45)
    assert (g.erwuenscht.titel, g.unerwuenscht.titel) == ("Flamme (GHS02)", "Operatorenblatt")
    assert round(g.luecke, 3) == 0.048
    assert g.trennt


def test_schwelle_ausserhalb_der_luecke_trennt_nicht():
    assert not M.grenzen(FACHLICH, BEILAEUFIG, 0.481).trennt   # unerwünschter Treffer drin
    assert not M.grenzen(FACHLICH, BEILAEUFIG, 0.40).trennt    # erwünschter fällt heraus


def test_auf_der_schwelle_zaehlt_noch_als_treffer():
    """`distanz > VORAB_SCHWELLE` fällt heraus — gleich ist noch drin."""
    assert M.grenzen(FACHLICH, BEILAEUFIG, 0.433).trennt


def test_bericht_nennt_grenzen_luecke_und_urteil():
    g = M.grenzen(FACHLICH, BEILAEUFIG, 0.45)
    text = "\n".join(M.bericht(g, [M.Messwert("Gedicht", "Merkblatt", 0.482)]))
    assert "0.433" in text and "0.481" in text and "0.048" in text
    assert "liegt dazwischen ✓" in text
    assert "Grenzfall" in text and "außerhalb der Schwelle" in text
    schlecht = "\n".join(M.bericht(M.grenzen(FACHLICH, BEILAEUFIG, 0.5), []))
    assert "liegt NICHT dazwischen" in schlecht
