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
    # In der Vorschau (0.29) zählt das **echte** Budget: Bezahlt wird aus dem Konto der
    # Lehrkraft, also gelten ihr Wochenbetrag und ihre Stufe, nicht die simulierten.
    merkmal = current_user.preview
    return await get_budget_info(
        db, current_user.sub,
        roles=merkmal.echte_rollen if merkmal else current_user.roles,
        grade=merkmal.echter_jahrgang if merkmal else current_user.grade,
    )
