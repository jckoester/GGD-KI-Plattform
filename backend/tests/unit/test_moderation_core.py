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

import json

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

def _alle(core, **abweichungen) -> dict:
    """Vollstaendige Bewertung: alle Kategorien auf 0.0, genannte ueberschrieben.

    `parse_scores` verlangt bewusst JEDE Kategorie — eine fehlende bedeutet „ungeprueft".
    Die Tests bauen ihre Eingabe deshalb aus `DEFAULT_CATEGORIES` statt sie zu tippen;
    sonst bricht bei jeder neuen Kategorie die halbe Datei.
    """
    werte = {name: 0.0 for name in core.DEFAULT_CATEGORIES}
    werte.update(abweichungen)
    return werte



def test_parses_plain_json(core):
    scores = core.parse_scores(json.dumps(_alle(core, sexual=0.1, self_harm_instructions=0.9)))

    assert scores["self_harm_instructions"] == 0.9


def test_parses_json_inside_a_fence(core):
    """LLMs legen gern ```json um ihre Antwort — das darf nicht am Parser scheitern."""
    raw = f"```json\n{json.dumps(_alle(core, sexual=0.2, violence_graphic=0.1))}\n```"

    assert core.parse_scores(raw)["sexual"] == 0.2


def test_parses_json_with_surrounding_prose(core):
    raw = f"Hier meine Einschätzung:\n{json.dumps(_alle(core))}\nViele Grüße"

    assert core.parse_scores(raw) == _alle(core)


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
    assert core.parse_scores(json.dumps(_alle(core, sexual=True))) is None


# ── Entscheidung ─────────────────────────────────────────────────────────────

def test_below_threshold_passes(core):
    hits = core.violated_categories(
        _alle(core, sexual=0.4, violence_graphic=0.6, self_harm_instructions=0.4)
    )

    assert hits == []


def test_at_threshold_blocks(core):
    """Die Schwelle ist inklusiv — genau darauf zu liegen zählt als Treffer."""
    hits = core.violated_categories(
        _alle(core, sexual=0.5)
    )

    assert hits == ["sexual"]


def test_thresholds_can_be_overridden(core):
    """Die Schule soll nachschärfen können, ohne den Code anzufassen."""
    scores = _alle(core, sexual=0.3)

    assert core.violated_categories(scores) == []
    assert core.violated_categories(scores, thresholds={"sexual": 0.2}) == ["sexual"]


def test_multiple_hits_are_all_reported(core):
    hits = core.violated_categories(
        {name: 0.9 for name in core.DEFAULT_CATEGORIES}
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


# ── Drogen-Anleitungen (ersetzt den entfallenen regex-Guardrail) ──────────────

def test_drug_category_exists(core):
    """Ohne sie prüft nach dem Wegfall von `regex` NICHTS mehr auf Herstellungsanleitungen."""
    assert "drug_instructions" in core.DEFAULT_CATEGORIES


def test_drug_prompt_carves_out_chemistry_lessons(core):
    """Der Grund, warum es der Klassifikator und nicht wieder eine Regex ist.

    Ein Muster wie `(anleitung|rezept).{0,40}synthese` trifft die Ammoniaksynthese mit.
    Die Kategoriebeschreibung muss den Unterricht deshalb ausdrücklich ausnehmen —
    sonst blockiert der Guardrail Chemie, Suchtprävention und Pharmakologie.
    """
    beschreibung, _ = core.DEFAULT_CATEGORIES["drug_instructions"]
    kleingeschrieben = beschreibung.lower()

    assert "kein treffer" in kleingeschrieben
    for erlaubt in ("chemieunterricht", "suchtprävention", "pharmakologie"):
        assert erlaubt in kleingeschrieben, f"{erlaubt} nicht ausgenommen"


def test_drug_prompt_names_the_deciding_question(core):
    """Nicht „kommen Drogen vor?", sondern „versetzt der Text jemanden in die Lage?"."""
    beschreibung, _ = core.DEFAULT_CATEGORIES["drug_instructions"]

    assert "herzustellen oder zu beschaffen" in beschreibung.lower()


def test_drug_hit_blocks(core):
    hits = core.violated_categories(_alle(core, drug_instructions=0.9))

    assert hits == ["drug_instructions"]


def test_chemistry_lesson_score_passes(core):
    """Ein niedriger Wert muss folgenlos bleiben — auch wenn Drogen im Text vorkommen."""
    assert core.violated_categories(_alle(core, drug_instructions=0.2)) == []


# ── Verhalten bei Ausfall des Klassifikators ─────────────────────────────────

def test_teachers_keep_working_when_the_classifier_is_down(core):
    """Sonst legte eine Anbieterstörung den Unterricht der ganzen Schule lahm."""
    assert core.fail_closed("lehrkraefte") is False


def test_students_are_blocked_when_the_classifier_is_down(core):
    """Der eigentliche Zweck: Eine abgewiesene Antwort ist ärgerlich, eine ungefilterte
    ist genau das, was der Guardrail verhindern soll."""
    for team in ("jahrgang-5", "jahrgang-9", "jahrgang-12"):
        assert core.fail_closed(team) is True, team


def test_unknown_team_is_treated_as_protected(core):
    """Ein kaputter Team-Bezug darf nicht dazu führen, dass alle als Lehrkraft gelten."""
    assert core.fail_closed(None) is True
    assert core.fail_closed("") is True


def test_fail_open_teams_are_configurable(core):
    """Die Schule soll den Kreis erweitern können, ohne den Code anzufassen."""
    assert core.fail_closed("referendare", {"lehrkraefte", "referendare"}) is False
    assert core.fail_closed("lehrkraefte", set()) is True, "leere Menge = niemand ausgenommen"


# ── Zustandsbericht ──────────────────────────────────────────────────────────

def _snapshot(core, **counters):
    return core.build_health_snapshot(
        counters, classifier="m", fallback=None, zeitstempel="2026-08-28T10:00:00+00:00"
    )


def test_snapshot_counts_every_outcome(core):
    s = _snapshot(core, primary_ok=90, retry_ok=5, failed_open=3, failed_closed=2, blocked=7)

    assert s["total"] == 100, "blocked zählt nicht mit — es ist ein Urteil, kein Ausfall"
    assert s["failure_rate"] == 0.05
    assert s["healthy"] is False


def test_snapshot_separates_retries_from_first_attempts(core):
    """Häufige, aber gelungene Wiederholungen deuten auf Latenz oder Überlast hin —
    in einer gemeinsamen Erfolgsquote gingen sie unter."""
    s = _snapshot(core, primary_ok=10, retry_ok=40)

    assert s["counters"]["retry_ok"] == 40
    assert s["healthy"] is True, "Wiederholungen sind kein Ausfall"
    assert s["failure_rate"] == 0.0


def test_snapshot_without_traffic_does_not_divide_by_zero(core):
    s = _snapshot(core)

    assert s["total"] == 0 and s["failure_rate"] == 0.0 and s["healthy"] is True


def test_snapshot_reports_the_configured_models(core):
    s = core.build_health_snapshot(
        {}, classifier="openai/gpt-4o-mini", fallback="ollama/llama3",
        zeitstempel="2026-08-28T10:00:00+00:00",
    )

    assert s["classifier_model"] == "openai/gpt-4o-mini"
    assert s["fallback_model"] == "ollama/llama3"
