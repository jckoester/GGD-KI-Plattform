import pytest
from pydantic import ValidationError
from app.chat.schemas import ChatMessage, ChatRequest, TextPart, ImageUrlPart


def test_chat_message_string_content():
    msg = ChatMessage(role="user", content="Hallo")
    assert msg.content == "Hallo"


def test_chat_message_multimodal_content():
    msg = ChatMessage(role="user", content=[
        {"type": "text", "text": "Was zeigt das Bild?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
    ])
    assert isinstance(msg.content, list)
    assert isinstance(msg.content[0], TextPart)
    assert isinstance(msg.content[1], ImageUrlPart)
    assert msg.content[1].image_url.url == "data:image/png;base64,abc"


def test_chat_message_invalid_content_part():
    with pytest.raises(ValidationError):
        ChatMessage(role="user", content=[{"type": "unknown", "foo": "bar"}])


def test_chat_request_empty_messages_raises():
    with pytest.raises(ValidationError):
        ChatRequest(messages=[])


def test_chat_request_with_assistant_id():
    req = ChatRequest(
        messages=[ChatMessage(role="user", content="Hallo")],
        assistant_id=5,
    )
    assert req.assistant_id == 5


def test_chat_request_without_assistant_id_defaults_to_none():
    req = ChatRequest(
        messages=[ChatMessage(role="user", content="Hallo")],
    )
    assert req.assistant_id is None
