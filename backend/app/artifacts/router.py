"""Artefaktbibliothek-Endpunkte (Phase 18).

Schritt 1: Auslieferung der Artefakt-Bytes (Pseudonym-Auth, analog `GET /images/{id}`).
Liste/Speichern/Löschen kommen in Schritt 2/3.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.artifacts import store
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.session import get_db

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}")
async def get_artifact_file(
    artifact_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Liefert die Artefakt-Bytes — nur an die Eigentümer:in (Pseudonym-Autorisierung)."""
    record = await store.get_artifact(db, artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Artefakt nicht gefunden")
    if record.owner_pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    data = store.read_artifact_bytes(record)
    if data is None:
        raise HTTPException(status_code=404, detail="Artefakt-Datei nicht gefunden")
    return Response(content=data, media_type=record.mime_type)
