"""Admin: schulweite Export-Vorlagen der Material-Werkstatt (Phase 19, Schritt 6).

- CSS (PDF) als Text in `site_config` (`export_css`).
- reference-docs (DOCX/ODT) als hochgeladene Dateien auf Disk.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.config import settings
from app.db.models import SiteConfig
from app.db.session import get_db
from app.export import templates as export_templates

router = APIRouter(prefix="/export-templates", tags=["admin-export-templates"])


class ExportTemplatesStatus(BaseModel):
    css: str
    css_updated_at: datetime | None = None
    css_updated_by: str | None = None
    has_docx_reference: bool
    has_odt_reference: bool


class CssUpdate(BaseModel):
    css: str = Field(default="", max_length=100_000)


@router.get("", response_model=ExportTemplatesStatus)
async def get_status(
    db: AsyncSession = Depends(get_db),
    _: JwtPayload = Depends(require_role("admin")),
) -> ExportTemplatesStatus:
    row = (await db.execute(
        select(SiteConfig).where(SiteConfig.key == export_templates.EXPORT_CSS_KEY)
    )).scalar_one_or_none()
    return ExportTemplatesStatus(
        css=(row.value if row else "") or "",
        css_updated_at=row.updated_at if row else None,
        css_updated_by=row.updated_by if row else None,
        has_docx_reference=export_templates.has_reference("docx"),
        has_odt_reference=export_templates.has_reference("odt"),
    )


@router.put("/css", response_model=ExportTemplatesStatus)
async def update_css(
    body: CssUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: JwtPayload = Depends(require_role("admin")),
) -> ExportTemplatesStatus:
    await export_templates.set_export_css(db, body.css, current_user.sub)
    return await get_status(db=db, _=current_user)


@router.post("/reference/{fmt}", response_model=ExportTemplatesStatus)
async def upload_reference(
    fmt: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: JwtPayload = Depends(require_role("admin")),
) -> ExportTemplatesStatus:
    if fmt not in export_templates.REFERENCE_FORMATS:
        raise HTTPException(status_code=422, detail="Nur DOCX oder ODT als Referenzdokument.")
    data = await file.read()
    if len(data) > settings.export_reference_max_bytes:
        raise HTTPException(status_code=413, detail="Referenzdokument ist zu groß.")
    # DOCX/ODT sind ZIP-Container → müssen mit der ZIP-Signatur beginnen.
    if data[:2] != b"PK":
        raise HTTPException(status_code=422, detail="Keine gültige DOCX/ODT-Datei.")
    export_templates.save_reference(fmt, data)
    return await get_status(db=db, _=current_user)


@router.delete("/reference/{fmt}", response_model=ExportTemplatesStatus)
async def delete_reference(
    fmt: str,
    db: AsyncSession = Depends(get_db),
    current_user: JwtPayload = Depends(require_role("admin")),
) -> ExportTemplatesStatus:
    if fmt not in export_templates.REFERENCE_FORMATS:
        raise HTTPException(status_code=422, detail="Unbekanntes Format.")
    export_templates.delete_reference(fmt)
    return await get_status(db=db, _=current_user)
