"""Schulweite Export-Vorlagen der Material-Werkstatt (Phase 19, Schritt 6).

Zwei Vorlagen-Mechanismen, je Ausgabeformat:
- **PDF** über eigenes CSS: schulweit ergänzbar, liegt als Text in `site_config` (`export_css`)
  und wird beim PDF-Export als `extra_css` in die Standard-Vorlage injiziert.
- **DOCX/ODT** über Pandoc `--reference-doc`: eine hochgeladene Referenzdatei je Format, liegt
  auf Disk (`settings.export_template_dir`).

Fehlt eine Vorlage, greift die eingebaute Default-Optik (kein Hard-Fail). Persönliche Vorlagen
(pro Lehrkraft) sind bewusst v1-out-of-scope (Todo).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import SiteConfig

EXPORT_CSS_KEY = "export_css"
REFERENCE_FORMATS = ("docx", "odt")

# Repo-Root: backend/app/export/templates.py → parents[3] (cwd-unabhängig, analog store).
_REPO_ROOT = Path(__file__).resolve().parents[3]


# ── PDF-CSS (site_config) ─────────────────────────────────────────────────────

async def get_export_css(db: AsyncSession) -> str:
    result = await db.execute(select(SiteConfig.value).where(SiteConfig.key == EXPORT_CSS_KEY))
    return result.scalar_one_or_none() or ""


async def set_export_css(db: AsyncSession, css: Optional[str], updated_by: Optional[str]) -> None:
    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(SiteConfig)
        .values(key=EXPORT_CSS_KEY, value=css, updated_at=now, updated_by=updated_by)
        .on_conflict_do_update(
            index_elements=["key"],
            set_={"value": css, "updated_at": now, "updated_by": updated_by},
        )
    )
    await db.execute(stmt)
    await db.commit()


# ── DOCX/ODT-Referenzdokumente (Disk) ─────────────────────────────────────────

def template_dir() -> Path:
    base = Path(settings.export_template_dir)
    d = base if base.is_absolute() else _REPO_ROOT / base
    d.mkdir(parents=True, exist_ok=True)
    return d


def reference_path(fmt: str) -> Optional[Path]:
    """Pfad des reference-docs (falls vorhanden) — für Pandoc `--reference-doc`."""
    if fmt not in REFERENCE_FORMATS:
        return None
    path = template_dir() / f"reference.{fmt}"
    return path if path.exists() else None


def has_reference(fmt: str) -> bool:
    return reference_path(fmt) is not None


def save_reference(fmt: str, data: bytes) -> None:
    if fmt not in REFERENCE_FORMATS:
        raise ValueError(f"kein referenzierbares Format: {fmt!r}")
    (template_dir() / f"reference.{fmt}").write_bytes(data)


def delete_reference(fmt: str) -> bool:
    if fmt not in REFERENCE_FORMATS:
        return False
    path = template_dir() / f"reference.{fmt}"
    if path.exists():
        path.unlink()
        return True
    return False
