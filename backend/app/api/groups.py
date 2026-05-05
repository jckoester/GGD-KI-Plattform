from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.models import Group, GroupMembership
from app.db.session import get_db

router = APIRouter(prefix="/groups", tags=["groups"])


class GroupOut(BaseModel):
    id: int
    name: str
    slug: str
    type: str
    subject_id: Optional[int]
    sso_group_id: Optional[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class GroupListResponse(BaseModel):
    items: list[GroupOut]


@router.get("", response_model=GroupListResponse)
async def list_groups(
    _: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroupListResponse:
    """Gibt alle Gruppen zurueck."""
    result = await db.execute(select(Group).order_by(Group.type, Group.name))
    return GroupListResponse(items=list(result.scalars().all()))


class GroupMembershipOut(BaseModel):
    group_id: int
    role_in_group: Optional[str]
    model_config = ConfigDict(from_attributes=True)


class MyGroupsResponse(BaseModel):
    items: list[GroupOut]


@router.get("/me", response_model=MyGroupsResponse)
async def list_my_groups(
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MyGroupsResponse:
    """Gibt die Gruppen zurueck, in denen der aktuelle Nutzer Mitglied ist."""
    stmt = (
        select(Group)
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        .where(GroupMembership.pseudonym == current_user.sub)
        .order_by(Group.type, Group.name)
    )
    result = await db.execute(stmt)
    return MyGroupsResponse(items=list(result.scalars().all()))
