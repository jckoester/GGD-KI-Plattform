"""Der geseedete Curriculum-Assistent (0.46): nur für Lehrkräfte, mit Prompt und Marke."""
from pathlib import Path

import yaml

from app.api.assistants import NUR_ADMIN_FAEHIGKEITEN

WURZEL = Path(__file__).resolve().parents[3]


def test_seed_gibt_die_faehigkeit_nur_lehrkraeften():
    eintraege = yaml.safe_load((WURZEL / "config" / "assistants.example.yaml").read_text())["assistants"]
    mit = [e for e in eintraege if NUR_ADMIN_FAEHIGKEITEN & set(e.get("tool_groups") or [])]
    assert [e["name"] for e in mit] == ["Curriculum-Entwurf"]
    for e in mit:
        assert e["audience"] == "teacher" and e["scope"] == "teachers"
        assert e["produces"] == ["curriculum"]
        assert (WURZEL / e["system_prompt_file"]).is_file()
