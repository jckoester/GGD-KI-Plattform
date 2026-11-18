"""Planungsassistenten ohne eigenes Modell laufen auf `PLANUNG_MODEL` (0.49).

Anlass: `chat-standard` sollte auf ein günstiges Modell (Mistral Small 4), das am
Stundenassistenten scheitert (13/30, Messung 17.11.2026). Die Planungsassistenten tragen im Seed
kein Modell, damit sie einem Modellwechsel folgen; auf Dev hatte selbst der Curriculum-Entwurf ein
leeres Modell.
"""
from types import SimpleNamespace

import pytest

from app.assistants import sichtbarkeit
from app.assistants.sichtbarkeit import PLANUNGS_FAEHIGKEITEN, modell_des_assistenten


def _a(model="", tool_groups=()):
    return SimpleNamespace(model=model, tool_groups=list(tool_groups))


@pytest.fixture
def modelle(monkeypatch):
    monkeypatch.setattr(sichtbarkeit.settings, "chat_default_model", "chat-standard")
    monkeypatch.setattr(sichtbarkeit.settings, "planung_model", "chat-komplex")


@pytest.mark.parametrize("faehigkeit", sorted(PLANUNGS_FAEHIGKEITEN))
def test_planungs_faehigkeit_ohne_modell_nimmt_planung_model(modelle, faehigkeit):
    assert modell_des_assistenten(_a(tool_groups=[faehigkeit, "context_search"])) == "chat-komplex"


def test_ohne_planung_bleibt_das_standardmodell(modelle):
    assert modell_des_assistenten(_a(tool_groups=["context_search", "image_generation"])) == "chat-standard"
    assert modell_des_assistenten(_a(tool_groups=["student_planning"])) == "chat-standard"


def test_ein_gesetztes_modell_gilt_immer(modelle):
    assert modell_des_assistenten(_a(model="chat-schnell", tool_groups=["lesson_planning"])) == "chat-schnell"


def test_ohne_planung_model_wie_bisher(monkeypatch):
    monkeypatch.setattr(sichtbarkeit.settings, "chat_default_model", "chat-standard")
    monkeypatch.setattr(sichtbarkeit.settings, "planung_model", "")
    assert modell_des_assistenten(_a(tool_groups=["lesson_planning"])) == "chat-standard"


def test_der_chat_nimmt_das_modell_ueber_dieselbe_regel():
    """Beide Stellen im Chat-Router, an denen ein Assistent sein Modell setzt."""
    from pathlib import Path
    quelle = Path(__file__).resolve().parents[2].joinpath("app", "chat", "router.py").read_text()
    assert quelle.count("model_used = modell_des_assistenten(") == 2
    assert "model_used = assistant.model" not in quelle
    assert "model_used = new_assistant.model" not in quelle
