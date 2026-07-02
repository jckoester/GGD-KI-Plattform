"""Speicherung, Auslieferung & Lifecycle generierter Bilder (Phase 16, Schritt 4).

Die Bild-Bytes liegen auf Disk (``settings.image_storage_dir``), die Referenz +
Metadaten in ``generated_images`` (FK ON DELETE CASCADE → ein Bild stirbt mit seiner
Konversation). Dateien werden in den Lösch-Pfaden (Cleanup-Crons, Lösch-Endpoint)
mitgelöscht; ``cleanup_generated_images`` ist der Backstop-Cron für verwaiste (Row
weg, Datei blieb) und über-alte Dateien.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import GeneratedImage

logger = logging.getLogger(__name__)

# Repo-Root: backend/app/chat/image_store.py → parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]

_MIME_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}

# Verwaiste Dateien erst nach dieser Frist löschen — schützt gerade erst geschriebene
# Dateien, deren DB-Commit noch aussteht (Race mit laufender Generierung).
_ORPHAN_GRACE = timedelta(hours=1)


def storage_dir() -> Path:
    """Ablageverzeichnis (repo-root-relativ, falls nicht absolut) — cwd-unabhängig."""
    base = Path(settings.image_storage_dir)
    return base if base.is_absolute() else _REPO_ROOT / base


def _file_path(image_id: UUID, mime_type: str = "image/png") -> Path:
    return storage_dir() / f"{image_id}{_MIME_EXT.get(mime_type, '.png')}"


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


async def save_generated_image(
    db: AsyncSession,
    *,
    pseudonym: str,
    conversation_id: UUID,
    image_bytes: bytes,
    model: str,
    size: str,
    mime_type: str = "image/png",
) -> UUID:
    """Schreibt die Bytes auf Disk + legt die DB-Referenz an (committed). Gibt die ID zurück."""
    image_id = uuid4()
    directory = storage_dir()
    directory.mkdir(parents=True, exist_ok=True)
    _file_path(image_id, mime_type).write_bytes(image_bytes)

    db.add(GeneratedImage(
        id=image_id,
        pseudonym=pseudonym,
        conversation_id=conversation_id,
        model=model,
        size=size,
        mime_type=mime_type,
        byte_size=len(image_bytes),
    ))
    await db.commit()
    logger.info("Bild persistiert id=%s conv=%s bytes=%d", image_id, conversation_id, len(image_bytes))
    return image_id


async def get_image_record(db: AsyncSession, image_id: UUID) -> GeneratedImage | None:
    return await db.get(GeneratedImage, image_id)


async def list_message_images(db: AsyncSession, conversation_id: UUID) -> dict[UUID, list[dict]]:
    """Bilder einer Konversation nach `message_id` gruppiert (für die History-Rehydrierung).

    Nur an eine Nachricht verknüpfte Bilder (message_id gesetzt); je Eintrag
    `{image_id, size}`, chronologisch."""
    rows = (await db.execute(
        select(GeneratedImage.id, GeneratedImage.size, GeneratedImage.message_id)
        .where(
            GeneratedImage.conversation_id == conversation_id,
            GeneratedImage.message_id.isnot(None),
        )
        .order_by(GeneratedImage.created_at.asc())
    )).all()
    out: dict[UUID, list[dict]] = {}
    for image_id, size, message_id in rows:
        out.setdefault(message_id, []).append({"image_id": str(image_id), "size": size})
    return out


async def link_images_to_message(db: AsyncSession, image_ids: list[UUID], message_id: UUID) -> None:
    """Hängt die (mid-Stream erzeugten) Bilder an die jetzt persistierte Assistant-Nachricht.

    Der Aufrufer commit-tet (Teil derselben Persistenz-Transaktion in `_persist`)."""
    if not image_ids:
        return
    await db.execute(
        update(GeneratedImage)
        .where(GeneratedImage.id.in_(image_ids))
        .values(message_id=message_id)
    )


def read_image_bytes(record: GeneratedImage) -> bytes | None:
    """Liest die Bytes zur Referenz; None, wenn die Datei fehlt (z. B. bereits geräumt)."""
    path = _file_path(record.id, record.mime_type)
    if not path.exists():
        return None
    return path.read_bytes()


# ── Datei-Löschung in den Lösch-Pfaden (collect VOR dem Row-Delete, unlink DANACH) ──

async def collect_conversation_image_paths(
    db: AsyncSession, conversation_ids: list[UUID]
) -> list[Path]:
    """Dateipfade der Bilder dieser Konversationen (vor deren Löschung aufzusammeln)."""
    if not conversation_ids:
        return []
    rows = (await db.execute(
        select(GeneratedImage.id, GeneratedImage.mime_type)
        .where(GeneratedImage.conversation_id.in_(conversation_ids))
    )).all()
    return [_file_path(image_id, mime_type) for image_id, mime_type in rows]


async def collect_pseudonym_image_paths(db: AsyncSession, pseudonym: str) -> list[Path]:
    rows = (await db.execute(
        select(GeneratedImage.id, GeneratedImage.mime_type)
        .where(GeneratedImage.pseudonym == pseudonym)
    )).all()
    return [_file_path(image_id, mime_type) for image_id, mime_type in rows]


def unlink_paths(paths: list[Path]) -> int:
    """Löscht die übergebenen Dateien best-effort; gibt die Anzahl gelöschter zurück."""
    removed = 0
    for path in paths:
        try:
            if path.exists():
                path.unlink()
                removed += 1
        except OSError as exc:
            logger.warning("Bilddatei konnte nicht gelöscht werden %s: %s", path, exc)
    return removed


# ── Backstop-Cron: verwaiste + über-alte Dateien ───────────────────────────────

@dataclass
class ImageCleanupStats:
    scanned: int = 0
    orphans_removed: int = 0
    aged_removed: int = 0
    kept: int = 0


async def cleanup_generated_images(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    max_age_days: int | None = None,
    dry_run: bool = False,
) -> ImageCleanupStats:
    """Räumt (a) verwaiste Dateien (keine DB-Zeile mehr) und (b) Dateien über der harten
    Maximal-Aufbewahrung (inkl. deren DB-Zeile). Idempotent, batch-frei (Datei-für-Datei)."""
    stats = ImageCleanupStats()
    directory = storage_dir()
    if not directory.exists():
        return stats

    current = _now(now)
    max_age = max_age_days if max_age_days is not None else settings.image_max_retention_days
    age_cutoff = current - timedelta(days=max_age)
    orphan_cutoff = current - _ORPHAN_GRACE

    known_ids = {
        str(row[0]) for row in (await db.execute(select(GeneratedImage.id))).all()
    }

    aged_ids: list[UUID] = []
    for path in directory.iterdir():
        if not path.is_file():
            continue
        stats.scanned += 1
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

        if path.stem not in known_ids:
            # Verwaist — aber Race-Schutz: gerade erst geschriebene Dateien verschonen.
            if mtime < orphan_cutoff:
                if not dry_run:
                    unlink_paths([path])
                stats.orphans_removed += 1
            else:
                stats.kept += 1
            continue

        if mtime < age_cutoff:
            if not dry_run:
                unlink_paths([path])
            try:
                aged_ids.append(UUID(path.stem))
            except ValueError:
                pass
            stats.aged_removed += 1
        else:
            stats.kept += 1

    if aged_ids and not dry_run:
        await db.execute(delete(GeneratedImage).where(GeneratedImage.id.in_(aged_ids)))
        await db.commit()

    logger.info(
        "cleanup_generated_images scanned=%d orphans=%d aged=%d kept=%d dry_run=%s",
        stats.scanned, stats.orphans_removed, stats.aged_removed, stats.kept, dry_run,
    )
    return stats
