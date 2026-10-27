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
    ("nw_aufgaben.yaml", "naturwissenschaftliche Aufgaben"),
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


def test_rueckfaelle_zeigen_auf_assistenten_der_datei():
    namen = {e["name"] for e in EINTRAEGE}
    for e in EINTRAEGE:
        for r in e.get("fallbacks") or []:
            assert r in namen, (e["name"], r)
            assert next(x for x in EINTRAEGE if x["name"] == r)["suggest"] == "fallback"


def test_nw_assistent_hat_operator_faecher():
    """Päckchen AF: Ohne Fächerkreis bekäme der Prompt (v5d) nie den Abschnitt „Operator
    dieser Aufgabe"; die Fächer müssen in der ausgelieferten `subjects.yaml` stehen."""
    import yaml
    from pathlib import Path

    wurzel = Path(__file__).resolve().parents[3]
    eintraege = yaml.safe_load((wurzel / "config/assistants.example.yaml").read_text(encoding="utf-8"))
    nw = next(e for e in eintraege["assistants"] if e["name"] == "naturwissenschaftliche Aufgaben")
    slugs = {f["slug"] for f in yaml.safe_load(
        (wurzel / "config/subjects.yaml").read_text(encoding="utf-8"))["subjects"]}
    # Fächer, die erst noch kommen (in `subjects.yaml` auskommentiert): NiT ab 2027/28.
    kommen_noch = {"nit"}
    assert nw["operator_faecher"] and set(nw["operator_faecher"]) <= slugs | kommen_noch
    assert "bnt" not in nw["operator_faecher"]          # entfällt mit V3
