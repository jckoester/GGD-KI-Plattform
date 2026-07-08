"""Artefaktbibliothek-Endpunkte (Phase 18).

Schritt 1: Auslieferung der Artefakt-Bytes (Pseudonym-Auth, analog `GET /images/{id}`).
Schritt 2: „In Bibliothek speichern" — Promotion von Chat-Inhalten (Bild/Diagramm).
Liste/Löschen/Download-Varianten kommen in Schritt 3.
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

import re

from app.artifacts import geogebra, promote, store
from app.artifacts.limits import get_artifact_limits
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.models import Artifact
from app.db.session import get_db
from app.render.errors import RenderError

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

_GGB_MIME = "application/vnd.geogebra.file"


def _ggb_filename(title: str | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "funktionsgraph").lower()).strip("-")[:60]
    return f"{slug or 'funktionsgraph'}.ggb"


def _ggb_response(data: bytes, title: str | None) -> Response:
    return Response(
        content=data,
        media_type=_GGB_MIME,
        headers={"Content-Disposition": f'attachment; filename="{_ggb_filename(title)}"'},
    )

# SVG-Artefakte können (mermaid) aus Client-gerendertem Markup stammen. Auslieferung nur an
# die Eigentümer:in, aber zusätzlich gehärtet: kein Skript, kein aktiver Inhalt, kein Sniffing.
_SVG_HARDENING = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "X-Content-Type-Options": "nosniff",
}


class SavedArtifact(BaseModel):
    """Antwort nach „In Bibliothek speichern"."""

    id: UUID
    kind: str
    mime_type: str
    title: str
    byte_size: int
    created_at: datetime
    expires_at: datetime
    created: bool  # False ⇒ war bereits in der Bibliothek (idempotent)


class ArtifactItem(BaseModel):
    """Ein Bibliotheks-Eintrag (Metadaten + roher Quelltext für Kopieren/Download)."""

    id: UUID
    kind: str
    mime_type: str
    title: str
    byte_size: int
    source: str | None
    created_at: datetime
    expires_at: datetime


class LibraryResponse(BaseModel):
    items: list[ArtifactItem]
    used_bytes: int
    quota_bytes: int


class FromImageRequest(BaseModel):
    image_id: UUID
    title: str | None = None


class FromDiagramRequest(BaseModel):
    kind: str            # circuit | plot | mermaid
    source: str
    svg: str | None = None   # nur mermaid: bereits im Browser gerendertes SVG
    title: str | None = None


class GgbRequest(BaseModel):
    source: str          # rohe Plot-Spec (YAML)
    title: str | None = None


def _saved(artifact: Artifact, created: bool) -> SavedArtifact:
    return SavedArtifact(
        id=artifact.id,
        kind=artifact.kind,
        mime_type=artifact.mime_type,
        title=artifact.title,
        byte_size=artifact.byte_size,
        created_at=artifact.created_at,
        expires_at=artifact.expires_at,
        created=created,
    )


@router.post("/from-image", response_model=SavedArtifact)
async def save_image_to_library(
    req: FromImageRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedArtifact:
    """Promotet ein generiertes Bild in die Bibliothek der eingeloggten Nutzer:in."""
    try:
        artifact, created = await promote.promote_image(
            db, user=current_user, image_id=req.image_id, title=req.title
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    except store.QuotaExceeded:
        raise HTTPException(
            status_code=409,
            detail="Deine Bibliothek ist voll. Bitte lösche zuerst ältere Artefakte.",
        )
    except promote.PromotionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _saved(artifact, created)


@router.post("/from-diagram", response_model=SavedArtifact)
async def save_diagram_to_library(
    req: FromDiagramRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedArtifact:
    """Promotet ein gerendertes Diagramm (circuit/plot server-, mermaid client-gerendert)."""
    if req.kind not in promote.DIAGRAM_KINDS:
        raise HTTPException(status_code=422, detail="unbekannter Diagrammtyp")
    try:
        artifact, created = await promote.promote_diagram(
            db, user=current_user, kind=req.kind, source=req.source,
            svg=req.svg, title=req.title,
        )
    except store.QuotaExceeded:
        raise HTTPException(
            status_code=409,
            detail="Deine Bibliothek ist voll. Bitte lösche zuerst ältere Artefakte.",
        )
    except promote.PromotionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _saved(artifact, created)


@router.get("", response_model=LibraryResponse)
async def list_library(
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LibraryResponse:
    """Die eigene Bibliothek (neueste zuerst) + Belegung/Quota für die Anzeige."""
    records = await store.list_artifacts(db, current_user.sub)
    used = await store.used_bytes(db, current_user.sub)
    _, quota_bytes = get_artifact_limits(current_user.roles, current_user.grade)
    items = [
        ArtifactItem(
            id=r.id, kind=r.kind, mime_type=r.mime_type, title=r.title,
            byte_size=r.byte_size, source=r.source,
            created_at=r.created_at, expires_at=r.expires_at,
        )
        for r in records
    ]
    return LibraryResponse(items=items, used_bytes=used, quota_bytes=quota_bytes)


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
    headers = _SVG_HARDENING if record.mime_type == "image/svg+xml" else None
    return Response(content=data, media_type=record.mime_type, headers=headers)


@router.delete("/{artifact_id}")
async def delete_artifact_endpoint(
    artifact_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Löscht ein Artefakt (Row + Datei) — nur die Eigentümer:in."""
    record = await store.get_artifact(db, artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Artefakt nicht gefunden")
    if record.owner_pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    await store.delete_artifact(db, record)
    return {"ok": True}


@router.post("/ggb")
async def ggb_from_source(
    req: GgbRequest,
    _: JwtPayload = Depends(get_current_user),
) -> Response:
    """Konvertiert eine rohe Plot-Spec direkt in eine `.ggb`-Datei (Download im Chat).

    Zustandslos (kein Persistenzbezug) — nur eingeloggt. 422 bei ungültiger Plot-Spec.
    """
    try:
        data = geogebra.ggb_bytes_from_source(req.source)
    except RenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _ggb_response(data, req.title)


@router.get("/{artifact_id}/ggb")
async def ggb_from_artifact(
    artifact_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """`.ggb`-Export eines gespeicherten Plot-Artefakts (aus dessen `source`)."""
    record = await store.get_artifact(db, artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Artefakt nicht gefunden")
    if record.owner_pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    if record.kind != "plot" or not record.source:
        raise HTTPException(status_code=422, detail="Kein GeoGebra-Export für dieses Artefakt")
    try:
        data = geogebra.ggb_bytes_from_source(record.source)
    except RenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _ggb_response(data, record.title)
