from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SiteText
from app.db.session import get_db

router = APIRouter(prefix="/site-texts", tags=["site-texts"])

# Whitelist der gültigen Keys
VALID_KEYS = {"impressum", "datenschutz", "hilfe", "regeln"}


@router.get("/{key}")
async def get_site_text(
    key: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Öffentlicher Endpoint: Gibt den Site-Text für den gegebenen Key zurück.
    
    Keine Authentifizierung erforderlich - Impressum/Datenschutz müssen öffentlich zugänglich sein.
    """
    if key not in VALID_KEYS:
        raise HTTPException(status_code=404, detail="Unbekannter Text-Key")
    
    result = await db.execute(
        select(SiteText).where(SiteText.key == key)
    )
    site_text = result.scalar_one_or_none()
    
    if site_text is None:
        raise HTTPException(status_code=404, detail="Text nicht gefunden")
    
    return {
        "key": site_text.key,
        "content": site_text.content,
        "updated_at": site_text.updated_at.isoformat() if site_text.updated_at else None,
    }
