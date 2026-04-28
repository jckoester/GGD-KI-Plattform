from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.db.models import SiteText
from app.db.session import get_db

router = APIRouter(prefix="/site-texts", tags=["admin-site-texts"])

# Whitelist der gültigen Keys
VALID_KEYS = {"impressum", "datenschutz", "hilfe", "regeln"}


class SiteTextUpdate(BaseModel):
    content: str = Field(max_length=50_000)


class SiteTextResponse(BaseModel):
    key: str
    updated_at: datetime


@router.put("/{key}", response_model=SiteTextResponse)
async def update_site_text(
    key: str,
    body: SiteTextUpdate,
    db: AsyncSession = Depends(get_db),
    _: JwtPayload = Depends(require_role("admin")),
) -> SiteTextResponse:
    """Admin-Endpoint: Überschreibt den Content für den gegebenen Key.
    
    Erfordert Admin-Rolle. nur Whitelist-Keys sind schreibbar.
    """
    if key not in VALID_KEYS:
        raise HTTPException(status_code=404, detail="Unbekannter Text-Key")
    
    # Check if key exists
    result = await db.execute(
        select(SiteText).where(SiteText.key == key)
    )
    site_text = result.scalar_one_or_none()
    
    if site_text is None:
        raise HTTPException(status_code=404, detail="Text nicht gefunden")
    
    # Update the content and updated_at
    await db.execute(
        sql_update(SiteText)
        .where(SiteText.key == key)
        .values(
            content=body.content,
            updated_at=datetime.now(timezone.utc)
        )
    )
    await db.commit()
    
    # Fetch updated record to get the precise updated_at timestamp
    result = await db.execute(
        select(SiteText).where(SiteText.key == key)
    )
    updated_text = result.scalar_one()
    
    return SiteTextResponse(
        key=key,
        updated_at=updated_text.updated_at
    )
