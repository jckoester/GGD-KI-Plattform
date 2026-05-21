from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.db.models import SiteConfig
from app.db.session import get_db
from app.litellm.client import LiteLLMClient

router = APIRouter(prefix="/guardrail", tags=["admin-guardrail"])

_litellm = LiteLLMClient()
_GUARDRAIL_KEY = "guardrail_prompt"


# ---------- Pydantic-Schemas ----------

class GuardrailPromptResponse(BaseModel):
    prompt: str | None
    updated_at: datetime | None
    updated_by: str | None


class GuardrailPromptUpdate(BaseModel):
    prompt: str | None = Field(default=None, max_length=10_000)


class LiteLLMGuardrailItem(BaseModel):
    name: str
    mode: str | None = None


class LiteLLMGuardrailsResponse(BaseModel):
    guardrails: list[LiteLLMGuardrailItem]
    available: bool  # False wenn LiteLLM nicht erreichbar war


# ---------- Endpunkte ----------

@router.get("/prompt", response_model=GuardrailPromptResponse)
async def get_guardrail_prompt(
    db: AsyncSession = Depends(get_db),
    _: JwtPayload = Depends(require_role("admin")),
) -> GuardrailPromptResponse:
    result = await db.execute(
        select(SiteConfig).where(SiteConfig.key == _GUARDRAIL_KEY)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return GuardrailPromptResponse(prompt=None, updated_at=None, updated_by=None)
    return GuardrailPromptResponse(
        prompt=row.value,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
    )


@router.put("/prompt", response_model=GuardrailPromptResponse)
async def update_guardrail_prompt(
    body: GuardrailPromptUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: JwtPayload = Depends(require_role("admin")),
) -> GuardrailPromptResponse:
    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(SiteConfig)
        .values(
            key=_GUARDRAIL_KEY,
            value=body.prompt,
            updated_at=now,
            updated_by=current_user.sub,
        )
        .on_conflict_do_update(
            index_elements=["key"],
            set_={
                "value": body.prompt,
                "updated_at": now,
                "updated_by": current_user.sub,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()

    # Chat-Router-Cache invalidieren
    import app.chat.router as chat_router
    chat_router._guardrail_prompt_cache = None

    result = await db.execute(
        select(SiteConfig).where(SiteConfig.key == _GUARDRAIL_KEY)
    )
    row = result.scalar_one()
    return GuardrailPromptResponse(
        prompt=row.value,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
    )


@router.get("/litellm", response_model=LiteLLMGuardrailsResponse)
async def get_litellm_guardrails(
    _: JwtPayload = Depends(require_role("admin")),
) -> LiteLLMGuardrailsResponse:
    raw = await _litellm.list_guardrails()
    items = [LiteLLMGuardrailItem(name=g["name"], mode=g.get("mode")) for g in raw]
    return LiteLLMGuardrailsResponse(guardrails=items, available=True)
