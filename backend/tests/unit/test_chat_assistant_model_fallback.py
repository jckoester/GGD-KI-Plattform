"""Unit-Tests: Ein Assistent ohne eigenes Modell nutzt den schulweiten Standard.

Damit ein Assistent einen Modellwechsel automatisch mitmacht, darf `assistants.model` leer
bleiben. Der Chat-Flow muss dann `CHAT_DEFAULT_MODEL` einsetzen — täte er das nicht, ginge
ein leerer Modellname an LiteLLM und der Chat bräche.

Die beiden Zweige (Assistent an einer bestehenden Konversation / neu gewählter Assistent)
prüfen das getrennt; einer der beiden hatte die Leerprüfung bisher nicht.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.auth.jwt import JwtPayload
from app.chat.router import chat
from app.chat.schemas import ChatRequest

from tests.unit.test_chat_models import _FakeHttpClient, _FAKE_LITELLM_KEY


def _payload() -> JwtPayload:
    return JwtPayload(
        sub="pseudo-1", roles=["teacher"], grade=None, jti="jti-1", iat=1, exp=9999999999
    )


def _assistant(model: str):
    """Minimaler Assistent, der die Sichtbarkeitsprüfung passiert."""
    return SimpleNamespace(
        id=1, name="Testassistent", system_prompt="Du bist hilfreich.",
        model=model, status="active", audience="all", scope="school",
        visibility="public", created_by="pseudo-1", min_grade=None, max_grade=None,
        available_from=None, available_until=None, tool_groups=[], subject_id=None,
        scope_group_id=None, disabled_augmentations=[], temperature=None, max_tokens=None,
    )


def _db_with_assistant(assistant):
    """db.execute liefert erst den Assistenten, danach generische Treffer."""
    calls = [0]

    def _side_effect(*args, **kwargs):
        calls[0] += 1
        result = MagicMock()
        if calls[0] == 1:
            result.scalar_one_or_none.return_value = assistant
        else:
            result.scalar_one_or_none.return_value = _FAKE_LITELLM_KEY
        result.scalars.return_value.all.return_value = []
        result.scalars.return_value.first.return_value = None
        result.fetchone.return_value = None
        return result

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    db.execute = AsyncMock(side_effect=_side_effect)
    return db


async def _run_chat(assistant, *, model_id=None, default_model="chat-standard"):
    db = _db_with_assistant(assistant)
    http = _FakeHttpClient()
    request = ChatRequest(
        messages=[{"role": "user", "content": "Hallo"}],
        assistant_id=assistant.id,
        model_id=model_id,
    )
    with patch("app.chat.router.httpx.AsyncClient", return_value=http), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = default_model
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3
        await chat(request, current_user=_payload(), db=db)
    return http.last_json


@pytest.mark.asyncio
async def test_empty_assistant_model_falls_back_to_default():
    """Der Kern von Schritt 7: leer = schulweiter Standard, kein leerer Modellname."""
    sent = await _run_chat(_assistant(""), default_model="chat-standard")
    assert sent["model"] == "chat-standard"


@pytest.mark.asyncio
async def test_assistant_model_wins_over_default():
    """Ein gesetztes Modell bindet den Assistenten weiterhin daran."""
    sent = await _run_chat(_assistant("chat-komplex"), default_model="chat-standard")
    assert sent["model"] == "chat-komplex"


@pytest.mark.asyncio
async def test_explicit_model_id_wins_over_assistant():
    """Eine ausdrückliche Modellwahl im Request schlägt beides."""
    sent = await _run_chat(
        _assistant("chat-komplex"), model_id="chat-schnell", default_model="chat-standard"
    )
    assert sent["model"] == "chat-schnell"


@pytest.mark.asyncio
async def test_explicit_model_id_wins_over_empty_assistant_model():
    sent = await _run_chat(
        _assistant(""), model_id="chat-schnell", default_model="chat-standard"
    )
    assert sent["model"] == "chat-schnell"
