import json
from app.chat.schemas import AttachmentMeta, ChatMessage, TextPart, ImageUrlPart, ImageUrlContent
from app.chat.router import _user_text, _serialize_content, _parse_stored_content


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
