from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.db.models import SiteConfig
from app.db.session import get_db

router = APIRouter(prefix="/site-texts", tags=["admin-site-texts"])

# Whitelist der gültigen Keys
VALID_KEYS = {"impressum", "datenschutz", "hilfe", "regeln"}


class SiteTextUpdate(BaseModel):
    content: str = Field(max_length=50_000)


class SiteTextResponse(BaseModel):
    key: str
    updated_at: datetime
    updated_by: str | None = None


@router.put("/{key}", response_model=SiteTextResponse)
async def update_site_text(
    key: str,
    body: SiteTextUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: JwtPayload = Depends(require_role("admin")),
) -> SiteTextResponse:
    """Admin-Endpoint: Überschreibt den Content für den gegebenen Key.
    
    Erfordert Admin-Rolle. nur Whitelist-Keys sind schreibbar.
    """
    if key not in VALID_KEYS:
        raise HTTPException(status_code=404, detail="Unbekannter Text-Key")
    
    # Check if key exists
    result = await db.execute(
        select(SiteConfig).where(SiteConfig.key == key)
    )
    site_config = result.scalar_one_or_none()
    
    if site_config is None:
        raise HTTPException(status_code=404, detail="Text nicht gefunden")
    
    # Update the value, updated_at and updated_by
    await db.execute(
        sql_update(SiteConfig)
        .where(SiteConfig.key == key)
        .values(
            value=body.content,
            updated_at=datetime.now(timezone.utc),
            updated_by=current_user.sub,
        )
    )
    await db.commit()
    
    # Fetch updated record to get the precise updated_at timestamp
    result = await db.execute(
        select(SiteConfig).where(SiteConfig.key == key)
    )
    updated = result.scalar_one()
    
    return SiteTextResponse(
        key=key,
        updated_at=updated.updated_at,
        updated_by=updated.updated_by,
    )
