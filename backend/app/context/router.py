"""CRUD-API für context_nodes.

Minimalimplementierung für KS-Phase-1 und -2-Tests.
Sichtbarkeitsfilter werden in KS-Phase-3 um group_memberships-Prüfung erweitert.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import sqlalchemy as sa

from sqlalchemy.exc import IntegrityError

from app.auth.dependencies import get_current_user, require_any_role
from app.auth.jwt import JwtPayload
from app.context.schemas import ContextAnchorCreate, ContextAnchorRead, ContextNodeCreate, ContextNodeRead, ContextNodeUpdate
from app.context.embedding import enqueue_embedding_job
from app.context.taxonomy import validate_content_type
from app.db.models import Assistant, AssistantContextAnchor, ContextNode
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/context", tags=["context"])

_TEACHER_OR_ADMIN = require_any_role(["teacher", "admin"])

# Nur strukturell sinnvolle Einstiegspunkte als retrieval_scope zulässig
VALID_SCOPE_ANCHOR_TYPES: frozenset[str] = frozenset({
    "fachplan", "leitidee", "pk_gruppe", "curriculum", "themengebiet",
    "unterrichtseinheit", "unterrichtsstunde",
})


async def _check_anchor_permission(
    assistant_id: int,
    db: AsyncSession,
    current_user: JwtPayload,
) -> Assistant:
    """Laedt den Assistenten und prueft Schreibrecht (Eigentuemer oder Admin)."""
    assistant = await db.get(Assistant, assistant_id)
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    if "admin" not in current_user.roles and assistant.created_by != current_user.sub:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    return assistant


def _check_write_permission(node: ContextNode, user: JwtPayload) -> None:
    """403 wenn weder Admin noch owner_pseudonym."""
    if "admin" not in user.roles and node.owner_pseudonym != user.sub:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")


def _visibility_filter(query, user: JwtPayload):
    """Phase-1-Sichtbarkeitsfilter: active + public scopes + eigene private Knoten."""
    return query.where(
        ContextNode.status == "active",
        or_(
            ContextNode.read_scope.in_(["global", "school", "subject", "group"]),
            ContextNode.owner_pseudonym == user.sub,
        ),
    )


# ── GET /api/context/nodes ────────────────────────────────────────────────────

@router.get("/nodes", response_model=list[ContextNodeRead])
async def list_nodes(
    category: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    q = select(ContextNode)
    q = _visibility_filter(q, user)
    if category:
        q = q.where(ContextNode.category == category)
    if content_type:
        q = q.where(ContextNode.content_type == content_type)
    if status:
        q = q.where(ContextNode.status == status)
    result = await db.execute(q.order_by(ContextNode.created_at.desc()))
    return result.scalars().all()


# ── GET /api/context/nodes/{id} ─────────────────────────────────────────────────

@router.get("/nodes/{node_id}", response_model=ContextNodeRead)
async def get_node(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    node = await db.get(ContextNode, node_id)
    if node is None or node.status == "deleted":
        raise HTTPException(status_code=404, detail="Knoten nicht gefunden")
    if node.read_scope == "private" and node.owner_pseudonym != user.sub:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    return node


# ── POST /api/context/nodes ────────────────────────────────────────────────────

@router.post("/nodes", response_model=ContextNodeRead, status_code=201)
async def create_node(
    payload: ContextNodeCreate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    try:
        validate_content_type(payload.category, payload.content_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    node = ContextNode(
        category=payload.category,
        content_type=payload.content_type,
        title=payload.title,
        content=payload.content,
        metadata_=payload.metadata_,
        owner_pseudonym=payload.owner_pseudonym or user.sub,
        read_scope=payload.read_scope,
        write_scope=payload.write_scope,
        read_scope_group_id=payload.read_scope_group_id,
        write_scope_group_id=payload.write_scope_group_id,
        assistant_id=payload.assistant_id,
        valid_until=payload.valid_until,
        schuljahr=payload.schuljahr,
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)

    # Embedding-Job
    await enqueue_embedding_job(node.id, db)

    return node


# ── PATCH /api/context/nodes/{id} ─────────────────────────────────────────────

@router.patch("/nodes/{node_id}", response_model=ContextNodeRead)
async def update_node(
    node_id: UUID,
    payload: ContextNodeUpdate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    node = await db.get(ContextNode, node_id)
    if node is None or node.status == "deleted":
        raise HTTPException(status_code=404, detail="Knoten nicht gefunden")
    _check_write_permission(node, user)

    update_data = payload.model_dump(exclude_unset=True, by_alias=False)
    for field, value in update_data.items():
        # metadata_ → DB-Spalte 'metadata'
        attr = field if field != "metadata_" else "metadata_"
        setattr(node, attr, value)

    await db.commit()
    await db.refresh(node)
    return node


# ── DELETE /api/context/nodes/{id} ────────────────────────────────────────────

@router.delete("/nodes/{node_id}", status_code=204)
async def delete_node(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    node = await db.get(ContextNode, node_id)
    if node is None or node.status == "deleted":
        raise HTTPException(status_code=404, detail="Knoten nicht gefunden")
    _check_write_permission(node, user)
    await db.delete(node)
    await db.commit()


# ── Context Anchors ────────────────────────────────────────────────────────

@router.get(
    "/assistants/{assistant_id}/anchors",
    response_model=list[ContextAnchorRead],
)
async def list_context_anchors(
    assistant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: JwtPayload = Depends(get_current_user),
) -> list[ContextAnchorRead]:
    await _check_anchor_permission(assistant_id, db, current_user)

    result = await db.execute(
        sa.select(
            AssistantContextAnchor.assistant_id,
            AssistantContextAnchor.node_id,
            AssistantContextAnchor.role,
            ContextNode.title.label("node_title"),
            ContextNode.content_type.label("node_content_type"),
        )
        .join(ContextNode, ContextNode.id == AssistantContextAnchor.node_id)
        .where(AssistantContextAnchor.assistant_id == assistant_id)
    )
    rows = result.mappings().all()
    return [ContextAnchorRead(**dict(row)) for row in rows]


@router.post(
    "/assistants/{assistant_id}/anchors",
    response_model=ContextAnchorRead,
    status_code=201,
)
async def add_context_anchor(
    assistant_id: int,
    body: ContextAnchorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: JwtPayload = Depends(get_current_user),
) -> ContextAnchorRead:
    await _check_anchor_permission(assistant_id, db, current_user)

    # Knoten laden und validieren
    node = await db.get(ContextNode, body.node_id)
    if node is None or node.status != "active":
        raise HTTPException(status_code=404, detail="Knoten nicht gefunden oder inaktiv")

    # Fuer retrieval_scope: nur strukturell sinnvolle Typen zulassen
    if body.role == "retrieval_scope" and node.content_type not in VALID_SCOPE_ANCHOR_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"content_type '{node.content_type}' ist kein gueltiger retrieval_scope-Anker. "
                f"Erlaubt: {sorted(VALID_SCOPE_ANCHOR_TYPES)}"
            ),
        )

    anchor = AssistantContextAnchor(
        assistant_id=assistant_id,
        node_id=body.node_id,
        role=body.role,
    )
    db.add(anchor)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Anker bereits vorhanden")

    await db.commit()
    await db.refresh(node)

    return ContextAnchorRead(
        assistant_id=assistant_id,
        node_id=body.node_id,
        role=body.role,
        node_title=node.title,
        node_content_type=node.content_type,
    )


@router.delete(
    "/assistants/{assistant_id}/anchors/{node_id}/{role}",
    status_code=204,
)
async def remove_context_anchor(
    assistant_id: int,
    node_id: UUID,
    role: str,
    db: AsyncSession = Depends(get_db),
    current_user: JwtPayload = Depends(get_current_user),
) -> None:
    await _check_anchor_permission(assistant_id, db, current_user)

    anchor = await db.get(
        AssistantContextAnchor, (assistant_id, node_id, role)
    )
    if anchor is None:
        raise HTTPException(status_code=404, detail="Anker nicht gefunden")
    await db.delete(anchor)
    await db.commit()
