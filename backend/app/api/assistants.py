from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.models import Assistant
from app.db.session import get_db


def _is_visible_for_user(assistant: Assistant, roles: list[str]) -> bool:
    if assistant.status != "active":
        return False
    now = datetime.now(timezone.utc)
    if assistant.available_from and assistant.available_from > now:
        return False
    if assistant.available_until and assistant.available_until < now:
        return False
    match assistant.audience:
        case "all":
            return True
        case "student":
            return "student" in roles
        case "teacher":
            return "teacher" in roles or "admin" in roles
    return False


class AssistantSummary(BaseModel):
    id: int
    name: str
    description: Optional[str]
    subject_id: Optional[int]
    audience: str
    scope: str
    icon: Optional[str]
    tags: Optional[list[str]]
    min_grade: Optional[int]
    max_grade: Optional[int]
    model_config = ConfigDict(from_attributes=True)


class AssistantListResponse(BaseModel):
    items: list[AssistantSummary]


router = APIRouter(prefix="/assistants", tags=["assistants"])


@router.get("", response_model=AssistantListResponse)
async def list_assistants(
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssistantListResponse:
    roles = current_user.roles
    is_student = "student" in roles
    is_teacher = "teacher" in roles or "admin" in roles
    now = datetime.now(timezone.utc)

    stmt = (
        select(Assistant)
        .where(
            and_(
                Assistant.status == "active",
                or_(Assistant.available_from.is_(None), Assistant.available_from <= now),
                or_(Assistant.available_until.is_(None), Assistant.available_until >= now),
                or_(
                    Assistant.audience == "all",
                    and_(Assistant.audience == "student", is_student),
                    and_(Assistant.audience == "teacher", is_teacher),
                ),
            )
        )
        .order_by(Assistant.sort_order.asc(), Assistant.name.asc())
    )

    result = await db.execute(stmt)
    assistants = result.scalars().all()

    return AssistantListResponse(
        items=[AssistantSummary.model_validate(a) for a in assistants]
    )
