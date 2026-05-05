from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Subject
from app.db.session import get_db

router = APIRouter(prefix="/subjects", tags=["subjects"])


class SubjectOut(BaseModel):
    id: int
    slug: str
    name: str
    icon: Optional[str]
    color: Optional[str]
    min_grade: Optional[int]
    max_grade: Optional[int]
    sort_order: int
    model_config = ConfigDict(from_attributes=True)


class SubjectListResponse(BaseModel):
    items: list[SubjectOut]


@router.get("", response_model=SubjectListResponse)
async def list_subjects(
    db: AsyncSession = Depends(get_db)
) -> SubjectListResponse:
    result = await db.execute(select(Subject).order_by(Subject.sort_order))
    subjects = result.scalars().all()
    return SubjectListResponse(items=list(subjects))
