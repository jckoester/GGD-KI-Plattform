from app.chat.schemas import TextPart, ImageUrlPart, ImageUrlContent
from app.chat.router import _text_from_content, _serialize_content


def test_text_from_content_string():
    assert _text_from_content("Hallo") == "Hallo"


def test_text_from_content_list_text_only():
    parts = [TextPart(type="text", text="Wort1"), TextPart(type="text", text="Wort2")]
    assert _text_from_content(parts) == "Wort1 Wort2"


def test_text_from_content_list_mixed():
    parts = [
        TextPart(type="text", text="Beschreibe das:"),
        ImageUrlPart(type="image_url", image_url=ImageUrlContent(url="data:image/png;base64,abc")),
    ]
    assert _text_from_content(parts) == "Beschreibe das:"


def test_text_from_content_list_image_only():
    parts = [ImageUrlPart(type="image_url", image_url=ImageUrlContent(url="data:image/png;base64,abc"))]
    assert _text_from_content(parts) == ""


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
