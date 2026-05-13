from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_any_role
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


# ── Teacher Assistant Schemas ───────────────────────────────────────────────

class TeacherAssistantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    subject_id: Optional[int] = None
    system_prompt: str = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    audience: str = Field(default="student")
    scope: str = Field(default="private")
    scope_group_id: Optional[int] = None
    min_grade: Optional[int] = Field(default=None, ge=1, le=13)
    max_grade: Optional[int] = Field(default=None, ge=1, le=13)
    tags: Optional[list[str]] = None
    icon: Optional[str] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None


class TeacherAssistantUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    subject_id: Optional[int] = None
    system_prompt: Optional[str] = Field(default=None, min_length=1)
    model: Optional[str] = Field(default=None, min_length=1)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    audience: Optional[str] = None
    scope: Optional[str] = None
    scope_group_id: Optional[int] = None
    min_grade: Optional[int] = Field(default=None, ge=1, le=13)
    max_grade: Optional[int] = Field(default=None, ge=1, le=13)
    tags: Optional[list[str]] = None
    icon: Optional[str] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None


class TeacherAssistantResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    subject_id: Optional[int]
    system_prompt: str
    model: str
    temperature: Optional[float]
    max_tokens: Optional[int]
    status: str
    audience: str
    scope: str
    scope_group_id: Optional[int]
    scope_pending: Optional[str]
    min_grade: Optional[int]
    max_grade: Optional[int]
    tags: Optional[list[str]]
    icon: Optional[str]
    available_from: Optional[datetime]
    available_until: Optional[datetime]
    created_by: Optional[str]
    creator_role: str
    reject_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TeacherAssistantListResponse(BaseModel):
    items: list[TeacherAssistantResponse]
    total: int


# ── Validation ──────────────────────────────────────────────────────────────

_VALID_AUDIENCES = {"student", "teacher", "all"}
_VALID_SCOPES = {
    "private", "subject_department", "teachers", "activity_group",
    "teaching_group", "grade", "all_students", "all",
}
_GROUP_SCOPES = {"subject_department", "activity_group", "teaching_group"}


def _validate_teacher_fields(
    name: Optional[str] = None,
    system_prompt: Optional[str] = None,
    audience: Optional[str] = None,
    scope: Optional[str] = None,
    scope_group_id: Optional[int] = None,
    min_grade: Optional[int] = None,
    max_grade: Optional[int] = None,
    available_from: Optional[datetime] = None,
    available_until: Optional[datetime] = None,
) -> None:
    """Validiert Business-Regeln für Lehrkraft-Assistenten. Wirft HTTPException(422)."""
    if name is not None and not name.strip():
        raise HTTPException(status_code=422, detail="name darf nicht leer sein")
    if system_prompt is not None and not system_prompt.strip():
        raise HTTPException(status_code=422, detail="system_prompt darf nicht leer sein")
    if audience is not None and audience not in _VALID_AUDIENCES:
        raise HTTPException(status_code=422, detail="Ungültiger audience-Wert")
    if scope is not None and scope not in _VALID_SCOPES:
        raise HTTPException(status_code=422, detail="Ungültiger scope-Wert")
    if scope is not None and scope in _GROUP_SCOPES and scope_group_id is None:
        raise HTTPException(
            status_code=422, detail="Gruppen-Scope erfordert eine scope_group_id"
        )
    if scope is not None and scope not in _GROUP_SCOPES and scope_group_id is not None:
        raise HTTPException(
            status_code=422, detail="scope_group_id darf nur bei Gruppen-Scopes gesetzt sein"
        )
    if audience == "teacher" and scope in {"all_students", "all"}:
        raise HTTPException(
            status_code=422,
            detail="teacher-Assistenten dürfen nicht für Schüler:innen sichtbar sein",
        )
    if available_from is not None and available_until is not None:
        if available_from >= available_until:
            raise HTTPException(
                status_code=422, detail="available_from muss vor available_until liegen"
            )
    if min_grade is not None and max_grade is not None:
        if min_grade > max_grade:
            raise HTTPException(
                status_code=422, detail="min_grade darf nicht größer als max_grade sein"
            )


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


# ── Teacher Endpoints ────────────────────────────────────────────────────────

@router.get("/mine", response_model=TeacherAssistantListResponse)
async def list_my_assistants(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> TeacherAssistantListResponse:
    """Gibt alle eigenen Assistenten zurück (alle Status)."""
    stmt = select(Assistant).where(Assistant.created_by == current_user.sub)
    if status is not None:
        stmt = stmt.where(Assistant.status == status)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar()

    stmt = stmt.order_by(Assistant.updated_at.desc()).limit(limit).offset(offset)
    assistants = (await db.execute(stmt)).scalars().all()

    return TeacherAssistantListResponse(
        items=[TeacherAssistantResponse.model_validate(a) for a in assistants],
        total=total,
    )


@router.post("", response_model=TeacherAssistantResponse, status_code=201)
async def create_my_assistant(
    request: TeacherAssistantCreate,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> TeacherAssistantResponse:
    """Erstellt einen neuen Assistenten im Entwurfsstatus."""
    _validate_teacher_fields(
        name=request.name,
        system_prompt=request.system_prompt,
        audience=request.audience,
        scope=request.scope,
        scope_group_id=request.scope_group_id,
        min_grade=request.min_grade,
        max_grade=request.max_grade,
        available_from=request.available_from,
        available_until=request.available_until,
    )
    creator_role = "admin" if "admin" in current_user.roles else "teacher"
    assistant = Assistant(
        name=request.name,
        description=request.description,
        subject_id=request.subject_id,
        system_prompt=request.system_prompt,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        status="draft",
        audience=request.audience,
        scope=request.scope,
        scope_group_id=request.scope_group_id,
        min_grade=request.min_grade,
        max_grade=request.max_grade,
        tags=request.tags,
        icon=request.icon,
        available_from=request.available_from,
        available_until=request.available_until,
        creator_role=creator_role,
        created_by=current_user.sub,
        updated_by_pseudonym=current_user.sub,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)
    return TeacherAssistantResponse.model_validate(assistant)


@router.patch("/{assistant_id}", response_model=TeacherAssistantResponse)
async def update_my_assistant(
    assistant_id: int,
    request: TeacherAssistantUpdate,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> TeacherAssistantResponse:
    """Aktualisiert einen eigenen Assistenten. Nur im Status 'draft' erlaubt."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    if assistant.created_by != current_user.sub:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    if assistant.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Bearbeitung nur im Status 'draft' möglich. "
                   "Eingereichte Assistenten müssen zuerst zurückgezogen werden.",
        )

    update_data = request.model_dump(exclude_unset=True)
    _validate_teacher_fields(**{k: update_data.get(k) for k in (
        "name", "system_prompt", "audience", "scope", "scope_group_id",
        "min_grade", "max_grade", "available_from", "available_until",
    )})

    for field, value in update_data.items():
        setattr(assistant, field, value)
    assistant.updated_at = datetime.now(timezone.utc)
    assistant.updated_by_pseudonym = current_user.sub

    await db.commit()
    await db.refresh(assistant)
    return TeacherAssistantResponse.model_validate(assistant)


@router.delete("/{assistant_id}", status_code=204)
async def delete_my_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Löscht einen eigenen Assistenten (nur draft oder pending_review)."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    if assistant.created_by != current_user.sub:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    if assistant.status not in ("draft", "pending_review"):
        raise HTTPException(
            status_code=409,
            detail="Nur Assistenten im Status 'draft' oder 'pending_review' können gelöscht werden.",
        )
    await db.delete(assistant)
    await db.commit()


@router.post("/{assistant_id}/submit", response_model=TeacherAssistantResponse)
async def submit_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> TeacherAssistantResponse:
    """Reicht einen Entwurf zur Admin-Freigabe ein."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    if assistant.created_by != current_user.sub:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    if assistant.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Nur Assistenten im Status 'draft' können eingereicht werden.",
        )

    assistant.status = "pending_review"
    assistant.reject_reason = None   # vorherige Ablehnung löschen
    assistant.updated_at = datetime.now(timezone.utc)
    assistant.updated_by_pseudonym = current_user.sub

    await db.commit()
    await db.refresh(assistant)
    return TeacherAssistantResponse.model_validate(assistant)
