from pdfminer.high_level import extract_text as _pdf_extract_text
import io


def extract_pdf(data: bytes) -> str:
    """Extrahiert Text aus PDF-Bytes. Wirft ValueError bei Lesefehler."""
    try:
        text = _pdf_extract_text(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"PDF konnte nicht gelesen werden: {exc}") from exc
    if not text or not text.strip():
        raise ValueError("PDF enthält keinen extrahierbaren Text (möglicherweise gescannt).")
    return text.strip()


def extract_plaintext(data: bytes) -> str:
    """Dekodiert Plaintext-Bytes. Versucht UTF-8, fällt auf Latin-1 zurück."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")
