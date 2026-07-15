import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.chat.schemas import AttachmentMeta, ChatMessage, TextPart, ImageUrlPart, ImageUrlContent
from app.chat.router import (
    _user_text, _serialize_content, _parse_stored_content, _crisis_sse_event, _CrisisRecord,
    _generate_title,
)
from app.crisis.detector import CrisisHit


def _crisis_hit(help_topic="crisis"):
    return CrisisHit(
        category="suizidalitaet",
        severity="alert",
        help_topic=help_topic,
        trigger_rule="crisis_triggers:suizidalitaet",
        coreviewer_role="review",
    )


def test_crisis_sse_event_none_without_record():
    assert _crisis_sse_event(None) is None


def test_crisis_sse_event_none_when_banner_suppressed():
    rec = _CrisisRecord(hit=_crisis_hit(), show_banner=False)
    assert _crisis_sse_event(rec) is None


def test_crisis_sse_event_emits_resolved_resources():
    rec = _CrisisRecord(hit=_crisis_hit("crisis"), show_banner=True)
    ev = _crisis_sse_event(rec)
    assert ev is not None
    assert ev.startswith("event: crisis\ndata: ")
    assert ev.endswith("\n\n")
    data = json.loads(ev.split("data: ", 1)[1].strip())
    assert data["help_topic"] == "crisis"
    assert data["label"]
    assert data["external"]


def test_crisis_sse_event_unknown_topic_returns_none():
    rec = _CrisisRecord(hit=_crisis_hit("nonexistent-topic"), show_banner=True)
    assert _crisis_sse_event(rec) is None


def test_user_text_string():
    msg = ChatMessage(role="user", content="Hallo")
    assert _user_text(msg) == "Hallo"


def test_user_text_list_no_attachments_joins_all():
    msg = ChatMessage(role="user", content=[
        TextPart(type="text", text="Wort1"),
        TextPart(type="text", text="Wort2"),
    ])
    assert _user_text(msg) == "Wort1 Wort2"


def test_user_text_list_no_attachments_mixed():
    msg = ChatMessage(role="user", content=[
        TextPart(type="text", text="Beschreibe das:"),
        ImageUrlPart(type="image_url", image_url=ImageUrlContent(url="data:image/png;base64,abc")),
    ])
    assert _user_text(msg) == "Beschreibe das:"


def test_user_text_list_no_attachments_image_only():
    msg = ChatMessage(role="user", content=[
        ImageUrlPart(type="image_url", image_url=ImageUrlContent(url="data:image/png;base64,abc")),
    ])
    assert _user_text(msg) == ""


def test_user_text_with_attachments_last_text_part():
    # buildUserContent puts file text parts first, user text last
    msg = ChatMessage(
        role="user",
        content=[
            TextPart(type="text", text="[dokument.pdf]\nDateiinhalt hier"),
            TextPart(type="text", text="Nutzertext"),
        ],
        attachments=[AttachmentMeta(name="dokument.pdf", type="text")],
    )
    assert _user_text(msg) == "Nutzertext"


def test_user_text_with_attachments_no_user_text():
    # Only file content, no user text appended
    msg = ChatMessage(
        role="user",
        content=[TextPart(type="text", text="[doc.pdf]\nInhalt")],
        attachments=[AttachmentMeta(name="doc.pdf", type="text")],
    )
    # Last (only) TextPart is the file content — acceptable fallback
    assert _user_text(msg) == "[doc.pdf]\nInhalt"


def test_user_text_with_image_attachment_and_text():
    msg = ChatMessage(
        role="user",
        content=[
            ImageUrlPart(type="image_url", image_url=ImageUrlContent(url="data:image/png;base64,abc")),
            TextPart(type="text", text="Was ist das?"),
        ],
        attachments=[AttachmentMeta(name="bild.png", type="image")],
    )
    assert _user_text(msg) == "Was ist das?"


def test_serialize_content_string():
    assert _serialize_content("Hallo") == "Hallo"


def test_serialize_content_list():
    parts = [
        TextPart(type="text", text="Test"),
        ImageUrlPart(type="image_url", image_url=ImageUrlContent(url="data:image/png;base64,abc")),
    ]
    result = _serialize_content(parts)
    assert result == [
        {"type": "text", "text": "Test"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
    ]


def test_parse_stored_content_plain_string():
    text, files = _parse_stored_content("Hallo Welt")
    assert text == "Hallo Welt"
    assert files == []


def test_parse_stored_content_structured():
    stored = json.dumps({"v": 1, "text": "Nutzertext", "files": [{"name": "doc.pdf", "type": "text"}]})
    text, files = _parse_stored_content(stored)
    assert text == "Nutzertext"
    assert len(files) == 1
    assert files[0].name == "doc.pdf"
    assert files[0].type == "text"


def test_parse_stored_content_invalid_json():
    text, files = _parse_stored_content("{broken json")
    assert text == "{broken json"
    assert files == []


def test_parse_stored_content_skips_invalid_files():
    stored = json.dumps({"v": 1, "text": "Text", "files": [
        {"name": "ok.pdf", "type": "text"},
        {"name": "bad.bin", "type": "unknown"},  # invalid type
        {},  # missing fields
    ]})
    text, files = _parse_stored_content(stored)
    assert text == "Text"
    assert len(files) == 1
    assert files[0].name == "ok.pdf"


# ========== _get_guardrail_prompt ==========

@pytest.mark.asyncio
async def test_get_guardrail_prompt_returns_value():
    """DB liefert 'Testprompt' → Funktion gibt ihn zurück und befüllt Cache."""
    from app.chat.router import _get_guardrail_prompt
    import app.chat.router as chat_router
    chat_router._guardrail_prompt_cache = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "Testprompt"
    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    result = await _get_guardrail_prompt(mock_db)

    assert result == "Testprompt"
    assert chat_router._guardrail_prompt_cache is not None
    assert chat_router._guardrail_prompt_cache[0] == "Testprompt"


@pytest.mark.asyncio
async def test_get_guardrail_prompt_returns_none_when_missing():
    """DB liefert None (kein Eintrag) → Funktion gibt None zurück."""
    from app.chat.router import _get_guardrail_prompt
    import app.chat.router as chat_router
    chat_router._guardrail_prompt_cache = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    result = await _get_guardrail_prompt(mock_db)

    assert result is None


@pytest.mark.asyncio
async def test_get_guardrail_prompt_uses_cache():
    """Frischer Cache → DB wird nicht abgefragt."""
    from app.chat.router import _get_guardrail_prompt
    import app.chat.router as chat_router

    future = asyncio.get_event_loop().time() + 60
    chat_router._guardrail_prompt_cache = ("CachedPrompt", future)

    mock_db = AsyncMock()
    result = await _get_guardrail_prompt(mock_db)

    assert result == "CachedPrompt"
    mock_db.execute.assert_not_called()


# --- Titelgenerierung: budgetiert über User-Virtual-Key (Sicherheits-Audit #8) ---

def _mock_title_client(content="Ein kurzer Titel"):
    """Mockt httpx.AsyncClient für _generate_title und gibt (client, captured) zurück.

    `captured` sammelt die build_request-kwargs (headers/json), damit der Test prüfen
    kann, welcher Key + welches user-Feld verwendet wurde.
    """
    captured = {}
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value={"choices": [{"message": {"content": content}}]})

    def _build_request(method, url, headers=None, json=None):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return MagicMock()

    client = MagicMock()
    client.build_request = MagicMock(side_effect=_build_request)
    client.send = AsyncMock(return_value=response)
    client.aclose = AsyncMock()
    return client, captured


@asynccontextmanager
async def _noop_session():
    db = AsyncMock()
    yield db


@pytest.mark.asyncio
async def test_generate_title_uses_virtual_key_and_user_sub():
    """Titel-Call läuft über den User-Virtual-Key + user=sub, nicht über den Master-Key (#8)."""
    client, captured = _mock_title_client("Bruchrechnung üben")
    with patch("app.chat.router.httpx.AsyncClient", return_value=client), \
         patch("app.chat.router.AsyncSessionLocal", _noop_session), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.title_model = "openai/gpt-4o-mini"
        mock_settings.litellm_proxy_url = "http://proxy"
        mock_settings.litellm_verify_ssl = True
        mock_settings.litellm_master_key = "sk-MASTER-should-not-be-used"

        title = await _generate_title(uuid4(), "Erkläre mir Brüche", "sk-user-vkey", "pseudo-abc")

    assert title == "Bruchrechnung üben"
    assert captured["headers"]["Authorization"] == "Bearer sk-user-vkey"
    assert "sk-MASTER-should-not-be-used" not in captured["headers"]["Authorization"]
    assert captured["json"]["user"] == "pseudo-abc"
    assert captured["json"]["user"] != "titlegen"


@pytest.mark.asyncio
async def test_generate_title_skips_without_key():
    """Ohne Virtual-Key kein Master-Key-Fallback → None, kein HTTP-Call."""
    client, captured = _mock_title_client()
    with patch("app.chat.router.httpx.AsyncClient", return_value=client) as mk, \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.title_model = "openai/gpt-4o-mini"

        title = await _generate_title(uuid4(), "Prompt", "", "pseudo-abc")

    assert title is None
    mk.assert_not_called()
    assert captured == {}
