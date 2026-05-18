import json
import logging
from datetime import datetime, timezone
from typing import Optional

import jsonschema
import yaml
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_any_role
from app.config import settings
from app.auth.jwt import JwtPayload
from app.config import settings
from app.db.models import Assistant, Subject, AssistantDocument
from app.db.session import get_db
from app.upload.extractor import extract_pdf, extract_plaintext

logger = logging.getLogger(__name__)

# ── Schema Caching ───────────────────────────────────────────────────────────

_assistant_schema: Optional[dict] = None


def _get_assistant_schema() -> dict:
    """Laedt und cached das JSON Schema fuer Assistenten-Import."""
    global _assistant_schema
    if _assistant_schema is None:
        with open(settings.assistant_schema_path, encoding="utf-8") as f:
            _assistant_schema = json.load(f)
    return _assistant_schema


# ── Visibility Check ─────────────────────────────────────────────────────────

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


# ── Common Schemas ───────────────────────────────────────────────────────────

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
    created_by: Optional[str]
    model_config = ConfigDict(from_attributes=True)


class AssistantListResponse(BaseModel):
    items: list[AssistantSummary]


# ── Dokument-Schemas ────────────────────────────────────────────────────────

class AssistantDocumentOut(BaseModel):
    id: int
    filename: str
    mime_type: str
    size_bytes: int
    token_estimate: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentUploadResponse(BaseModel):
    id: int
    filename: str
    size_bytes: int
    token_estimate: int
    total_tokens: int
    document_count: int


# ── Hilfsfunktion für Dokument-Konvertierung ────────────────────────────────

def _doc_to_out(doc: AssistantDocument) -> AssistantDocumentOut:
    return AssistantDocumentOut(
        id=doc.id,
        filename=doc.filename,
        mime_type=doc.mime_type,
        size_bytes=doc.size_bytes,
        token_estimate=len(doc.content) // 4,
        created_at=doc.created_at,
    )


# ── Konsolidierte Schemas (ersetzt TeacherAssistant* und Admin Assistant*) ───

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
    scope_group_id: Optional[int] = None
    min_grade: Optional[int] = Field(default=None, ge=1, le=13)
    max_grade: Optional[int] = Field(default=None, ge=1, le=13)
    tags: Optional[list[str]] = None
    icon: Optional[str] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    sort_order: int = 0  # nur Admin wertet das aus; Lehrkraefte senden 0 oder nichts


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
    scope_group_id: Optional[int] = None
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
    scope_group_id: Optional[int]
    scope_pending: Optional[str]
    min_grade: Optional[int]
    max_grade: Optional[int]
    tags: Optional[list[str]]
    icon: Optional[str]
    available_from: Optional[datetime]
    available_until: Optional[datetime]
    sort_order: int
    created_by: Optional[str]
    creator_role: str
    reject_reason: Optional[str]
    updated_by_pseudonym: Optional[str]
    created_at: datetime
    updated_at: datetime
    documents: list[AssistantDocumentOut] = []

    model_config = ConfigDict(from_attributes=True)


class AssistantFullListResponse(BaseModel):
    items: list[AssistantResponse]
    total: int


# ── Import/Export Mapping ────────────────────────────────────────────────────


def _grades_list(min_grade: Optional[int], max_grade: Optional[int]) -> Optional[list[int]]:
    """Erzeugt eine Liste der Jahrgaenge."""
    if min_grade is None and max_grade is None:
        return None
    if min_grade == max_grade:
        return [min_grade]
    return list(range(min_grade or 0, (max_grade or 0) + 1))


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
    
    # Marktplatz-Felder aus import_metadata uebernehmen
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


# ── Validation ──────────────────────────────────────────────────────────────

VALID_AUDIENCES = {"student", "teacher", "all"}
VALID_SCOPES = {
    "private", "subject_department", "teachers", "activity_group",
    "teaching_group", "grade", "all_students", "all",
}
GROUP_SCOPES = {"subject_department", "activity_group", "teaching_group"}
SCHOOLWIDE_SCOPES = {"grade", "all_students", "all"}


def _initial_status(scope: str, creator_role: str) -> str:
    """Bestimmt den initialen Status eines Assistenten bei Erstellung.

    Admins starten immer im Draft. Lehrkraefte erhalten sofort 'active' fuer
    private und gruppen-beschraenkte Scopes; schulweite Scopes koennen eine
    Admin-Freigabe erfordern (abhaengig von teacher_schoolwide_sharing_requires_admin).
    """
    if creator_role == "admin":
        return "draft"
    if scope in SCHOOLWIDE_SCOPES:
        return "pending_review" if settings.teacher_schoolwide_sharing_requires_admin else "active"
    return "active"


def validate_assistant_fields(
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
    """Validiert Business-Regeln fuer Assistenten. Wirft HTTPException(422)."""
    if name is not None and not name.strip():
        raise HTTPException(status_code=422, detail="name darf nicht leer sein")
    if system_prompt is not None and not system_prompt.strip():
        raise HTTPException(status_code=422, detail="system_prompt darf nicht leer sein")
    if audience is not None and audience not in VALID_AUDIENCES:
        raise HTTPException(status_code=422, detail="Ungültiger audience-Wert")
    if scope is not None and scope not in VALID_SCOPES:
        raise HTTPException(status_code=422, detail="Ungültiger scope-Wert")
    if scope is not None and scope in GROUP_SCOPES and scope_group_id is None:
        raise HTTPException(
            status_code=422, detail="Gruppen-Scope erfordert eine scope_group_id"
        )
    if scope is not None and scope not in GROUP_SCOPES and scope_group_id is not None:
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


# ── Permission Helpers ───────────────────────────────────────────────────────

async def _load_and_authorize_assistant(assistant_id: int, current_user: JwtPayload, db: AsyncSession) -> Assistant:
    """Lädt einen Assistenten und prüft die Berechtigung. Wirft 404 oder 403."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    
    is_admin = "admin" in current_user.roles
    if not is_admin and assistant.created_by != current_user.sub:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    return assistant


def _check_assistant_access(assistant: Assistant, current_user: JwtPayload, is_admin: bool) -> None:
    """Prueft Zugriffsrechte auf einen Assistenten."""
    if not is_admin and assistant.created_by != current_user.sub:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")


def _check_assistant_update_permission(assistant: Assistant, current_user: JwtPayload, is_admin: bool) -> None:
    """Prueft Berechtigung fuer PATCH-Operationen."""
    if not is_admin:
        if assistant.created_by != current_user.sub:
            raise HTTPException(status_code=403, detail="Keine Berechtigung")
        if assistant.status != "draft":
            raise HTTPException(
                status_code=409,
                detail="Bearbeitung nur im Status 'draft' moeglich. "
                       "Eingereichte Assistenten muessen zuerst zurueckgezogen werden.",
            )


def _check_assistant_delete_permission(assistant: Assistant, current_user: JwtPayload, is_admin: bool) -> None:
    """Prueft Berechtigung fuer DELETE-Operationen."""
    if is_admin:
        if assistant.status not in ("draft", "disabled", "archived"):
            raise HTTPException(
                status_code=409,
                detail="Nur Assistenten im Status 'draft', 'disabled' oder 'archived' koennen geloescht werden.",
            )
    else:
        if assistant.created_by != current_user.sub:
            raise HTTPException(status_code=403, detail="Keine Berechtigung")
        if assistant.status not in ("draft", "pending_review"):
            raise HTTPException(
                status_code=409,
                detail="Nur eigene Assistenten im Status 'draft' oder 'pending_review' koennen geloescht werden.",
            )


router = APIRouter(prefix="/assistants", tags=["assistants"])


# ── Public Endpoints ─────────────────────────────────────────────────────────

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
                # private-Scope: nur fuer den Ersteller sichtbar
                or_(
                    Assistant.scope != "private",
                    Assistant.created_by == current_user.sub,
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


# ── Eigene Assistenten ───────────────────────────────────────────────────────
# Muss VOR /{assistant_id} registriert werden, sonst matched FastAPI "mine" als int-ID.

@router.get("/mine", response_model=AssistantFullListResponse)
async def list_my_assistants(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> AssistantFullListResponse:
    """Gibt alle eigenen Assistenten zurueck (alle Status)."""
    stmt = select(Assistant).where(Assistant.created_by == current_user.sub)
    if status is not None:
        stmt = stmt.where(Assistant.status == status)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar()

    stmt = stmt.order_by(Assistant.updated_at.desc()).limit(limit).offset(offset)
    assistants = (await db.execute(stmt)).scalars().all()

    return AssistantFullListResponse(
        items=[AssistantResponse.model_validate(a) for a in assistants],
        total=total,
    )


# ── Einzelabruf ─────────────────────────────────────────────────────────────

@router.get("/{assistant_id}", response_model=AssistantResponse)
async def get_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Gibt einen einzelnen Assistenten zurueck. Nur Eigentuemer oder Admin."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")

    is_admin = "admin" in current_user.roles
    _check_assistant_access(assistant, current_user, is_admin)

    # Dokumente für den Assistenten laden
    docs = (
        await db.execute(
            select(AssistantDocument)
            .where(AssistantDocument.assistant_id == assistant_id)
            .order_by(AssistantDocument.created_at)
        )
    ).scalars().all()

    response = AssistantResponse.model_validate(assistant)
    return response.model_copy(update={"documents": [_doc_to_out(d) for d in docs]})


@router.post("", response_model=AssistantResponse, status_code=201)
async def create_assistant(
    request: AssistantCreate,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Erstellt einen neuen Assistenten im Entwurfsstatus."""
    validate_assistant_fields(
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
    sort_order = request.sort_order if "admin" in current_user.roles else 0
    initial_status = _initial_status(request.scope, creator_role)

    assistant = Assistant(
        name=request.name,
        description=request.description,
        subject_id=request.subject_id,
        system_prompt=request.system_prompt,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        status=initial_status,
        audience=request.audience,
        scope=request.scope,
        scope_group_id=request.scope_group_id,
        min_grade=request.min_grade,
        max_grade=request.max_grade,
        tags=request.tags,
        icon=request.icon,
        available_from=request.available_from,
        available_until=request.available_until,
        sort_order=sort_order,
        creator_role=creator_role,
        created_by=current_user.sub,
        updated_by_pseudonym=current_user.sub,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)
    return AssistantResponse.model_validate(assistant)


@router.patch("/{assistant_id}", response_model=AssistantResponse)
async def update_assistant(
    assistant_id: int,
    request: AssistantUpdate,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Aktualisiert einen Assistenten."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    
    is_admin = "admin" in current_user.roles
    _check_assistant_update_permission(assistant, current_user, is_admin)
    
    update_data = request.model_dump(exclude_unset=True)
    validate_assistant_fields(**{k: update_data.get(k) for k in (
        "name", "system_prompt", "audience", "scope", "scope_group_id",
        "min_grade", "max_grade", "available_from", "available_until",
    )})
    
    # sort_order: nur Admin kann das aendern
    if not is_admin and "sort_order" in update_data:
        update_data["sort_order"] = assistant.sort_order

    # Scope-Aenderung durch Lehrkraft: Status automatisch anpassen
    if not is_admin and "scope" in update_data:
        new_scope = update_data["scope"]
        new_status = _initial_status(new_scope, "teacher")
        # Nur umschalten wenn der Assistent nicht bereits im Ziel-Status ist
        if assistant.status in ("active", "pending_review") and new_status != assistant.status:
            update_data["status"] = new_status
        # Wechsel von schulweit → privat/gruppe: reject_reason loeschen
        if new_status == "active" and assistant.reject_reason:
            update_data["reject_reason"] = None

    for field, value in update_data.items():
        setattr(assistant, field, value)
    assistant.updated_at = datetime.now(timezone.utc)
    assistant.updated_by_pseudonym = current_user.sub
    
    await db.commit()
    await db.refresh(assistant)
    return AssistantResponse.model_validate(assistant)


@router.delete("/{assistant_id}", status_code=204)
async def delete_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Loescht einen Assistenten."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    
    is_admin = "admin" in current_user.roles
    _check_assistant_delete_permission(assistant, current_user, is_admin)
    
    await db.delete(assistant)
    await db.commit()


@router.post("/{assistant_id}/submit", response_model=AssistantResponse)
async def submit_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
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
            detail="Nur Assistenten im Status 'draft' koennen eingereicht werden.",
        )

    assistant.status = "pending_review"
    assistant.reject_reason = None   # vorherige Ablehnung loeschen
    assistant.updated_at = datetime.now(timezone.utc)
    assistant.updated_by_pseudonym = current_user.sub

    await db.commit()
    await db.refresh(assistant)
    return AssistantResponse.model_validate(assistant)


# ── Dokument-Endpunkte ──────────────────────────────────────────────────────

MAX_DOCS = 3
MAX_TOTAL_TOKENS = 15_000
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB
ALLOWED_MIME = {"application/pdf", "text/plain", "text/markdown"}


@router.post("/{assistant_id}/documents", response_model=DocumentUploadResponse, status_code=201)
async def upload_assistant_document(
    assistant_id: int,
    file: UploadFile = File(...),
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> DocumentUploadResponse:
    """Lädt ein Kontext-Dokument für einen Assistenten hoch."""
    # 1. Assistent laden + Besitzprüfung
    assistant = await _load_and_authorize_assistant(assistant_id, current_user, db)
    
    # 2. Datei-Validierung
    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(422, "Datei überschreitet das Maximum von 2 MB.")
    mime = file.content_type or ""
    if mime not in ALLOWED_MIME:
        # Fallback: Endung prüfen
        name = (file.filename or "").lower()
        if name.endswith(".pdf"):
            mime = "application/pdf"
        elif name.endswith(".md"):
            mime = "text/markdown"
        elif name.endswith(".txt"):
            mime = "text/plain"
        else:
            raise HTTPException(422, "Nur PDF, TXT und Markdown (MD) sind erlaubt.")
    
    # 3. Klartext extrahieren
    try:
        if mime == "application/pdf":
            text = extract_pdf(data)
        else:
            text = extract_plaintext(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    
    # 4. Constraints prüfen
    existing_docs = (
        await db.execute(
            select(AssistantDocument).where(AssistantDocument.assistant_id == assistant_id)
        )
    ).scalars().all()
    
    if len(existing_docs) >= MAX_DOCS:
        raise HTTPException(422, f"Maximal {MAX_DOCS} Dokumente pro Assistent erlaubt.")
    
    existing_tokens = sum(len(d.content) // 4 for d in existing_docs)
    new_tokens = len(text) // 4
    if existing_tokens + new_tokens > MAX_TOTAL_TOKENS:
        raise HTTPException(
            422,
            f"Dieses Dokument würde das Token-Limit überschreiten "
            f"({existing_tokens + new_tokens} / {MAX_TOTAL_TOKENS}). "
            "Bitte entferne ein anderes Dokument oder verwende eine kürzere Datei."
        )
    
    # 5. Speichern
    doc = AssistantDocument(
        assistant_id=assistant_id,
        filename=file.filename or "dokument",
        mime_type=mime,
        size_bytes=len(data),
        content=text,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    
    total = existing_tokens + new_tokens
    return DocumentUploadResponse(
        id=doc.id,
        filename=doc.filename,
        size_bytes=doc.size_bytes,
        token_estimate=new_tokens,
        total_tokens=total,
        document_count=len(existing_docs) + 1,
    )


@router.get("/{assistant_id}/documents", response_model=list[AssistantDocumentOut])
async def list_assistant_documents(
    assistant_id: int,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[AssistantDocumentOut]:
    """Listet alle Kontext-Dokumente eines Assistenten auf."""
    await _load_and_authorize_assistant(assistant_id, current_user, db)
    docs = (
        await db.execute(
            select(AssistantDocument)
            .where(AssistantDocument.assistant_id == assistant_id)
            .order_by(AssistantDocument.created_at)
        )
    ).scalars().all()
    return [_doc_to_out(d) for d in docs]


@router.delete("/{assistant_id}/documents/{doc_id}", status_code=204)
async def delete_assistant_document(
    assistant_id: int,
    doc_id: int,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Löscht ein Kontext-Dokument eines Assistenten."""
    await _load_and_authorize_assistant(assistant_id, current_user, db)
    doc = (
        await db.execute(
            select(AssistantDocument).where(
                AssistantDocument.id == doc_id,
                AssistantDocument.assistant_id == assistant_id,
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "Dokument nicht gefunden.")
    await db.delete(doc)
    await db.commit()


@router.post("/import", response_model=AssistantResponse, status_code=201)
async def import_assistant(
    file: UploadFile = File(...),
    model_override: Optional[str] = None,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
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
    validate_assistant_fields(
        name=fields.get("name"),
        system_prompt=fields.get("system_prompt"),
        audience=fields.get("audience"),
        scope=fields.get("scope"),
        scope_group_id=fields.get("scope_group_id"),
        min_grade=fields.get("min_grade"),
        max_grade=fields.get("max_grade"),
        available_from=fields.get("available_from"),
        available_until=fields.get("available_until"),
    )
    
    creator_role = "admin" if "admin" in current_user.roles else "teacher"
    
    # Assistent erstellen
    assistant = Assistant(
        **fields,
        status="draft",
        creator_role=creator_role,
        created_by=current_user.sub,
        updated_by_pseudonym=current_user.sub,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        sort_order=0,  # Importierte Assistenten kommen als Draft, sort_order ist Admin-Sache
    )
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)
    
    return AssistantResponse.model_validate(assistant)


@router.get("/{assistant_id}/export")
async def export_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Exportiert einen Assistenten als YAML-Datei. Nur Eigentuemer oder Admin."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    
    is_admin = "admin" in current_user.roles
    _check_assistant_access(assistant, current_user, is_admin)
    
    # Subject-Slug fuer Export
    subject_slug = None
    if assistant.subject_id:
        subj_result = await db.execute(
            select(Subject.slug).where(Subject.id == assistant.subject_id)
        )
        subject_slug = subj_result.scalar_one_or_none()
    
    yaml_content = _assistant_to_yaml(assistant, subject_slug)
    
    # Dateiname: name kleingeschrieben, Leerzeichen -> Bindestrich
    slug = assistant.name.lower().replace(" ", "-")
    filename = f"{slug}.yaml"
    
    return Response(
        content=yaml_content,
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
