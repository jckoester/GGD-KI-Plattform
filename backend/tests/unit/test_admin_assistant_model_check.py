"""Unit-Tests: Assistenten mit verschwundenem Modell werden gemeldet.

Die zweite Namensebene (§5.4) erlaubt es, einen Assistenten fest an ein Modell zu binden —
`ionos-gpt-oss-120b` statt `chat-standard`. Fällt dieser Eintrag später aus der LiteLLM-Config
(Anbieterwechsel, abgekündigtes Modell), bricht der Assistent **still**: Der Chat-Aufruf
scheitert, aber niemand weiß warum. Ein Hinweistext im Editor hilft dabei nicht — er erreicht
nur den, der den Assistenten anlegt, nicht den, der ihn ein Jahr später erbt.
"""
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.api.admin.assistants import router as admin_assistants_router
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.session import get_db

KNOWN_MODELS = ["chat-standard", "chat-komplex", "ionos-gpt-oss-120b", "system-titel"]


def _assistant(id_, name, model, status="active"):
    return SimpleNamespace(id=id_, name=name, model=model, status=status)


def _admin() -> JwtPayload:
    return JwtPayload(
        sub="admin-1", roles=["admin"], grade=None, jti="j", iat=1, exp=9999999999
    )


def _make_client(assistants, *, known=KNOWN_MODELS, list_models_raises=False):
    """App mit gemocktem LiteLLM-Client und DB.

    Die DB-Filterung (`model != ''`, `status != 'archived'`) passiert in SQL; hier wird sie
    im Fake nachgebildet, damit der Test die Auswahllogik mitprüft.
    """
    app = FastAPI()
    app.include_router(admin_assistants_router)

    visible = [a for a in assistants if a.model and a.status != "archived"]

    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = visible
    db.execute = AsyncMock(return_value=result)

    async def _fake_db():
        yield db

    async def _fake_user():
        return _admin()

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = _fake_user

    client = AsyncMock()
    if list_models_raises:
        client.list_models.side_effect = RuntimeError("Proxy weg")
    else:
        client.list_models.return_value = known
    client.close.return_value = None

    return app, client


def _get(assistants, **kwargs):
    app, litellm = _make_client(assistants, **kwargs)
    with patch("app.litellm.client.LiteLLMClient", return_value=litellm):
        response = TestClient(app).get("/assistants/model-check")
    assert response.status_code == 200
    return response.json()


def test_reports_only_the_assistant_with_a_vanished_model():
    """Die Abnahme aus dem Plan: Alias, gültiger expliziter Name, verschwundener Name."""
    data = _get([
        _assistant(1, "Alias-Assistent", "chat-standard"),
        _assistant(2, "Gebunden, vorhanden", "ionos-gpt-oss-120b"),
        _assistant(3, "Gebunden, verschwunden", "anthropic-claude-sonnet-4-6"),
    ])

    assert data["checked"] is True
    assert [o["name"] for o in data["orphaned"]] == ["Gebunden, verschwunden"]
    assert data["orphaned"][0]["model"] == "anthropic-claude-sonnet-4-6"


def test_empty_model_is_not_a_warning():
    """Ein Assistent ohne eigenes Modell folgt CHAT_DEFAULT_MODEL (Schritt 7)."""
    data = _get([
        _assistant(1, "Ohne Modell", ""),
        _assistant(2, "Kaputt", "weg-damit"),
    ])

    assert [o["name"] for o in data["orphaned"]] == ["Kaputt"]


def test_archived_assistants_are_ignored():
    """Archivierte laufen ohnehin nicht — sie als Problem zu melden wäre Rauschen."""
    data = _get([
        _assistant(1, "Archiviert", "weg-damit", status="archived"),
        _assistant(2, "Aktiv", "weg-damit"),
    ])

    assert [o["name"] for o in data["orphaned"]] == ["Aktiv"]


def test_all_healthy_yields_empty_list():
    data = _get([
        _assistant(1, "A", "chat-standard"),
        _assistant(2, "B", "chat-komplex"),
    ])

    assert data == {"checked": True, "orphaned": []}


def test_unreachable_litellm_is_distinguishable_from_all_clear():
    """Ausfall darf nicht wie „alles in Ordnung" aussehen.

    Ohne das `checked`-Flag wäre ein leerer `orphaned`-Array zweideutig — und die UI würde
    bei einem Proxy-Ausfall fälschlich Entwarnung geben.
    """
    data = _get([_assistant(1, "Kaputt", "weg-damit")], list_models_raises=True)

    assert data["checked"] is False
    assert data["orphaned"] == []


def test_status_is_reported_for_prioritisation():
    """Ein aktiver Assistent wiegt schwerer als ein Entwurf — die UI soll das zeigen können."""
    data = _get([_assistant(7, "Entwurf", "weg-damit", status="draft")])

    assert data["orphaned"][0]["status"] == "draft"
    assert data["orphaned"][0]["id"] == 7


def test_system_models_count_as_known():
    """Der Modellwähler-Filter (Schritt 10) ist kosmetisch — hier zählt die volle Liste.

    Sonst würde ein bewusst auf `system-titel` gesetzter Assistent fälschlich als defekt
    gemeldet.
    """
    data = _get([_assistant(1, "Titel-Sonderfall", "system-titel")])

    assert data["orphaned"] == []
