from fastapi import APIRouter, Depends
from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload

from app.api.admin.assistants import router as assistants_router
from app.api.admin.budgets import router as budgets_router
from app.api.admin.flags import router as flags_router
from app.api.admin.groups import router as groups_router
from app.api.admin.guardrail import router as guardrail_router
from app.api.admin.models import router as models_router
from app.api.admin.image_models import router as image_models_router
from app.api.admin.stats import router as stats_router
from app.api.admin.site_texts import router as site_texts_router
from app.api.admin.export_templates import router as export_templates_router

router = APIRouter(prefix="/admin", tags=["admin"])

router.include_router(assistants_router)
router.include_router(budgets_router)
router.include_router(flags_router)
router.include_router(groups_router)
router.include_router(guardrail_router)
router.include_router(models_router)
router.include_router(image_models_router)
router.include_router(stats_router)
router.include_router(site_texts_router)
router.include_router(export_templates_router)


@router.get("/ping")
async def ping(
    _: JwtPayload = Depends(require_role("admin")),
) -> dict:
    return {"ok": True}
