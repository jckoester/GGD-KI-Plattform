from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.db.models import Group, GroupMembership, Assistant
from app.db.session import get_db

router = APIRouter(prefix="/groups", tags=["admin-groups"])

VALID_GROUP_TYPES = {
    "school_class", "subject_department", "teaching_group", "activity_group", "teachers"
}
VALID_ROLES_IN_GROUP = {"teacher", "student"}


# ── Pydantic Schemas ────────────────────────────────────────────────────────

class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=r'^[a-z0-9][a-z0-9\-\.]*$')
    type: str
    subject_id: Optional[int] = None
    sso_group_id: Optional[str] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    subject_id: Optional[int] = None
    sso_group_id: Optional[str] = None


class MemberAdd(BaseModel):
    pseudonym: str = Field(min_length=1)
    role_in_group: Optional[str] = None


class GroupOut(BaseModel):
    id: int
    name: str
    slug: str
    type: str
    subject_id: Optional[int]
    sso_group_id: Optional[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class GroupDetailOut(BaseModel):
    id: int
    name: str
    slug: str
    type: str
    subject_id: Optional[int]
    sso_group_id: Optional[str]
    created_at: datetime
    member_count: int
    model_config = ConfigDict(from_attributes=True)


class GroupListResponse(BaseModel):
    items: list[GroupOut]
    total: int


class MemberOut(BaseModel):
    pseudonym: str
    role_in_group: Optional[str]
    model_config = ConfigDict(from_attributes=True)


class MemberListResponse(BaseModel):
    items: list[MemberOut]
    total: int


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.get("", response_model=GroupListResponse)
async def list_groups(
    type_filter: Optional[str] = None,
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> GroupListResponse:
    """Liste aller Gruppen mit optionalem Typ-Filter."""
    stmt = select(Group).order_by(Group.type, Group.name)
    
    if type_filter is not None:
        if type_filter not in VALID_GROUP_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Ungueltiger Typ. Erlaubt: {', '.join(sorted(VALID_GROUP_TYPES))}"
            )
        stmt = stmt.where(Group.type == type_filter)
    
    result = await db.execute(stmt)
    groups = result.scalars().all()
    
    return GroupListResponse(items=list(groups), total=len(groups))


@router.post("", response_model=GroupDetailOut, status_code=status.HTTP_201_CREATED)
async def create_group(
    request: GroupCreate,
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> GroupDetailOut:
    """Neue Gruppe anlegen."""
    if request.type not in VALID_GROUP_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Ungueltiger Typ. Erlaubt: {', '.join(sorted(VALID_GROUP_TYPES))}"
        )

    result = await db.execute(select(Group).where(Group.slug == request.slug))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Slug '{request.slug}' existiert bereits")

    group = Group(
        name=request.name,
        slug=request.slug,
        type=request.type,
        subject_id=request.subject_id,
        sso_group_id=request.sso_group_id,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return await _to_detail_out(db, group)


@router.get("/{group_id}", response_model=GroupDetailOut)
async def get_group(
    group_id: int,
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> GroupDetailOut:
    """Einzelne Gruppe abrufen."""
    group = await _get_or_404(db, group_id)
    return await _to_detail_out(db, group)


@router.patch("/{group_id}", response_model=GroupDetailOut)
async def update_group(
    group_id: int,
    request: GroupUpdate,
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> GroupDetailOut:
    """Gruppe aktualisieren."""
    group = await _get_or_404(db, group_id)

    if request.name is not None:
        group.name = request.name
    if request.subject_id is not None:
        group.subject_id = request.subject_id
    if request.sso_group_id is not None:
        group.sso_group_id = request.sso_group_id

    await db.commit()
    await db.refresh(group)
    return await _to_detail_out(db, group)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int,
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Gruppe loeschen. Schlaegt fehl wenn Assistenten darauf referenzieren."""
    # Pruefen ob Assistenten auf diese Gruppe referenzieren
    result = await db.execute(
        select(func.count())
        .select_from(Assistant)
        .where(Assistant.scope_group_id == group_id)
    )
    count = result.scalar()
    
    if count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Gruppe kann nicht geloescht werden: {count} Assistent(en) referenzieren sie"
        )
    
    # Gruppe loeschen
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    
    if group is None:
        raise HTTPException(status_code=404, detail="Gruppe nicht gefunden")
    
    await db.delete(group)
    await db.commit()


@router.get("/{group_id}/members", response_model=MemberListResponse)
async def list_members(
    group_id: int,
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> MemberListResponse:
    """Mitglieder einer Gruppe auflisten."""
    result = await db.execute(
        select(GroupMembership)
        .where(GroupMembership.group_id == group_id)
        .order_by(GroupMembership.pseudonym)
    )
    members = result.scalars().all()
    
    return MemberListResponse(items=list(members), total=len(members))


@router.post("/{group_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
async def add_member(
    group_id: int,
    request: MemberAdd,
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> MemberOut:
    """Mitglied zu Gruppe hinzufuegen (Upsert)."""
    # Validierung
    if request.role_in_group is not None and request.role_in_group not in VALID_ROLES_IN_GROUP:
        raise HTTPException(
            status_code=422,
            detail=f"Ungueltige Rolle. Erlaubt: {', '.join(filter(None, VALID_ROLES_IN_GROUP))}"
        )
    
    # Pruefen ob Gruppe existiert
    result = await db.execute(select(Group).where(Group.id == group_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Gruppe nicht gefunden")
    
    # Upsert: wenn (group_id, pseudonym) existiert, role_in_group aktualisieren
    result = await db.execute(
        select(GroupMembership)
        .where(
            and_(
                GroupMembership.group_id == group_id,
                GroupMembership.pseudonym == request.pseudonym
            )
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        existing.role_in_group = request.role_in_group
    else:
        membership = GroupMembership(
            group_id=group_id,
            pseudonym=request.pseudonym,
            role_in_group=request.role_in_group,
        )
        db.add(membership)
    
    await db.commit()
    
    return MemberOut(
        pseudonym=request.pseudonym,
        role_in_group=request.role_in_group
    )


@router.delete("/{group_id}/members/{pseudonym}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    group_id: int,
    pseudonym: str,
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Mitglied aus Gruppe entfernen."""
    result = await db.execute(
        select(GroupMembership)
        .where(
            and_(
                GroupMembership.group_id == group_id,
                GroupMembership.pseudonym == pseudonym
            )
        )
    )
    membership = result.scalar_one_or_none()
    
    if membership is None:
        raise HTTPException(status_code=404, detail="Mitgliedschaft nicht gefunden")
    
    await db.delete(membership)
    await db.commit()


# ── Helper Functions ────────────────────────────────────────────────────────

async def _count_members(db: AsyncSession, group_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(GroupMembership).where(GroupMembership.group_id == group_id)
    )
    return result.scalar() or 0


async def _get_or_404(db: AsyncSession, group_id: int) -> Group:
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Gruppe nicht gefunden")
    return group


async def _to_detail_out(db: AsyncSession, group: Group) -> GroupDetailOut:
    member_count = await _count_members(db, group.id)
    return GroupDetailOut(
        id=group.id,
        name=group.name,
        slug=group.slug,
        type=group.type,
        subject_id=group.subject_id,
        sso_group_id=group.sso_group_id,
        created_at=group.created_at,
        member_count=member_count,
    )
