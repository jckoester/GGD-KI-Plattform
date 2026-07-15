"""Unit-Tests: Magic-Byte-Prüfung für Uploads (Sicherheits-Audit #14)."""
from app.upload.sniff import content_matches

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 16
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n" + b"1 0 obj" * 4


def test_pdf_valid():
    assert content_matches("pdf", PDF) is True


def test_pdf_with_leading_junk_within_1024():
    assert content_matches("pdf", b"junk " * 3 + PDF) is True


def test_pdf_rejects_non_pdf():
    assert content_matches("pdf", b"not a pdf at all") is False


def test_pdf_rejects_png_bytes():
    assert content_matches("pdf", PNG) is False


def test_png_valid():
    assert content_matches("image/png", PNG) is True


def test_jpeg_valid():
    assert content_matches("image/jpeg", JPEG) is True


def test_webp_valid():
    assert content_matches("image/webp", WEBP) is True


def test_webp_too_short_rejected():
    assert content_matches("image/webp", b"RIFF") is False


def test_image_format_mismatch_rejected():
    # JPEG-Bytes, aber als PNG deklariert → abgelehnt (MIME muss zum Inhalt passen).
    assert content_matches("image/png", JPEG) is False
    assert content_matches("image/jpeg", PNG) is False


def test_html_renamed_as_png_rejected():
    # Der klassische Smuggle-Fall: HTML/SVG mit .png-Endung.
    html = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
    assert content_matches("image/png", html) is False


def test_text_plain_ascii_ok():
    assert content_matches("text", b"Hallo Welt, das ist Text.\n") is True


def test_text_utf8_ok():
    assert content_matches("text", "Grüße mit Ümläüten".encode("utf-8")) is True


def test_text_rejects_binary_with_nul():
    assert content_matches("text", b"abc\x00def binary") is False


def test_unknown_declared_type_rejected():
    assert content_matches("application/x-evil", b"whatever") is False
