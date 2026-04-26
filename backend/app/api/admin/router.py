from fastapi import APIRouter, Depends
from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload

from app.api.admin.models import router as models_router
from app.api.admin.stats import router as stats_router

router = APIRouter(prefix="/admin", tags=["admin"])

router.include_router(models_router)
router.include_router(stats_router)


@router.get("/ping")
async def ping(
    _: JwtPayload = Depends(require_role("admin")),
) -> dict:
    return {"ok": True}
