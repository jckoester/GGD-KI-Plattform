"""Die Beispiel-Assistenten (`config/assistants.example.yaml`) und ihre Prompts.

Der Seed (`scripts/seed_assistants.py`) legt sie auf einer neuen Instanz an. Was hier
schiefgeht, fällt sonst erst im Chat auf: eine Fähigkeit, die der Import verwirft, eine
Prompt-Datei, die fehlt, oder ein Prompt, der ein Werkzeug beim alten Namen ruft.
"""
import re
from pathlib import Path

import pytest
import yaml

import app.chat.router  # noqa: F401 — füllt TOOL_REGISTRY
from app.chat.tools import FAEHIGKEITEN, TOOL_REGISTRY

WURZEL = Path(__file__).resolve().parents[3]
EINTRAEGE = yaml.safe_load((WURZEL / "config" / "assistants.example.yaml").read_text(encoding="utf-8"))["assistants"]


def _eintrag(name):
    return next(e for e in EINTRAEGE if e["name"] == name)


def _prompt(eintrag) -> str:
    return (WURZEL / eintrag["system_prompt_file"]).read_text(encoding="utf-8")


@pytest.mark.parametrize("eintrag", EINTRAEGE, ids=lambda e: e["name"])
def test_faehigkeiten_und_prompt_datei(eintrag):
    assert set(eintrag.get("tool_groups", [])) <= set(FAEHIGKEITEN)
    if "system_prompt_file" in eintrag:
        assert (WURZEL / eintrag["system_prompt_file"]).is_file()


@pytest.mark.parametrize("eintrag", [e for e in EINTRAEGE if "system_prompt_file" in e],
                         ids=lambda e: e["name"])
def test_prompt_nennt_nur_werkzeuge_seiner_faehigkeiten(eintrag):
    """`snake_case` in Backticks, der wie ein Werkzeugname aussieht, muss eines sein — und
    eines, das die Fähigkeiten dieses Assistenten freischalten (oder die Suche, die immer
    greift)."""
    erreichbar = {
        name for name, werkzeug in TOOL_REGISTRY.items()
        if werkzeug.groups & (set(eintrag.get("tool_groups", [])) | {"context_search"})
    }
    genannt = set(re.findall(r"`([a-z]+(?:_[a-z]+)+)`", _prompt(eintrag)))
    werkzeugnamen = {n for n in genannt if n in TOOL_REGISTRY or n.split("_")[0] in
                     {"get", "update", "create", "set", "assign", "apply", "undo", "finde",
                      "waehle", "search", "list"}}
    assert werkzeugnamen <= erreichbar, sorted(werkzeugnamen - erreichbar)


class TestStundenentwurf:
    """Der schulweite Stundenassistent (0.15, Päckchen A Schritt 6)."""

    def test_eintrag(self):
        e = _eintrag("Stundenentwurf")
        assert e["tool_groups"] == ["lesson_planning"]
        assert e["audience"] == "teacher" and e["status"] == "active"

    def test_prompt_nennt_die_stundenwerkzeuge(self):
        text = _prompt(_eintrag("Stundenentwurf"))
        for werkzeug in ("finde_stunde", "waehle_stunde", "get_lesson_detail",
                         "update_lesson_phases"):
            assert f"`{werkzeug}`" in text, werkzeug
        # Das Vokabular kommt mit dem Entwurf; einzeln nachschlagen kostete die Runden,
        # die zum Schreiben fehlten (Messung 1, 10.10.2026).
        assert "`vokabular`" in text

    def test_vorlage_fuer_eigene_assistenten(self):
        """Der Abschnitt mit den Lücken ist die Vorlage (Plan F6) — und der Prompt sagt, dass
        eine leere Lücke nicht gilt."""
        text = _prompt(_eintrag("Stundenentwurf"))
        abschnitt = text.split("## Meine Planungsgewohnheiten", 1)[1]
        assert abschnitt.count("[…]") >= 4
        assert "gilt nicht" in abschnitt
