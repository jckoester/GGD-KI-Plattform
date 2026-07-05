"""Persistenter SVG-Cache (Tabelle `rendered_svg`) für Server-Rendering (Phase 17).

Content-adressiert per Hash der Render-Quelle. Nur Erfolge werden gecacht (der Service
cacht keine Fehler-Platzhalter). Altersbasiert aufgeräumt (`cleanup_rendered_svg`).
"""
import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RenderedSvg


def svg_hash(kind: str, source: str) -> str:
    """Stabiler Hash über (kind, source) — trennt circuit/plot mit gleicher Quelle."""
    return hashlib.sha256(f"{kind}\x00{source}".encode("utf-8")).hexdigest()


async def get_cached_svg(db: AsyncSession, hash_: str) -> str | None:
    result = await db.execute(select(RenderedSvg.svg).where(RenderedSvg.hash == hash_))
    return result.scalar_one_or_none()


async def set_cached_svg(db: AsyncSession, hash_: str, svg: str) -> None:
    # Idempotent: gleicher Hash = gleicher Input → bereits vorhandenen Eintrag behalten.
    stmt = (
        pg_insert(RenderedSvg)
        .values(hash=hash_, svg=svg)
        .on_conflict_do_nothing(index_elements=["hash"])
    )
    await db.execute(stmt)
    await db.commit()


async def cleanup_rendered_svg(db: AsyncSession, max_age_days: int) -> int:
    """Löscht Cache-Einträge älter als max_age_days. Gibt die Anzahl zurück."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    result = await db.execute(delete(RenderedSvg).where(RenderedSvg.created_at < cutoff))
    await db.commit()
    return result.rowcount or 0
