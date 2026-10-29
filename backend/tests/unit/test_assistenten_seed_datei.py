"""`config/assistants.example.yaml` — die ausgelieferten Assistenten sind vollständig (26.10.2026)."""
from pathlib import Path

import pytest
import yaml

from app.assistants import ausloeser

WURZEL = Path(__file__).resolve().parents[3]
EINTRAEGE = yaml.safe_load((WURZEL / "config/assistants.example.yaml").read_text(encoding="utf-8"))["assistants"]
SCHUELER = [e for e in EINTRAEGE if e.get("audience") == "student"]


def test_namen_eindeutig():
    namen = [e["name"] for e in EINTRAEGE]
    assert len(namen) == len(set(namen))


@pytest.mark.parametrize("eintrag", EINTRAEGE, ids=lambda e: e["name"])
def test_dateien_vorhanden(eintrag):
    for rel in [eintrag.get("system_prompt_file"), *(eintrag.get("documents") or [])]:
        if rel:
            assert (WURZEL / rel).is_file(), rel


@pytest.mark.parametrize("eintrag", SCHUELER, ids=lambda e: e["name"])
def test_schueler_assistent_traegt_vorschlag(eintrag):
    assert eintrag["suggest"] in ("specific", "fallback")
    assert eintrag.get("suggestion_text")
    beispiele = ausloeser.bereinige(eintrag["trigger_examples"], ausloeser.BEISPIEL)
    gegen = ausloeser.bereinige(eintrag["trigger_counterexamples"], ausloeser.GEGENBEISPIEL)
    assert 5 <= len(beispiele) <= 15
    assert gegen
    assert not set(beispiele) & set(gegen)


@pytest.mark.parametrize("szenario,name", [
    ("stoechiometrie.yaml", "stöchiometrische Berechnungen"),
    ("reaktionsgleichung.yaml", "Reaktionsgleichungen"),
])
def test_pruefsatz_nicht_unter_den_beispielen(szenario, name):
    """Die ersten Züge der Messszenarien sind der zurückgehaltene Prüfsatz (C1, Schritt 0/5)."""
    faelle = yaml.safe_load((WURZEL / "backend/scripts/szenarien" / szenario).read_text(encoding="utf-8"))["faelle"]
    erste = {f["zuege"][0]["schueler"].strip() for f in faelle}
    eintrag = next(e for e in EINTRAEGE if e["name"] == name)
    assert not erste & set(eintrag["trigger_examples"])
    # Und der Seed stimmt mit dem Kopf der Szenariodatei überein (Messung = Auslieferung).
    kopf = yaml.safe_load((WURZEL / "backend/scripts/szenarien" / szenario).read_text(encoding="utf-8"))["assistent"]
    assert kopf["name"] == eintrag["name"]
    assert kopf["prompt"] == eintrag["system_prompt_file"]
    assert (kopf["min_grade"], kopf["max_grade"], kopf["modell"]) == (
        eintrag["min_grade"], eintrag["max_grade"], eintrag["model"])
    assert kopf["ohne"] == eintrag["disabled_augmentations"]
    assert kopf.get("operator_faecher", []) == eintrag.get("operator_faecher", [])
    assert kopf.get("bausteine", []) == eintrag.get("bausteine", [])


def test_rueckfaelle_zeigen_auf_assistenten_der_datei():
    namen = {e["name"] for e in EINTRAEGE}
    for e in EINTRAEGE:
        for r in e.get("fallbacks") or []:
            assert r in namen, (e["name"], r)
            assert next(x for x in EINTRAEGE if x["name"] == r)["suggest"] == "fallback"


def test_operator_faecher_gibt_es():
    """Päckchen AF: Die Fächer für den Abschnitt „Operator dieser Aufgabe" müssen in der
    ausgelieferten `subjects.yaml` stehen — sonst übergeht der Seed sie still."""
    slugs = {f["slug"] for f in yaml.safe_load(
        (WURZEL / "config/subjects.example.yaml").read_text(encoding="utf-8"))["subjects"]}
    # Fächer, die erst noch kommen (in `subjects.yaml` auskommentiert): NiT ab 2027/28.
    kommen_noch = {"nit"}
    for e in EINTRAEGE:
        faecher = set(e.get("operator_faecher") or [])
        assert faecher <= slugs | kommen_noch, e["name"]
        assert "bnt" not in faecher, e["name"]          # entfällt mit V3


def test_rueckfallebene_vollstaendig():
    """Die zwölf allgemeinen Assistenten der Landkarte (28.10.2026), alle mit beiden Bausteinen."""
    rueck = [e for e in SCHUELER if e["suggest"] == "fallback"]
    assert len(rueck) == 12
    for e in rueck:
        assert e["bausteine"] == ["begleiten_statt_loesen", "grundton"], e["name"]
        assert "subject" not in e, e["name"]
    assert "naturwissenschaftliche Aufgaben" not in {e["name"] for e in EINTRAEGE}


def test_bausteine_der_datei_gibt_es():
    """Ein unbekannter Baustein übergeht der Seed nur mit Warnung — hier fällt er auf."""
    from app.assistants.bausteine import SCHLUESSEL
    for e in EINTRAEGE:
        assert set(e.get("bausteine") or []) <= SCHLUESSEL, e["name"]
