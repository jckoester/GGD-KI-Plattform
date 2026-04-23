from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.budget.exchange import get_current_rate
from app.budget.service import get_budget_info
from app.db.session import get_db

router = APIRouter(prefix="/budget", tags=["budget"])


@router.get("/me")
async def read_my_budget(
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_budget_info(db, current_user.sub)
