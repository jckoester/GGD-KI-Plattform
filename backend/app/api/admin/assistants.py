import io
import logging
import zipfile
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.assistants import (
    AssistantResponse,
    AssistantFullListResponse,
    _assistant_to_yaml,
)
from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.db.models import Assistant, Subject
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistants", tags=["admin-assistants"])


# ── Local Schemas (nur was nicht aus assistants importiert wird) ───────────────

class RejectBody(BaseModel):
    reason: Optional[str] = None


class OrphanedAssistant(BaseModel):
    id: int
    name: str
    model: str
    status: str


class ModelCheckResponse(BaseModel):
    """Assistenten, deren fest gewähltes Modell es in LiteLLM nicht (mehr) gibt.

    `checked=False` heißt: LiteLLM war nicht erreichbar — dann ist `orphaned` leer und
    bedeutet *nicht*, dass alles in Ordnung ist. Die UI muss beides unterscheiden können,
    sonst suggeriert ein Ausfall fälschlich Unauffälligkeit.
    """

    checked: bool
    orphaned: list[OrphanedAssistant]


# ── Admin-only Endpoints ─────────────────────────────────────────────────────

@router.get("", response_model=AssistantFullListResponse)
async def list_assistants(
    status: Optional[str] = None,
    audience: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AssistantFullListResponse:
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
    
    return AssistantFullListResponse(
        items=[AssistantResponse.model_validate(a) for a in assistants],
        total=total,
    )


@router.get("/model-check", response_model=ModelCheckResponse)
async def check_assistant_models(
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> ModelCheckResponse:
    """Meldet Assistenten, deren gewähltes Modell in LiteLLM nicht mehr existiert.

    Ein Assistent, der auf einen konkreten Modellnamen gebunden ist, bricht **still**, sobald
    dieser aus der `model_list` fällt (Anbieterwechsel, abgekündigtes Modell). Ein Hinweis im
    Editor hilft nur dem, der ihn beim Anlegen liest — nicht dem, der ein Jahr später erbt.

    Bewusst über **alle** Assistenten statt als Feld an der paginierten Liste: Sonst bliebe
    ein defekter Assistent auf Seite 3 unsichtbar.

    Assistenten ohne eigenes Modell sind kein Warnfall — sie folgen `CHAT_DEFAULT_MODEL`
    (Schritt 7). Archivierte ebenfalls nicht: Sie laufen ohnehin nicht mehr.

    Es wird nichts automatisch korrigiert — welches Modell fachlich passt, entscheidet der
    Mensch.
    """
    from app.litellm.client import LiteLLMClient

    client = LiteLLMClient()
    try:
        known = set(await client.list_models())
    except Exception as exc:
        logger.warning(
            "Modell-Abgleich der Assistenten nicht möglich (%s): %s", type(exc).__name__, exc
        )
        return ModelCheckResponse(checked=False, orphaned=[])
    finally:
        await client.close()

    result = await db.execute(
        select(Assistant)
        .where(Assistant.model != "", Assistant.status != "archived")
        .order_by(Assistant.name.asc())
    )
    orphaned = [
        OrphanedAssistant(id=a.id, name=a.name, model=a.model, status=a.status)
        for a in result.scalars().all()
        if a.model not in known
    ]
    if orphaned:
        logger.warning(
            "%d Assistent(en) verweisen auf unbekannte Modelle: %s",
            len(orphaned), ", ".join(sorted({o.model for o in orphaned})),
        )
    return ModelCheckResponse(checked=True, orphaned=orphaned)


@router.get("/pending", response_model=AssistantFullListResponse)
async def list_pending_assistants(
    limit: int = 50,
    offset: int = 0,
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AssistantFullListResponse:
    """Gibt alle Assistenten im Status 'pending_review' zurueck."""
    stmt = select(Assistant).where(Assistant.status == "pending_review")

    total_stmt = select(text("count(*)")).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar()

    stmt = stmt.order_by(Assistant.updated_at.asc()).limit(limit).offset(offset)
    assistants = (await db.execute(stmt)).scalars().all()

    return AssistantFullListResponse(
        items=[AssistantResponse.model_validate(a) for a in assistants],
        total=total,
    )


@router.post("/{assistant_id}/approve", response_model=AssistantResponse)
async def approve_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Gibt einen eingereichten Assistenten frei (→ active)."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    if assistant.status != "pending_review":
        raise HTTPException(
            status_code=409,
            detail="Nur Assistenten im Status 'pending_review' koennen freigegeben werden.",
        )

    assistant.status = "active"
    assistant.reject_reason = None
    assistant.updated_at = datetime.now(timezone.utc)
    assistant.updated_by_pseudonym = current_user.sub

    await db.commit()
    await db.refresh(assistant)
    # Zielgruppe ist ein bewusster Prüfpunkt (Phase 13): eine Fehlkonfiguration hat
    # pädagogische Folgen (Schüler:innen-Sichtbarkeit, Präambel-/Augmentierungs-Auswahl).
    logger.info(
        "Assistent freigegeben (id=%s, audience=%s, scope=%s)",
        assistant.id,
        assistant.audience,
        assistant.scope,
    )
    return AssistantResponse.model_validate(assistant)


@router.post("/{assistant_id}/reject", response_model=AssistantResponse)
async def reject_assistant(
    assistant_id: int,
    body: RejectBody,
    current_user: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Lehnt einen eingereichten Assistenten ab (→ draft + reject_reason)."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    if assistant.status != "pending_review":
        raise HTTPException(
            status_code=409,
            detail="Nur Assistenten im Status 'pending_review' koennen abgelehnt werden.",
        )

    assistant.status = "draft"
    assistant.reject_reason = body.reason
    assistant.updated_at = datetime.now(timezone.utc)
    assistant.updated_by_pseudonym = current_user.sub

    await db.commit()
    await db.refresh(assistant)
    return AssistantResponse.model_validate(assistant)


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


@router.get("/export-all")
async def export_all_assistants(
    status: Optional[str] = "active",
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Exportiert alle aktiven (oder gefilterten) Assistenten als ZIP-Datei."""
    # Assistenten abrufen
    stmt = select(Assistant)
    if status is not None:
        stmt = stmt.where(Assistant.status == status)
    stmt = stmt.order_by(Assistant.name.asc())
    
    result = await db.execute(stmt)
    assistants = result.scalars().all()
    
    if not assistants:
        raise HTTPException(status_code=404, detail="Keine Assistenten zum Exportieren gefunden")
    
    # Subject-Slugs für alle Assistenten vorab laden
    subject_ids = {a.subject_id for a in assistants if a.subject_id}
    subject_slugs = {}
    if subject_ids:
        subj_result = await db.execute(
            select(Subject.id, Subject.slug).where(Subject.id.in_(subject_ids))
        )
        for subj_id, slug in subj_result:
            subject_slugs[subj_id] = slug
    
    # ZIP-Datei im Speicher erstellen
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for assistant in assistants:
            subject_slug = subject_slugs.get(assistant.subject_id)
            yaml_content = _assistant_to_yaml(assistant, subject_slug)
            
            # Dateiname: name kleingeschrieben, Leerzeichen → Bindestrich
            slug = assistant.name.lower().replace(" ", "-")
            filename = f"{slug}.yaml"
            
            zipf.writestr(filename, yaml_content.encode("utf-8"))
    
    zip_buffer.seek(0)
    
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=assistants-export.zip"
        }
    )
