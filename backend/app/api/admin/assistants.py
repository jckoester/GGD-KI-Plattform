import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import jsonschema
import yaml
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.config import settings
from app.db.models import Assistant, Subject
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistants", tags=["admin-assistants"])

# ── Schema Caching ───────────────────────────────────────────────────────────

_assistant_schema: Optional[dict] = None


def _get_assistant_schema() -> dict:
    """Lädt und cached das JSON Schema für Assistenten-Import."""
    global _assistant_schema
    if _assistant_schema is None:
        with open(settings.assistant_schema_path, encoding="utf-8") as f:
            _assistant_schema = json.load(f)
    return _assistant_schema


# ── Pydantic Schemas ────────────────────────────────────────────────────────


class AssistantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    subject_id: Optional[int] = None
    system_prompt: str = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    audience: str = Field(default="student")
    scope: str = Field(default="private")
    min_grade: Optional[int] = Field(default=None, ge=1, le=13)
    max_grade: Optional[int] = Field(default=None, ge=1, le=13)
    tags: Optional[list[str]] = None
    icon: Optional[str] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    sort_order: int = 0


class AssistantUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    subject_id: Optional[int] = None
    system_prompt: Optional[str] = Field(default=None, min_length=1)
    model: Optional[str] = Field(default=None, min_length=1)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    audience: Optional[str] = None
    scope: Optional[str] = None
    min_grade: Optional[int] = Field(default=None, ge=1, le=13)
    max_grade: Optional[int] = Field(default=None, ge=1, le=13)
    tags: Optional[list[str]] = None
    icon: Optional[str] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    sort_order: Optional[int] = None


class AssistantResponse(BaseModel):
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
    scope_pending: Optional[str]
    min_grade: Optional[int]
    max_grade: Optional[int]
    tags: Optional[list[str]]
    icon: Optional[str]
    available_from: Optional[datetime]
    available_until: Optional[datetime]
    sort_order: int
    created_by_pseudonym: Optional[str]
    updated_by_pseudonym: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssistantListResponse(BaseModel):
    items: list[AssistantResponse]
    total: int


# ── Helper Functions ─────────────────────────────────────────────────────────

VALID_AUDIENCES = {"student", "teacher", "all"}
VALID_SCOPES = {
    "private", "subject_department", "teachers", "activity_group",
    "class_group", "grade", "all_students", "all",
}
GROUP_SCOPES = {"subject_department", "activity_group", "class_group"}


def _validate_assistant_fields(
    name: Optional[str] = None,
    system_prompt: Optional[str] = None,
    audience: Optional[str] = None,
    scope: Optional[str] = None,
    min_grade: Optional[int] = None,
    max_grade: Optional[int] = None,
    available_from: Optional[datetime] = None,
    available_until: Optional[datetime] = None,
) -> None:
    """Validiert alle Business-Regeln. Wirft HTTPException(422)."""
    if name is not None and not name.strip():
        raise HTTPException(status_code=422, detail="name darf nicht leer sein")
    if system_prompt is not None and not system_prompt.strip():
        raise HTTPException(status_code=422, detail="system_prompt darf nicht leer sein")
    if audience is not None and audience not in VALID_AUDIENCES:
        raise HTTPException(status_code=422, detail="Ungültiger audience-Wert")
    if scope is not None and scope not in VALID_SCOPES:
        raise HTTPException(status_code=422, detail="Ungültiger scope-Wert")
    if scope is not None and scope in GROUP_SCOPES:
        raise HTTPException(
            status_code=422,
            detail="Gruppen-Scopes sind erst ab Phase 3 verfügbar"
        )
    if audience == "teacher" and scope in {"all_students", "all"}:
        raise HTTPException(
            status_code=422,
            detail="teacher-Assistenten dürfen nicht für Schüler:innen sichtbar sein"
        )
    if available_from is not None and available_until is not None:
        if available_from >= available_until:
            raise HTTPException(
                status_code=422,
                detail="available_from muss vor available_until liegen"
            )
    if min_grade is not None and max_grade is not None:
        if min_grade > max_grade:
            raise HTTPException(
                status_code=422,
                detail="min_grade darf nicht größer als max_grade sein"
            )


# ── Import/Export Mapping ────────────────────────────────────────────────────


def _grades_list(min_grade: Optional[int], max_grade: Optional[int]) -> Optional[list[int]]:
    """Erzeugt eine Liste der Jahrgänge."""
    if min_grade is None and max_grade is None:
        return None
    if min_grade == max_grade:
        return [min_grade]
    return list(range(min_grade or 0, (max_grade or 0) + 1))


# Python 3.14 compatibility: datetime.fromisoformat doesn't handle 'T' or timezone
# so we use a custom parser
def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parsed ISO-8601 string to aware datetime (UTC). Returns None on error."""
    if not value or not value.strip():
        return None
    try:
        # Replace 'T' with space for compatibility
        normalized = value.replace('T', ' ')
        # Try parsing with timezone
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _assistant_to_yaml(assistant: Assistant, subject_slug: Optional[str]) -> str:
    """Serialisiert Assistent in YAML-Format."""
    data = {
        "metadata": {
            "name": assistant.name,
            "description": assistant.description,
            "subject": subject_slug,
            "grades": _grades_list(assistant.min_grade, assistant.max_grade),
            "tags": assistant.tags or [],
            "audience": assistant.audience,
            "available_from": assistant.available_from.isoformat() if assistant.available_from else None,
            "available_until": assistant.available_until.isoformat() if assistant.available_until else None,
            "updated": assistant.updated_at.date().isoformat(),
        },
        "config": {
            "model": assistant.model,
            "temperature": float(assistant.temperature) if assistant.temperature is not None else None,
            "max_tokens": assistant.max_tokens,
            "system_prompt": assistant.system_prompt,
        },
    }
    # None-Werte aus config entfernen
    data["config"] = {k: v for k, v in data["config"].items() if v is not None}
    data["metadata"] = {k: v for k, v in data["metadata"].items() if v is not None}
    
    # Marktplatz-Felder aus import_metadata übernehmen
    if assistant.import_metadata:
        for k in {"author", "license", "version", "created"}:
            if k in assistant.import_metadata:
                data["metadata"][k] = assistant.import_metadata[k]
    
    return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _yaml_to_assistant_fields(data: dict, subject_id: Optional[int]) -> dict:
    """Mappt YAML-Daten auf Assistenten-Felder."""
    meta = data["metadata"]
    config = data["config"]
    grades = meta.get("grades") or []
    return {
        "name": meta["name"].strip(),
        "description": meta.get("description"),
        "subject_id": subject_id,
        "system_prompt": config["system_prompt"].strip(),
        "model": config["model"].strip(),
        "temperature": config.get("temperature"),
        "max_tokens": config.get("max_tokens"),
        "audience": meta["audience"],
        "scope": "private",
        "min_grade": min(grades) if grades else None,
        "max_grade": max(grades) if grades else None,
        "tags": meta.get("tags"),
        "available_from": _parse_iso(meta.get("available_from")),
        "available_until": _parse_iso(meta.get("available_until")),
        "import_metadata": {
            k: meta.get(k)
            for k in ("author", "license", "version", "created")
            if meta.get(k) is not None
        } or None,
    }


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("", response_model=AssistantListResponse)
async def list_assistants(
    status: Optional[str] = None,
    audience: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AssistantListResponse:
    """Liste aller Assistenten mit optionalem Filter."""
    stmt = select(Assistant)
    
    if status is not None:
        stmt = stmt.where(Assistant.status == status)
    if audience is not None:
        stmt = stmt.where(Assistant.audience == audience)
    
    # Gesamtzahl
    total_stmt = select(text("count(*)")).select_from(stmt.subquery())
    total_result = await db.execute(total_stmt)
    total = total_result.scalar()
    
    # Paginierte Liste
    stmt = stmt.order_by(Assistant.sort_order.asc(), Assistant.name.asc())
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    assistants = result.scalars().all()
    
    return AssistantListResponse(
        items=[AssistantResponse.model_validate(a) for a in assistants],
        total=total,
    )


@router.post("", response_model=AssistantResponse, status_code=201)
async def create_assistant(
    request: AssistantCreate,
    current_user: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Erstellt einen neuen Assistenten als Draft."""
    # Validierung der Business-Regeln
    _validate_assistant_fields(
        name=request.name,
        system_prompt=request.system_prompt,
        audience=request.audience,
        scope=request.scope,
        min_grade=request.min_grade,
        max_grade=request.max_grade,
        available_from=request.available_from,
        available_until=request.available_until,
    )
    
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
        min_grade=request.min_grade,
        max_grade=request.max_grade,
        tags=request.tags,
        icon=request.icon,
        available_from=request.available_from,
        available_until=request.available_until,
        sort_order=request.sort_order,
        created_by_pseudonym=current_user.sub,
        updated_by_pseudonym=current_user.sub,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)
    
    return AssistantResponse.model_validate(assistant)


@router.get("/{assistant_id}", response_model=AssistantResponse)
async def get_assistant(
    assistant_id: int,
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Gibt einen Assistenten zurück."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    return AssistantResponse.model_validate(assistant)


@router.patch("/{assistant_id}", response_model=AssistantResponse)
async def update_assistant(
    assistant_id: int,
    request: AssistantUpdate,
    current_user: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Aktualisiert einen Assistenten."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    
    # Nur gesetzte Felder validieren und aktualisieren
    update_data = request.model_dump(exclude_unset=True)
    
    # Validierung der Business-Regeln für gesetzte Felder
    _validate_assistant_fields(
        name=update_data.get("name"),
        system_prompt=update_data.get("system_prompt"),
        audience=update_data.get("audience"),
        scope=update_data.get("scope"),
        min_grade=update_data.get("min_grade"),
        max_grade=update_data.get("max_grade"),
        available_from=update_data.get("available_from"),
        available_until=update_data.get("available_until"),
    )
    
    for field, value in update_data.items():
        if field == "updated_at":
            continue
        setattr(assistant, field, value)
    
    assistant.updated_at = datetime.now(timezone.utc)
    assistant.updated_by_pseudonym = current_user.sub
    
    await db.commit()
    await db.refresh(assistant)
    
    return AssistantResponse.model_validate(assistant)


@router.delete("/{assistant_id}", status_code=204)
async def delete_assistant(
    assistant_id: int,
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Löscht einen Assistenten (nur draft, disabled, archived)."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    
    if assistant.status == "active":
        raise HTTPException(
            status_code=409,
            detail="Aktive Assistenten können nicht direkt gelöscht werden. "
                   "Deaktivieren Sie den Assistenten zunächst."
        )
    
    await db.delete(assistant)
    await db.commit()


@router.post("/{assistant_id}/activate", response_model=AssistantResponse)
async def activate_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Aktiviert einen Assistenten."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    
    assistant.status = "active"
    assistant.updated_at = datetime.now(timezone.utc)
    assistant.updated_by_pseudonym = current_user.sub
    
    await db.commit()
    await db.refresh(assistant)
    
    return AssistantResponse.model_validate(assistant)


@router.post("/{assistant_id}/deactivate", response_model=AssistantResponse)
async def deactivate_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Deaktiviert einen Assistenten."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    
    assistant.status = "disabled"
    assistant.updated_at = datetime.now(timezone.utc)
    assistant.updated_by_pseudonym = current_user.sub
    
    await db.commit()
    await db.refresh(assistant)
    
    return AssistantResponse.model_validate(assistant)


@router.get("/{assistant_id}/export")
async def export_assistant(
    assistant_id: int,
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Exportiert einen Assistenten als YAML-Datei."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    
    # Subject-Slug für Export
    subject_slug = None
    if assistant.subject_id:
        subj_result = await db.execute(
            select(Subject.slug).where(Subject.id == assistant.subject_id)
        )
        subject_slug = subj_result.scalar_one_or_none()
    
    yaml_content = _assistant_to_yaml(assistant, subject_slug)
    
    # Dateiname: name kleingeschrieben, Leerzeichen → Bindestrich
    slug = assistant.name.lower().replace(" ", "-")
    filename = f"{slug}.yaml"
    
    return Response(
        content=yaml_content,
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.post("/import", response_model=AssistantResponse, status_code=201)
async def import_assistant(
    file: UploadFile = File(...),
    model_override: Optional[str] = None,
    current_user: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Importiert einen Assistenten aus einer YAML-Datei."""
    # YAML parsen
    try:
        content = await file.read()
        data = yaml.safe_load(content.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"YAML-Parsefehler: {exc}"
        )
    
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=422,
            detail="YAML muss ein Objekt (Dictionary) auf oberster Ebene enthalten"
        )
    
    # JSON-Schema-Validierung
    try:
        jsonschema.validate(instance=data, schema=_get_assistant_schema())
    except jsonschema.ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Schema-Validierungsfehler: {exc.message}"
        )
    
    # Subject-Lookup
    subject_id = None
    if "subject" in data.get("metadata", {}):
        subject_slug = data["metadata"]["subject"]
        if subject_slug:
            result = await db.execute(
                select(Subject.id).where(Subject.slug == subject_slug.lower())
            )
            subject_id = result.scalar_one_or_none()
    
    # Felder mappen
    fields = _yaml_to_assistant_fields(data, subject_id)
    
    # model_override anwenden
    if model_override:
        fields["model"] = model_override.strip()
    
    # Validierung der gemappten Felder
    _validate_assistant_fields(
        name=fields.get("name"),
        system_prompt=fields.get("system_prompt"),
        audience=fields.get("audience"),
        scope=fields.get("scope"),
        min_grade=fields.get("min_grade"),
        max_grade=fields.get("max_grade"),
        available_from=fields.get("available_from"),
        available_until=fields.get("available_until"),
    )
    
    # Assistent erstellen
    assistant = Assistant(
        **fields,
        status="draft",
        created_by_pseudonym=current_user.sub,
        updated_by_pseudonym=current_user.sub,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)
    
    return AssistantResponse.model_validate(assistant)
