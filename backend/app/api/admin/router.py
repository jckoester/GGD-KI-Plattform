from fastapi import APIRouter, Depends
from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/ping")
async def ping(
    _: JwtPayload = Depends(require_role("admin")),
) -> dict:
    return {"ok": True}
