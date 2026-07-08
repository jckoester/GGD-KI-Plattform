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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.artifacts.limits import get_artifact_limits
from app.config import settings
from app.db.models import Artifact

logger = logging.getLogger(__name__)

# Repo-Root: backend/app/artifacts/store.py → parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]

_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "application/vnd.geogebra.file": ".ggb",
}


class QuotaExceeded(Exception):
    """Die Bibliothek der Nutzer:in ist voll (Quota überschritten)."""


def storage_dir() -> Path:
    """Ablageverzeichnis (repo-root-relativ, falls nicht absolut) — cwd-unabhängig.

    Wichtig für den Cleanup-Cron: der läuft nicht aus dem Backend-Verzeichnis, muss aber
    denselben Pfad auflösen wie das Backend beim Speichern (analog `image_store`)."""
    base = Path(settings.artifact_storage_dir)
    d = base if base.is_absolute() else _REPO_ROOT / base
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


async def find_by_origin_ref(
    db: AsyncSession, owner_pseudonym: str, origin_ref: str
) -> Optional[Artifact]:
    """Bereits gespeichertes Artefakt gleicher Herkunft (Idempotenz von „In Bibliothek speichern")."""
    result = await db.execute(
        select(Artifact).where(
            Artifact.owner_pseudonym == owner_pseudonym,
            Artifact.origin_ref == origin_ref,
        )
    )
    return result.scalars().first()


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
    origin_ref: Optional[str] = None,
    origin_conversation_id: Optional[UUID] = None,
    now: Optional[datetime] = None,
) -> Artifact:
    """Speichert ein Artefakt: Quota prüfen → Bytes auf Disk → Row mit `expires_at`.

    Idempotent über `origin_ref`: existiert bereits ein Artefakt dieser Herkunft, wird es
    unverändert zurückgegeben (kein zweiter Disk-Write, kein Quota-Verbrauch). Wirft
    `QuotaExceeded`, wenn die Bibliothek der Nutzer:in durch das Speichern überliefe.
    """
    # Idempotenz: gleiche Herkunft → bestehendes Artefakt, ohne erneut zu schreiben.
    if origin_ref is not None:
        existing = await find_by_origin_ref(db, owner_pseudonym, origin_ref)
        if existing is not None:
            return existing

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
        origin_ref=origin_ref,
        origin_conversation_id=origin_conversation_id,
        created_at=ts,
        expires_at=ts + timedelta(days=retention_days),
    )
    db.add(artifact)
    try:
        await db.commit()
    except IntegrityError:
        # Wettlauf (Doppelklick): der Unique-Index hat den zweiten Insert verhindert.
        # Datei verwerfen, bestehendes Artefakt zurückgeben.
        await db.rollback()
        _file_path(artifact_id, mime_type).unlink(missing_ok=True)
        if origin_ref is not None:
            existing = await find_by_origin_ref(db, owner_pseudonym, origin_ref)
            if existing is not None:
                return existing
        raise
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
