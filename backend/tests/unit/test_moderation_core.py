"""Unit-Tests für die Entscheidungslogik des Moderations-Guardrails.

Die Datei liegt in `infra/guardrails/` (dort, wo der LiteLLM-Proxy läuft) und ist kein
Python-Paket — daher der Import über importlib, wie bei `scripts/` (CLAUDE.md).

Der wichtigste Test hier ist `test_caring_crisis_response_is_not_blocked`: Der Guardrail darf
die fürsorgliche Krisenantwort nicht wegfiltern. Sie nennt Selbstverletzung, verweist aber auf
Hilfe — genau die Antwort, die ADR-008 Teil 3 will. Ein Guardrail, der sie blockiert, richtet
mehr Schaden an als der Inhalt, den er verhindern soll.
"""
import importlib.util
from pathlib import Path

import pytest

_CORE = (
    Path(__file__).resolve().parents[3] / "infra" / "guardrails" / "moderation_core.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("moderation_core", _CORE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def core():
    return _load()


# ── Prompt ───────────────────────────────────────────────────────────────────

def test_prompt_lists_all_categories(core):
    system = core.build_messages("egal")[0]["content"]

    for name in core.DEFAULT_CATEGORIES:
        assert name in system


def test_prompt_carves_out_the_caring_crisis_answer(core):
    """Die Abgrenzung muss im Prompt stehen, nicht nur in der Doku.

    Ohne sie stuft ein Klassifikator eine Antwort, die Suizid benennt, zuverlässig als
    Treffer ein — und der Guardrail filterte genau die Hilfe weg, die gewünscht ist.
    """
    system = core.build_messages("egal")[0]["content"]

    assert "Hilfsangebote" in system
    assert "niemals blockiert" in system


def test_prompt_frames_the_school_context(core):
    """Aufklärung und Fachunterricht sollen nicht als Verstoß gelten."""
    system = core.build_messages("egal")[0]["content"]

    assert "schulischen Lernkontext" in system
    assert "zurückhaltend" in system


def test_long_text_is_truncated(core):
    messages = core.build_messages("x" * 20000, max_chars=100)

    assert messages[1]["content"] == "x" * 100


# ── Antwort lesen ────────────────────────────────────────────────────────────

def test_parses_plain_json(core):
    scores = core.parse_scores(
        '{"sexual": 0.1, "violence_graphic": 0.0, "self_harm_instructions": 0.9}'
    )

    assert scores["self_harm_instructions"] == 0.9


def test_parses_json_inside_a_fence(core):
    """LLMs legen gern ```json um ihre Antwort — das darf nicht am Parser scheitern."""
    raw = '```json\n{"sexual": 0.2, "violence_graphic": 0.1, "self_harm_instructions": 0.0}\n```'

    assert core.parse_scores(raw)["sexual"] == 0.2


def test_parses_json_with_surrounding_prose(core):
    raw = 'Hier meine Einschätzung:\n{"sexual": 0, "violence_graphic": 0, "self_harm_instructions": 0}\nViele Grüße'

    assert core.parse_scores(raw) == {
        "sexual": 0.0, "violence_graphic": 0.0, "self_harm_instructions": 0.0
    }


@pytest.mark.parametrize("raw", ["", "keine Ahnung", "{kaputt", None])
def test_unusable_answers_yield_none(core, raw):
    """None bedeutet „kein Urteil" → der Aufrufer lässt durch (fail-open)."""
    assert core.parse_scores(raw) is None


def test_missing_category_yields_none_instead_of_assuming_zero(core):
    """Eine nicht bewertete Kategorie ist ungeprüft — nicht unauffällig.

    Ein stillschweigendes 0.0 wäre eine falsche Entwarnung: Der Guardrail meldete dann
    „geprüft, alles in Ordnung", obwohl der Klassifikator gar nichts gesagt hat.
    """
    assert core.parse_scores('{"sexual": 0.1, "violence_graphic": 0.0}') is None


def test_boolean_is_not_accepted_as_a_score(core):
    """`true` ist in Python 1.0 — das darf nicht versehentlich als Höchstwert durchgehen."""
    assert core.parse_scores(
        '{"sexual": true, "violence_graphic": 0.0, "self_harm_instructions": 0.0}'
    ) is None


# ── Entscheidung ─────────────────────────────────────────────────────────────

def test_below_threshold_passes(core):
    hits = core.violated_categories(
        {"sexual": 0.4, "violence_graphic": 0.6, "self_harm_instructions": 0.4}
    )

    assert hits == []


def test_at_threshold_blocks(core):
    """Die Schwelle ist inklusiv — genau darauf zu liegen zählt als Treffer."""
    hits = core.violated_categories(
        {"sexual": 0.5, "violence_graphic": 0.0, "self_harm_instructions": 0.0}
    )

    assert hits == ["sexual"]


def test_thresholds_can_be_overridden(core):
    """Die Schule soll nachschärfen können, ohne den Code anzufassen."""
    scores = {"sexual": 0.3, "violence_graphic": 0.0, "self_harm_instructions": 0.0}

    assert core.violated_categories(scores) == []
    assert core.violated_categories(scores, thresholds={"sexual": 0.2}) == ["sexual"]


def test_multiple_hits_are_all_reported(core):
    hits = core.violated_categories(
        {"sexual": 0.9, "violence_graphic": 0.9, "self_harm_instructions": 0.9}
    )

    assert set(hits) == set(core.DEFAULT_CATEGORIES)


def test_caring_crisis_response_is_not_blocked(core):
    """Der Kernfall: niedrige Werte → keine Blockade, egal wie heikel das Thema ist.

    Die Einstufung selbst leistet der Klassifikator (Prompt-Abgrenzung oben); hier wird
    festgehalten, dass die Entscheidungslogik ein „nein" auch respektiert.
    """
    scores = {"sexual": 0.0, "violence_graphic": 0.1, "self_harm_instructions": 0.15}

    assert core.violated_categories(scores) == []


def test_violence_threshold_is_more_permissive_than_sexual(core):
    """Historische und literarische Gewaltdarstellung gehört zum Unterricht.

    Deshalb liegt die Schwelle höher — wie schon in der abgelösten
    openai_moderation-Konfiguration.
    """
    _, sexual = core.DEFAULT_CATEGORIES["sexual"]
    _, violence = core.DEFAULT_CATEGORIES["violence_graphic"]

    assert violence > sexual
