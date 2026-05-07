from datetime import datetime
from typing import Optional
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.models import Group, GroupMembership, Subject, TeacherGroupExclusion
from app.db.session import get_db

router = APIRouter(prefix="/groups", tags=["groups"])


# Hilfsfunktion: Jahrgang aus Klassenname parsen
import re

def _parse_grade(class_name: str) -> Optional[int]:
    """Extrahiert die führende Jahrgangs-Zahl aus einem Klassennamen.

    '10C' -> 10, '8a' -> 8, 'EF' -> None, 'Q1' -> None
    """
    m = re.match(r'^(\d+)', class_name)
    return int(m.group(1)) if m else None


class GroupOut(BaseModel):
    id: int
    name: str
    slug: str
    type: str
    subject_id: Optional[int]
    sso_group_id: Optional[str]
    source_class_group_id: Optional[int]
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


# --- Schritt 2: Phase 5 API-Endpunkte ---


class PotentialTeachingGroupItem(BaseModel):
    class_group_id: int
    class_name: str
    class_grade: Optional[int]
    subject_id: int
    subject_name: str
    subject_slug: str
    subject_color: Optional[str]
    subject_icon: Optional[str]


class PotentialTeachingGroupsResponse(BaseModel):
    items: list[PotentialTeachingGroupItem]


@router.get("/teaching/potential", response_model=PotentialTeachingGroupsResponse)
async def list_potential_teaching_groups(
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PotentialTeachingGroupsResponse:
    if "teacher" not in current_user.roles:
        return PotentialTeachingGroupsResponse(items=[])

    pseudonym = current_user.sub

    # Eigene school_class- und subject_department-Gruppen laden
    stmt = (
        select(Group)
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        .where(
            GroupMembership.pseudonym == pseudonym,
            Group.type.in_(["school_class", "subject_department"]),
        )
    )
    result = await db.execute(stmt)
    all_groups = result.scalars().all()

    classes = [g for g in all_groups if g.type == "school_class"]
    dept_subject_ids = {
        g.subject_id for g in all_groups
        if g.type == "subject_department" and g.subject_id is not None
    }

    if not classes or not dept_subject_ids:
        return PotentialTeachingGroupsResponse(items=[])

    # Eigene teaching_groups: (subject_id, source_class_group_id) -> bereits vorhanden
    stmt = (
        select(Group.subject_id, Group.source_class_group_id)
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        .where(
            GroupMembership.pseudonym == pseudonym,
            Group.type == "teaching_group",
            Group.source_class_group_id.is_not(None),
        )
    )
    result = await db.execute(stmt)
    existing_pairs = {(row.subject_id, row.source_class_group_id) for row in result}

    # Negativliste
    stmt = select(
        TeacherGroupExclusion.class_group_id,
        TeacherGroupExclusion.subject_id,
    ).where(TeacherGroupExclusion.pseudonym == pseudonym)
    result = await db.execute(stmt)
    excluded_pairs = {(row.class_group_id, row.subject_id) for row in result}

    # Subjects laden
    stmt = select(Subject).where(Subject.id.in_(dept_subject_ids))
    result = await db.execute(stmt)
    subjects = {s.id: s for s in result.scalars().all()}

    items: list[PotentialTeachingGroupItem] = []
    for cls in classes:
        grade = _parse_grade(cls.name)
        for subj_id, subj in subjects.items():
            # Grade-Filter (nur wenn Fach min/max hat UND Jahrgang parsbar)
            if grade is not None and subj.min_grade is not None and subj.max_grade is not None:
                if not (subj.min_grade <= grade <= subj.max_grade):
                    continue
            # Duplikat- und Negativlisten-Filter
            if (subj_id, cls.id) in existing_pairs:
                continue
            if (cls.id, subj_id) in excluded_pairs:
                continue
            items.append(PotentialTeachingGroupItem(
                class_group_id=cls.id,
                class_name=cls.name,
                class_grade=grade,
                subject_id=subj.id,
                subject_name=subj.name,
                subject_slug=subj.slug,
                subject_color=subj.color,
                subject_icon=subj.icon,
            ))

    items.sort(key=lambda x: (
        subjects[x.subject_id].sort_order or 999,
        x.class_name,
    ))
    return PotentialTeachingGroupsResponse(items=items)


class CreateTeachingGroupRequest(BaseModel):
    class_group_id: int
    subject_id: int


class TeachingGroupOut(BaseModel):
    id: int
    name: str
    slug: str
    subject_id: Optional[int]
    source_class_group_id: Optional[int]
    model_config = ConfigDict(from_attributes=True)


@router.post("/teaching", response_model=TeachingGroupOut, status_code=201)
async def create_teaching_group(
    body: CreateTeachingGroupRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeachingGroupOut:
    if "teacher" not in current_user.roles:
        raise HTTPException(403, "Nur Lehrkräfte können Unterrichtsgruppen anlegen")

    pseudonym = current_user.sub

    # Klasse und Fach validieren
    cls = await db.get(Group, body.class_group_id)
    if cls is None or cls.type != "school_class":
        raise HTTPException(404, "Klasse nicht gefunden")
    subj = await db.get(Subject, body.subject_id)
    if subj is None:
        raise HTTPException(404, "Fach nicht gefunden")

    # Lehrkraft muss in der Klasse sein
    stmt = select(GroupMembership).where(
        GroupMembership.group_id == body.class_group_id,
        GroupMembership.pseudonym == pseudonym,
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(403, "Keine Mitgliedschaft in dieser Klasse")

    # Duplikat verhindern
    stmt = (
        select(Group)
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        .where(
            GroupMembership.pseudonym == pseudonym,
            Group.type == "teaching_group",
            Group.subject_id == body.subject_id,
            Group.source_class_group_id == body.class_group_id,
        )
    )
    if (await db.execute(stmt)).scalar_one_or_none() is not None:
        raise HTTPException(409, "Unterrichtsgruppe bereits vorhanden")

    # Negativlisten-Eintrag entfernen (falls vorhanden)
    await db.execute(
        delete(TeacherGroupExclusion).where(
            TeacherGroupExclusion.pseudonym == pseudonym,
            TeacherGroupExclusion.class_group_id == body.class_group_id,
            TeacherGroupExclusion.subject_id == body.subject_id,
        )
    )

    # Slug generieren
    base_slug = f"teaching-{subj.slug}-{cls.name.lower()}"
    # Einfache Slug-Generierung - uniqueSlug Funktion nachbilden
    slug = base_slug
    i = 1
    while True:
        stmt = select(Group).where(Group.slug == slug)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing is None:
            break
        slug = f"{base_slug}-{i}"
        i += 1

    group = Group(
        name=cls.name,
        slug=slug,
        type="teaching_group",
        subject_id=body.subject_id,
        source_class_group_id=body.class_group_id,
        sso_group_id=None,
    )
    db.add(group)
    await db.flush()

    membership = GroupMembership(
        group_id=group.id,
        pseudonym=pseudonym,
        role_in_group="teacher",
    )
    db.add(membership)
    await db.commit()
    await db.refresh(group)
    return group


@router.delete("/teaching/{group_id}", status_code=204)
async def delete_teaching_group(
    group_id: int,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    pseudonym = current_user.sub

    # Gruppe laden und prüfen
    group = await db.get(Group, group_id)
    if group is None or group.type != "teaching_group":
        raise HTTPException(404, "Unterrichtsgruppe nicht gefunden")
    if group.sso_group_id is not None:
        raise HTTPException(403, "SSO-Gruppen können nicht manuell gelöscht werden")

    # Eigene Mitgliedschaft prüfen
    stmt = select(GroupMembership).where(
        GroupMembership.group_id == group_id,
        GroupMembership.pseudonym == pseudonym,
        GroupMembership.role_in_group == "teacher",
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(403, "Keine Berechtigung")

    await db.delete(group)
    await db.commit()


class ExclusionOut(BaseModel):
    class_group_id: int
    class_name: str
    subject_id: int
    subject_name: str


@router.get("/exclusions", response_model=list[ExclusionOut])
async def list_exclusions(
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ExclusionOut]:
    stmt = (
        select(
            TeacherGroupExclusion,
            Group.name.label("class_name"),
            Subject.name.label("subject_name"),
        )
        .join(Group, Group.id == TeacherGroupExclusion.class_group_id)
        .join(Subject, Subject.id == TeacherGroupExclusion.subject_id)
        .where(TeacherGroupExclusion.pseudonym == current_user.sub)
        .order_by(Subject.sort_order, Group.name)
    )
    result = await db.execute(stmt)
    return [
        ExclusionOut(
            class_group_id=row.TeacherGroupExclusion.class_group_id,
            class_name=row.class_name,
            subject_id=row.TeacherGroupExclusion.subject_id,
            subject_name=row.subject_name,
        )
        for row in result
    ]


class CreateExclusionRequest(BaseModel):
    class_group_id: int
    subject_id: int


@router.post("/exclusions", status_code=201)
async def add_exclusion(
    body: CreateExclusionRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    excl = TeacherGroupExclusion(
        pseudonym=current_user.sub,
        class_group_id=body.class_group_id,
        subject_id=body.subject_id,
    )
    db.add(excl)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        # Bereits vorhanden = idempotent
        pass
    return {}


@router.delete("/exclusions/{class_group_id}/{subject_id}", status_code=204)
async def remove_exclusion(
    class_group_id: int,
    subject_id: int,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.execute(
        delete(TeacherGroupExclusion).where(
            TeacherGroupExclusion.pseudonym == current_user.sub,
            TeacherGroupExclusion.class_group_id == class_group_id,
            TeacherGroupExclusion.subject_id == subject_id,
        )
    )
    await db.commit()
