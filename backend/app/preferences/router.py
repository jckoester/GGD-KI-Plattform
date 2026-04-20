from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.preferences.service import get_preferences, patch_preferences

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("")
async def read_preferences(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_preferences(db, current_user.sub)


@router.patch("")
async def update_preferences(
    updates: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await patch_preferences(db, current_user.sub, updates)
