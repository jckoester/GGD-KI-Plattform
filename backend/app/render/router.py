"""Render-Endpunkt (Phase 17, §3.2).

`POST /render/{kind}` — Registry-getrieben (kind = circuit; plot ab Schritt 5).
Pseudonym-authentifiziert (nur eingeloggte Nutzer:innen), moderationsfrei (reines
Rendering). Antwort enthält immer ein `svg` (bei Fehler ein Platzhalter) + `error`.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.session import get_db
from app.render import service

router = APIRouter(prefix="/render", tags=["render"])


class RenderRequest(BaseModel):
    source: str


class RenderResponse(BaseModel):
    svg: str
    cached: bool = False
    error: str | None = None


@router.post("/{kind}", response_model=RenderResponse)
async def render_block(
    kind: str,
    request: RenderRequest,
    _: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RenderResponse:
    result = await service.render(db, kind, request.source)
    return RenderResponse(**result)
