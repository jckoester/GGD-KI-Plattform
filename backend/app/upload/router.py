import base64
import logging
from pathlib import Path
from typing import Annotated, Literal, Union

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from app.auth.jwt import JwtPayload
from app.config import settings
from app.ratelimit.dependency import rate_limit
from app.upload.extractor import extract_pdf, extract_plaintext
from app.upload.sniff import content_matches

logger = logging.getLogger(__name__)
router = APIRouter(tags=["upload"])

EXTENSION_MAP: dict[str, str] = {
    ".pdf": "pdf",
    ".txt": "text",
    ".md": "text",
    ".csv": "text",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class TextUploadResult(BaseModel):
    type: Literal["text"] = "text"
    filename: str
    content: str
    size_bytes: int


class ImageUploadResult(BaseModel):
    type: Literal["image"] = "image"
    filename: str
    data: str  # base64-kodiert
    mime_type: str
    size_bytes: int


UploadResult = Annotated[
    Union[TextUploadResult, ImageUploadResult],
    Field(discriminator="type")
]


# Hinweis: Dieser Endpoint ist zustandslos — eine Datei pro Request, kein Session-Tracking.
# `settings.upload_max_files` (max. Anhänge pro Nachricht) wird deshalb dort erzwungen, wo es
# semantisch greift: bei der Chat-Nachrichten-Annahme (app/chat/router.py, Audit #10). Gegen
# Volumen-Missbrauch am Endpoint selbst wirken das Rate-Limit (`rate_limit("upload")`, Audit #2),
# `upload_max_bytes` und `client_max_body_size` im Reverse-Proxy (Audit #5).
@router.post("/upload/session", response_model=UploadResult)
async def upload_session(
    file: UploadFile = File(...),
    current_user: JwtPayload = Depends(rate_limit("upload")),
) -> UploadResult:
    # Dateiendung bestimmen
    suffix = Path(file.filename or "").suffix.lower()
    file_type = EXTENSION_MAP.get(suffix)
    if file_type is None:
        raise HTTPException(
            status_code=415,
            detail=f"Dateiformat '{suffix}' wird nicht unterstützt. "
                   f"Erlaubt: {', '.join(EXTENSION_MAP.keys())}",
        )

    # Inhalt lesen
    data = await file.read()
    size = len(data)

    if size == 0:
        raise HTTPException(status_code=422, detail="Datei ist leer.")
    if size > settings.upload_max_bytes:
        limit_mb = settings.upload_max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"Datei zu groß ({size // (1024*1024)} MB). Maximum: {limit_mb} MB.",
        )

    # Magic-Byte-Prüfung (Audit #14): Inhalt muss zur Endung passen — Defense-in-Depth gegen
    # umbenannte/gefälschte Dateien. Die Endung allein legt den Typ nicht fest.
    if not content_matches(file_type, data):
        raise HTTPException(
            status_code=415,
            detail=f"Der Dateiinhalt passt nicht zur Endung '{suffix}'. "
                   "Bitte eine unveränderte Datei des angegebenen Typs hochladen.",
        )

    filename = file.filename or "datei"

    # Verarbeitung nach Typ
    if file_type == "pdf":
        try:
            content = extract_pdf(data)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return TextUploadResult(filename=filename, content=content, size_bytes=size)

    if file_type == "text":
        content = extract_plaintext(data)
        return TextUploadResult(filename=filename, content=content, size_bytes=size)

    # Bild
    encoded = base64.b64encode(data).decode("ascii")
    return ImageUploadResult(
        filename=filename,
        data=encoded,
        mime_type=file_type,  # z.B. "image/png"
        size_bytes=size,
    )
