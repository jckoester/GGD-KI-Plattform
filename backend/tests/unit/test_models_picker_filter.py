"""Unit-Tests: interne Modelle erscheinen nicht im Chat-Modellwähler.

Mit dem Namensschema aus §5 stehen neben den Chat-Stufen auch System-, Embedding- und
Bildmodelle in der LiteLLM-`model_list` — rund 15 Einträge. Ohne Filter landen sie alle im
Dropdown, das Schüler:innen bei jedem freien Chat sehen (`chat/+page.svelte` rendert die
Modell-ID roh).

Zwei Dinge sind dabei nicht offensichtlich:

* **`system-titel` muss allowlistet bleiben.** Die Titelgenerierung läuft über den
  persönlichen Virtual Key, nicht über den Master-Key — LiteLLM prüft also die Team-Allowlist.
  Der Filter ist deshalb rein kosmetisch und darf keine Berechtigung anfassen.
* **Der Admin-Zweig umgeht die Allowlist-Filterung.** Ohne ausdrückliche Behandlung sähe
  ausgerechnet der Admin die volle Liste inklusive Embedding- und Bildmodellen.
"""
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import app.chat.router as _chat_router_mod
from app.config import settings

from tests.unit.test_models_router import (
    _fake_admin_payload,
    _fake_student_payload,
    _fake_teacher_payload,
    _make_app,
)

# Wie eine vollständige IONOS-Konfiguration nach §5.2 aussieht.
FULL_MODEL_LIST = [
    "chat-schnell", "chat-standard", "chat-code", "chat-komplex",
    "system-titel", "system-moderation",
    "embedding-standard", "bild-standard",
    "ollama-fallback",
    "ionos-gpt-oss-120b",
]


@pytest.fixture(autouse=True)
def reset_cache():
    _chat_router_mod._model_info_cache = None
    yield
    _chat_router_mod._model_info_cache = None


def _get_models(payload, *, allowlist=None, models=None):
    app = _make_app(payload)
    with patch("app.chat.router.LiteLLMClient") as client_cls:
        client = AsyncMock()
        client.list_models.return_value = models if models is not None else FULL_MODEL_LIST
        client.get_team_info.return_value = (
            {"models": allowlist} if allowlist is not None else None
        )
        client.get_model_info.return_value = {}
        client.close.return_value = None
        client_cls.return_value = client
        response = TestClient(app).get("/models")
    assert response.status_code == 200
    return [m["id"] for m in response.json()["models"]]


def test_student_sees_only_chat_stages():
    """Alles freigeschaltet — trotzdem nur wählbare Modelle im Dropdown."""
    ids = _get_models(_fake_student_payload(grade=8), allowlist=FULL_MODEL_LIST)

    assert ids == [
        "chat-schnell", "chat-standard", "chat-code", "chat-komplex",
        "ollama-fallback", "ionos-gpt-oss-120b",
    ]
    assert not [m for m in ids if m.startswith(("system-", "embedding-", "bild-"))]


def test_admin_bypass_is_also_filtered():
    """Der Admin umgeht die Allowlist — der kosmetische Filter greift trotzdem."""
    ids = _get_models(_fake_admin_payload())

    assert "system-titel" not in ids
    assert "embedding-standard" not in ids
    assert "bild-standard" not in ids
    assert "chat-standard" in ids


def test_teacher_sees_explicit_names_too():
    """Ebene 2 (Anbieter-Präfix) bleibt sichtbar — sie ist ja gerade für Lehrkräfte da."""
    ids = _get_models(_fake_teacher_payload(), allowlist=FULL_MODEL_LIST)

    assert "ionos-gpt-oss-120b" in ids
    assert "system-titel" not in ids


def test_filter_does_not_touch_the_allowlist():
    """`system-titel` bleibt freigeschaltet, es verschwindet nur aus der Auswahl.

    Der Test hält fest, dass der Filter erst NACH der Allowlist-Auswertung greift: Ein Team
    mit ausschließlich internen Modellen bekommt eine leere Auswahl — aber die
    Titelgenerierung, die über den Virtual Key läuft, ist davon unberührt.
    """
    ids = _get_models(_fake_student_payload(grade=5), allowlist=["system-titel"])

    assert ids == []


def test_title_model_stays_callable_despite_being_hidden():
    """Gegenprobe zur Kosmetik-Zusage: der Chat-Flow nutzt settings.title_model direkt.

    Der Filter sitzt allein im /models-Endpunkt; er kann die Titelgenerierung gar nicht
    erreichen. Dieser Test nagelt fest, dass niemand ihn versehentlich in den Chat-Pfad zieht.
    """
    from app.chat.router import _generate_title
    import inspect

    source = inspect.getsource(_generate_title)
    assert "_is_pickable_model" not in source
    assert "settings.title_model" in source


def test_hidden_prefixes_are_configurable(monkeypatch):
    """Wer anders benennt, passt die Präfixe an — der Filter greift dann dort."""
    monkeypatch.setattr(settings, "model_picker_hidden_prefixes", ["intern-"])

    ids = _get_models(
        _fake_admin_payload(),
        models=["chat-standard", "intern-titel", "system-titel"],
    )

    assert ids == ["chat-standard", "system-titel"]


def test_empty_prefix_list_hides_nothing(monkeypatch):
    monkeypatch.setattr(settings, "model_picker_hidden_prefixes", [])

    ids = _get_models(_fake_admin_payload())

    assert ids == FULL_MODEL_LIST


def test_admin_matrix_still_sees_internal_models():
    """Die Freischaltungsmatrix darf NICHT filtern — dort schaltet der Admin sie ja frei.

    `system-titel` muss in jeder Team-Allowlist stehen; wäre es in der Matrix unsichtbar,
    könnte niemand es freischalten und die Titelgenerierung bliebe dauerhaft kaputt.
    """
    import inspect
    import app.api.admin.models as admin_models

    source = inspect.getsource(admin_models)
    assert "_is_pickable_model" not in source
    assert "model_picker_hidden_prefixes" not in source
