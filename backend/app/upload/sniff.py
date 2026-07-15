"""Magic-Byte-Prüfung für Uploads (Sicherheits-Audit #14).

Die Dateiendung allein bestimmt den Typ nicht verlässlich — der tatsächliche Inhalt muss zur
deklarierten Art passen. Defense-in-Depth gegen umbenannte/gefälschte Dateien (z. B. eine
HTML/SVG-Datei mit `.png`-Endung, die sonst als `data:image/png`-URI weitergereicht würde).
"""


def _is_pdf(data: bytes) -> bool:
    # Laut PDF-Spezifikation muss `%PDF-` innerhalb der ersten 1024 Bytes stehen.
    return b"%PDF-" in data[:1024]


def _is_png(data: bytes) -> bool:
    return data[:8] == b"\x89PNG\r\n\x1a\n"


def _is_jpeg(data: bytes) -> bool:
    return data[:3] == b"\xff\xd8\xff"


def _is_webp(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"


_IMAGE_SNIFFERS = {
    "image/png": _is_png,
    "image/jpeg": _is_jpeg,
    "image/webp": _is_webp,
}


def _looks_binary(data: bytes) -> bool:
    # Ein NUL-Byte in den ersten 8 KB spricht stark gegen eine (UTF-8-)Textdatei.
    return b"\x00" in data[:8192]


def content_matches(declared_type: str, data: bytes) -> bool:
    """Prüft, ob der Byte-Inhalt zur deklarierten Art (aus EXTENSION_MAP) passt.

    `declared_type` ist einer der EXTENSION_MAP-Werte: ``pdf``, ``text`` oder ein Bild-MIME
    (``image/png`` etc.). Für Text gibt es keine Signatur — hier wird nur grob geprüft, dass
    die Datei nicht offensichtlich binär ist.
    """
    if declared_type == "pdf":
        return _is_pdf(data)
    if declared_type in _IMAGE_SNIFFERS:
        return _IMAGE_SNIFFERS[declared_type](data)
    if declared_type == "text":
        return not _looks_binary(data)
    return False
