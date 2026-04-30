import pytest
from app.upload.extractor import extract_plaintext, extract_pdf


def test_extract_plaintext_utf8():
    assert extract_plaintext(b"Hallo Welt") == "Hallo Welt"


def test_extract_plaintext_latin1_fallback():
    # 0xe4 = 'ä' in Latin-1
    result = extract_plaintext(bytes([0x48, 0xe4, 0x6c, 0x6c, 0x6f]))
    assert "H" in result


def test_extract_pdf_invalid_raises():
    with pytest.raises(ValueError, match="PDF konnte nicht gelesen werden"):
        extract_pdf(b"not a pdf")
