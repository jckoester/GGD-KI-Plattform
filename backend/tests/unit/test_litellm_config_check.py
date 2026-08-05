"""Unit-Tests für die Vollständigkeitsprüfung der LiteLLM-Konfiguration.

Jeder dieser Funde entspricht einem Fehler, der sonst **still** bleibt und erst Wochen später
auffällt — an einer Kostenstatistik, die auf 0 steht, oder an Werkzeugen, die nicht mehr
erscheinen. Der Zweck der Prüfung ist, sie vor der Inbetriebnahme sichtbar zu machen.
"""
from types import SimpleNamespace

import pytest

from app.litellm.config_check import ERROR, INFO, WARNING, check_config


def _settings(**over):
    base = dict(
        chat_default_model="chat-standard",
        title_model="system-titel",
        embedding_model="embedding-standard",
        image_default_model="bild-standard",
        model_picker_hidden_prefixes=["system-", "embedding-", "bild-"],
    )
    base.update(over)
    return SimpleNamespace(**base)


def _entry(name, *, target="openai/x", **info):
    return {
        "model_name": name,
        "litellm_params": {"model": target},
        "model_info": info,
    }


def _healthy():
    """Eine Konfiguration, die alle Anforderungen erfüllt."""
    return [
        _entry("chat-standard", supports_function_calling=True,
               input_cost_per_token=1.5e-7, output_cost_per_token=6e-7),
        _entry("system-titel", supports_function_calling=False,
               input_cost_per_token=1e-8, output_cost_per_token=2e-8),
        _entry("embedding-standard", mode="embedding", input_cost_per_token=1e-9),
        _entry("bild-standard", mode="image_generation", output_cost_per_image=0.01),
        _entry("ollama-fallback", target="ollama/llama3", supports_function_calling=False),
    ]


def _levels(findings, level):
    return [f.message for f in findings if f.level == level]


def test_healthy_config_has_no_errors_or_warnings():
    findings = check_config(_healthy(), _settings())

    assert _levels(findings, ERROR) == []
    assert _levels(findings, WARNING) == []


def test_empty_proxy_is_an_error():
    findings = check_config([], _settings())

    assert len(_levels(findings, ERROR)) == 1


# ── Preise: der teuerste stille Fehler ───────────────────────────────────────

def test_missing_token_prices_are_errors():
    """Ohne Preise meldet der SpendLog 0 — Budgets und 429-Enforcement greifen nicht."""
    entries = _healthy()
    entries[0] = _entry("chat-standard", supports_function_calling=True)

    errors = _levels(check_config(entries, _settings()), ERROR)

    assert any("input_cost_per_token" in m for m in errors)
    assert any("output_cost_per_token" in m for m in errors)
    assert any("Umrechnung" in m for m in errors), "Meldung soll die Umrechnung nennen"


def test_ollama_needs_no_prices():
    """Der lokale Fallback kostet nichts — ihn zu bemängeln wäre Rauschen."""
    findings = check_config(_healthy(), _settings())

    assert not [m for m in _levels(findings, ERROR) if "ollama" in m]


def test_per_image_token_pricing_counts_as_priced():
    """Regression: gpt-image-1 rechnet pro **Bild-Token** ab, nicht pro Bild.

    Eine feste Schlüsselliste (`output_cost_per_image`) hat das als „kein Preis" gemeldet —
    ein Fehlalarm, aufgefallen erst beim Lauf gegen den echten Dev-Proxy. Ein Prüfer, der
    grundlos warnt, wird ignoriert.
    """
    entries = _healthy()
    entries[3] = _entry(
        "bild-standard", mode="image_generation",
        input_cost_per_image_token=1e-5, output_cost_per_image_token=4e-5,
    )

    findings = check_config(entries, _settings())

    assert not [m for m in _levels(findings, WARNING) if "bild-standard" in m]


def test_missing_image_price_is_only_a_warning():
    """Bilder ohne Preis sind ärgerlich, aber blockieren den Betrieb nicht."""
    entries = _healthy()
    entries[3] = _entry("bild-standard", mode="image_generation")

    findings = check_config(entries, _settings())

    assert any("bild-standard" in m for m in _levels(findings, WARNING))
    assert not [m for m in _levels(findings, ERROR) if "bild-standard" in m]


# ── Werkzeug-Fähigkeit ───────────────────────────────────────────────────────

def test_unset_function_calling_is_an_error():
    """Unbestimmt ist schlimmer als False: Das Backend kann sich dann nicht entscheiden."""
    entries = _healthy()
    entries[0] = _entry("chat-standard", input_cost_per_token=1e-7, output_cost_per_token=1e-7)

    errors = _levels(check_config(entries, _settings()), ERROR)

    assert any("supports_function_calling" in m for m in errors)


def test_explicit_false_is_only_a_warning():
    """Ein bewusst tool-loses Standardmodell ist eine Entscheidung, kein Konfigurationsfehler."""
    entries = _healthy()
    entries[0] = _entry("chat-standard", supports_function_calling=False,
                        input_cost_per_token=1e-7, output_cost_per_token=1e-7)

    findings = check_config(entries, _settings())

    assert any("Function-Calling" in m for m in _levels(findings, WARNING))
    assert not [m for m in _levels(findings, ERROR) if "chat-standard" in m]


# ── .env ↔ Proxy ─────────────────────────────────────────────────────────────

def test_unknown_model_name_in_env_is_an_error():
    findings = check_config(_healthy(), _settings(chat_default_model="gibt-es-nicht"))

    errors = _levels(findings, ERROR)
    assert any("CHAT_DEFAULT_MODEL" in m and "gibt-es-nicht" in m for m in errors)
    assert any("chat-standard" in m for m in errors), "verfügbare Namen sollen genannt werden"


def test_missing_required_env_var_is_an_error():
    findings = check_config(_healthy(), _settings(chat_default_model=""))

    assert any("CHAT_DEFAULT_MODEL ist nicht gesetzt" in m for m in _levels(findings, ERROR))


def test_optional_title_model_may_be_empty():
    """Leeres TITLE_MODEL heißt schlicht „keine Titelgenerierung"."""
    findings = check_config(_healthy(), _settings(title_model=""))

    assert not [m for m in _levels(findings, ERROR) if "TITLE_MODEL" in m]


# ── Modalitäten ──────────────────────────────────────────────────────────────

def test_image_model_without_mode_is_an_error():
    """Ohne mode taucht es in der Bild-Freigabe-Matrix nicht auf."""
    entries = _healthy()
    entries[3] = _entry("bild-standard", output_cost_per_image=0.01)

    errors = _levels(check_config(entries, _settings()), ERROR)

    assert any("image_generation" in m for m in errors)


def test_embedding_model_without_mode_is_only_a_warning():
    entries = _healthy()
    entries[2] = _entry("embedding-standard", input_cost_per_token=1e-9)

    findings = check_config(entries, _settings())

    assert any("embedding" in m for m in _levels(findings, WARNING))
    assert not [m for m in _levels(findings, ERROR) if "embedding-standard" in m]


# ── Sichtbarkeit ─────────────────────────────────────────────────────────────

def test_reports_which_models_are_pickable():
    findings = check_config(_healthy(), _settings())
    info = " ".join(_levels(findings, INFO))

    assert "chat-standard" in info
    assert "system-titel" in info  # als ausgeblendet gemeldet


def test_title_model_visible_in_picker_is_a_warning():
    """Ein Titelmodell ohne system--Präfix landet im Dropdown der Schüler:innen."""
    entries = _healthy()
    entries[1] = _entry("gpt-4o-mini", supports_function_calling=False,
                        input_cost_per_token=1e-8, output_cost_per_token=2e-8)

    findings = check_config(entries, _settings(title_model="gpt-4o-mini"))

    warnings = _levels(findings, WARNING)
    assert any("TITLE_MODEL" in m and "Modellwähler" in m for m in warnings)
    assert any("freigeschaltet bleiben muss" in m for m in warnings), (
        "Die Warnung darf nicht dazu verleiten, das Modell aus der Allowlist zu nehmen"
    )


# ── Vorlagen-Platzhalter ─────────────────────────────────────────────────────

@pytest.mark.parametrize("name,target", [
    ("ionos-<GROSS>", "openai/x"),
    ("chat-standard", "openai/<IONOS-CHAT-ID>"),
    ("chat-standard", "openai/TODO"),
])
def test_unreplaced_placeholders_are_errors(name, target):
    """Die Vorlage ist voller `<…>` — wer eines übersieht, soll es hier erfahren."""
    findings = check_config([_entry(name, target=target)], _settings())

    assert any("Platzhalter" in m for m in _levels(findings, ERROR))
