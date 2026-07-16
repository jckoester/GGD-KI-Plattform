"""PDF laden (URL/lokal) + seiten-bewusste Textextraktion.

Bewusst schlank und ohne Backend-Kopplung — nutzt pdfminer direkt (in der Backend-venv
verfügbar, `pdfminer.six`). Die Seitenauswahl erlaubt es, für den LFDB-Import nur die
Tabellenseiten (Baustein/Leitfrage) zu lesen (E3).
"""
from __future__ import annotations

import io
from pathlib import Path

import httpx
from pdfminer.high_level import extract_text as _pdf_extract_text

_USER_AGENT = "GGD-KI-Plattform-PDF-Import/1.0"


def parse_page_spec(spec: str | None) -> set[int] | None:
    """'1-5,7' (1-indexiert, menschlich) → {0,1,2,3,4,6} (0-indexiert für pdfminer).

    None/leer → None (alle Seiten). Wirft ValueError bei ungültigem Bereich.
    """
    if not spec or not spec.strip():
        return None
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
            if start < 1 or end < start:
                raise ValueError(f"Ungültiger Seitenbereich: {part!r}")
            pages.update(range(start - 1, end))
        else:
            n = int(part)
            if n < 1:
                raise ValueError(f"Ungültige Seitennummer: {part!r}")
            pages.add(n - 1)
    return pages or None


def load_pdf_bytes(source: str, *, timeout: float = 60.0) -> bytes:
    """Lädt die PDF-Bytes von einer URL (http/https) oder einem lokalen Pfad."""
    if source.startswith(("http://", "https://")):
        resp = httpx.get(
            source,
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.content
    return Path(source).read_bytes()


def extract_text(data: bytes, pages: set[int] | None = None) -> str:
    """Extrahiert Text (optional nur die 0-indexierten `pages`). ValueError bei Lesefehler
    oder leerem Ergebnis (gescanntes PDF / falsche Seitenauswahl)."""
    try:
        text = _pdf_extract_text(io.BytesIO(data), page_numbers=pages)
    except Exception as exc:  # pdfminer wirft diverse Fehlertypen
        raise ValueError(f"PDF konnte nicht gelesen werden: {exc}") from exc
    if not text or not text.strip():
        raise ValueError(
            "PDF enthält keinen extrahierbaren Text (evtl. gescannt oder falsche Seitenauswahl)."
        )
    return text.strip()
