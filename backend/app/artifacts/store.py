"""Persistenz-Store der Artefaktbibliothek (Phase 18).

Bytes auf Disk (`settings.artifact_storage_dir`), Metadaten in der Tabelle `artifacts`.
Speichern prüft die Per-User-Quota und friert `expires_at` aus der role-/jahrgangsbasierten
Aufbewahrung ein (kein Rollen-Lookup im Cleanup nötig). Muster analog `app/chat/image_store.py`.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.artifacts.limits import get_artifact_limits
from app.config import settings
from app.db.models import Artifact

logger = logging.getLogger(__name__)

_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "application/vnd.geogebra.file": ".ggb",
}


class QuotaExceeded(Exception):
    """Die Bibliothek der Nutzer:in ist voll (Quota überschritten)."""


def storage_dir() -> Path:
    d = Path(settings.artifact_storage_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file_path(artifact_id: UUID, mime_type: str) -> Path:
    return storage_dir() / f"{artifact_id}{_EXT_BY_MIME.get(mime_type, '.bin')}"


def _now(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now(timezone.utc)


async def used_bytes(db: AsyncSession, owner_pseudonym: str) -> int:
    """Aktuell belegte Gesamtgröße der Bibliothek dieser Nutzer:in."""
    result = await db.execute(
        select(func.coalesce(func.sum(Artifact.byte_size), 0)).where(
            Artifact.owner_pseudonym == owner_pseudonym
        )
    )
    return int(result.scalar_one())


async def save_artifact(
    db: AsyncSession,
    *,
    owner_pseudonym: str,
    roles: list[str],
    grade: Optional[int],
    kind: str,
    mime_type: str,
    data: bytes,
    title: str,
    source: Optional[str] = None,
    origin_conversation_id: Optional[UUID] = None,
    now: Optional[datetime] = None,
) -> Artifact:
    """Speichert ein Artefakt: Quota prüfen → Bytes auf Disk → Row mit `expires_at`.

    Wirft `QuotaExceeded`, wenn die Bibliothek der Nutzer:in dadurch überliefe.
    """
    retention_days, quota_bytes = get_artifact_limits(roles, grade)
    size = len(data)
    used = await used_bytes(db, owner_pseudonym)
    if used + size > quota_bytes:
        raise QuotaExceeded(
            f"Bibliothek voll: {used + size} > {quota_bytes} Bytes"
        )

    artifact_id = uuid4()
    _file_path(artifact_id, mime_type).write_bytes(data)

    ts = _now(now)
    artifact = Artifact(
        id=artifact_id,
        owner_pseudonym=owner_pseudonym,
        kind=kind,
        mime_type=mime_type,
        byte_size=size,
        title=title,
        source=source,
        origin_conversation_id=origin_conversation_id,
        created_at=ts,
        expires_at=ts + timedelta(days=retention_days),
    )
    db.add(artifact)
    await db.commit()
    return artifact


async def get_artifact(db: AsyncSession, artifact_id: UUID) -> Optional[Artifact]:
    return await db.get(Artifact, artifact_id)


async def list_artifacts(db: AsyncSession, owner_pseudonym: str) -> list[Artifact]:
    result = await db.execute(
        select(Artifact)
        .where(Artifact.owner_pseudonym == owner_pseudonym)
        .order_by(Artifact.created_at.desc())
    )
    return list(result.scalars().all())


def read_artifact_bytes(record: Artifact) -> Optional[bytes]:
    path = _file_path(record.id, record.mime_type)
    if not path.exists():
        return None
    return path.read_bytes()


async def delete_artifact(db: AsyncSession, record: Artifact) -> None:
    path = _file_path(record.id, record.mime_type)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Artefakt-Datei nicht löschbar: %s", path)
    await db.delete(record)
    await db.commit()


@dataclass
class ArtifactCleanupStats:
    scanned: int
    expired_removed: int


async def cleanup_artifacts(
    db: AsyncSession, *, now: Optional[datetime] = None, dry_run: bool = False
) -> ArtifactCleanupStats:
    """Löscht abgelaufene Artefakte (`expires_at < now`) + ihre Dateien."""
    ts = _now(now)
    result = await db.execute(select(Artifact).where(Artifact.expires_at < ts))
    expired = list(result.scalars().all())
    if not dry_run and expired:
        for a in expired:
            try:
                _file_path(a.id, a.mime_type).unlink(missing_ok=True)
            except OSError:
                logger.warning("Artefakt-Datei nicht löschbar: %s", a.id)
        await db.execute(delete(Artifact).where(Artifact.expires_at < ts))
        await db.commit()
    return ArtifactCleanupStats(scanned=len(expired), expired_removed=len(expired))
