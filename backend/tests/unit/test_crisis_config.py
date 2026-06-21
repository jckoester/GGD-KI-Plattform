"""Tests für app.crisis.config — Laden, Validierung, Vorkompilierung, Referenzen."""

import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from pydantic import ValidationError

import app.crisis.config as crisis_config
from app.crisis.config import (
    CrisisTrigger,
    CrisisTriggers,
    HelpResources,
    invalidate_crisis_cache,
    load_crisis_triggers,
    load_help_resources,
    missing_help_topics,
    normalize,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Jeder Test startet und endet mit leerem Modul-Cache."""
    invalidate_crisis_cache()
    yield
    invalidate_crisis_cache()


# ========== Laden der echten Konfigurationsdateien ==========


def test_load_crisis_triggers_real_file():
    cfg = load_crisis_triggers()
    cats = {t.category for t in cfg.triggers}
    assert "suizidalitaet" in cats
    assert all(t.severity in ("info", "warning", "alert") for t in cfg.triggers)
    assert all(t.coreviewer_role == "review" for t in cfg.triggers)


def test_load_help_resources_real_file():
    res = load_help_resources()
    assert "crisis" in res.topics
    assert res.topics["crisis"].external  # mind. eine externe Anlaufstelle


def test_real_config_references_resolve():
    """Jeder Trigger.help_topic existiert in help_resources.yaml."""
    assert missing_help_topics() == []


def test_loaders_use_cache():
    first = load_crisis_triggers()
    assert load_crisis_triggers() is first  # zweiter Aufruf liefert dasselbe Objekt


# ========== Vorkompilierung der Patterns ==========


def test_triggers_are_precompiled():
    cfg = load_crisis_triggers()
    for t in cfg.triggers:
        assert len(t.compiled) == len(t.patterns)
        assert all(hasattr(p, "search") for p in t.compiled)


def test_compiled_pattern_matches_normalized_text():
    trigger = CrisisTrigger(
        category="x", severity="alert", patterns=["niemand würde mich vermissen"], help_topic="crisis"
    )
    pattern = trigger.compiled[0]
    # Großschreibung + NFKC/casefold-Normalisierung der Eingabe → Treffer
    assert pattern.search(normalize("NIEMAND WÜRDE MICH VERMISSEN"))
    assert not pattern.search(normalize("alles gut heute"))


# ========== Normalisierung ==========


def test_normalize_casefold_and_nfkc():
    assert normalize("ÜBER") == normalize("über")
    assert normalize("Ärger") == "ärger"


# ========== Validierung ==========


def test_invalid_severity_rejected():
    with pytest.raises(ValidationError):
        CrisisTrigger(category="x", severity="critical", patterns=["a"], help_topic="crisis")


def test_empty_patterns_rejected():
    with pytest.raises(ValidationError):
        CrisisTrigger(category="x", severity="alert", patterns=[], help_topic="crisis")


def test_missing_required_field_rejected():
    with pytest.raises(ValidationError):
        CrisisTriggers.model_validate({"triggers": [{"category": "x", "severity": "alert"}]})


# ========== Fehlende Datei / fehlende Referenz ==========


def test_missing_file_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(crisis_config.settings, "crisis_triggers_path", str(tmp_path / "nope.yaml"))
    invalidate_crisis_cache()
    with pytest.raises(FileNotFoundError):
        load_crisis_triggers()


def test_missing_help_topic_detected(monkeypatch, tmp_path):
    triggers_yaml = tmp_path / "triggers.yaml"
    triggers_yaml.write_text(
        "triggers:\n"
        "  - category: x\n"
        "    severity: alert\n"
        "    help_topic: nonexistent\n"
        "    patterns: ['foo']\n",
        encoding="utf-8",
    )
    resources_yaml = tmp_path / "resources.yaml"
    resources_yaml.write_text("topics:\n  crisis:\n    label: 'X'\n", encoding="utf-8")

    monkeypatch.setattr(crisis_config.settings, "crisis_triggers_path", str(triggers_yaml))
    monkeypatch.setattr(crisis_config.settings, "help_resources_path", str(resources_yaml))
    invalidate_crisis_cache()

    assert missing_help_topics() == ["nonexistent"]
