"""CRUD-API für context_nodes.

Minimalimplementierung für KS-Phase-1 und -2-Tests.
Sichtbarkeitsfilter werden in KS-Phase-3 um group_memberships-Prüfung erweitert.
"""

import io
import logging
import os
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

import sqlalchemy as sa

from sqlalchemy.exc import IntegrityError

from app.auth.dependencies import get_current_user, require_any_role
from app.auth.jwt import JwtPayload
from app.context.schemas import (
    ContextAnchorCreate,
    ContextAnchorRead,
    ContextEdgeRead,
    ContextEdgeCreate,
    ContextNodeCreate,
    ContextNodeRead,
    ContextNodeUpdate,
    NeighborhoodResponse,
    ArchivedReferenceRead,
    ContextNodeCopyRequest,
    ChatContextNodeAdd,
    ChatContextNodeRead,
    ContextSearchRequest,
    ContextSearchResult,
    CurriculumRead,
    CurriculumDraftConfirmed,
    CurriculumCreate,
    FachplanTreeRead,
    LeitideeRead,
    IkKompetenzRead,
    PkGruppeRead,
    PkKompetenzRead,
)
from app.context.embedding import enqueue_embedding_job
from app.context.taxonomy import validate_content_type
from app.context.retrieval import VALID_SCOPE_ANCHOR_TYPES
from app.preferences.service import get_preferences
from app.db.models import (
    Assistant,
    AssistantContextAnchor,
    ChatContextNode,
    ContextEdge,
    ContextNode,
    Conversation,
    Group,
    GroupMembership,
    Subject,
)
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/context", tags=["context"])

_TEACHER_OR_ADMIN = require_any_role(["teacher", "admin"])


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


def _visibility_filter(query, user: JwtPayload, status_override: str | None = None):
    """Sichtbarkeitsfilter; status_override überschreibt den active-Default."""
    q = query.where(
        or_(
            ContextNode.read_scope.in_(["global", "school", "subject", "group"]),
            ContextNode.owner_pseudonym == user.sub,
        ),
    )
    if status_override is not None:
        q = q.where(ContextNode.status == status_override)
    else:
        q = q.where(ContextNode.status == "active")
    return q


# ── GET /api/context/nodes ────────────────────────────────────────────────────


@router.get("/nodes", response_model=list[ContextNodeRead])
async def list_nodes(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    content_type: list[str] | None = Query(default=None),
    status: str | None = Query(default=None),
    subject_slug: str | None = Query(default=None),
    group_id: int | None = Query(default=None),
    grade: int | None = Query(default=None, ge=1, le=13, description="Jahrgangsstufe"),
    owner: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    query = select(ContextNode)
    query = _visibility_filter(query, user, status_override=status)

    # subject_slug: Knoten deren Scope-Gruppe zu diesem Fach gehört,
    # plus schulweite/globale knowledge-Knoten mit passendem Fach oder fächerübergreifend
    if subject_slug:
        subquery_group_ids = (
            sa.select(Group.id)
            .join(Subject, Subject.id == Group.subject_id)
            .where(Subject.slug == subject_slug)
            .scalar_subquery()
        )
        # subject_id der Ziel-Slug nachschlagen
        subject_id_subq = (
            sa.select(Subject.id)
            .where(Subject.slug == subject_slug)
            .scalar_subquery()
        )
        query = query.where(
            or_(
                ContextNode.read_scope_group_id.in_(subquery_group_ids),
                and_(
                    ContextNode.read_scope.in_(["global", "school"]),
                    ContextNode.category == "knowledge",
                    or_(
                        ContextNode.subject_id == subject_id_subq,
                        ContextNode.subject_id.is_(None),
                    ),
                ),
            )
        )

    # group_id: nur Knoten mit exakt dieser read_scope_group_id
    if group_id is not None:
        query = query.where(ContextNode.read_scope_group_id == group_id)

    # grade: Jahrgangsstufen-Filter
    if grade is not None:
        query = query.where(
            or_(
                ContextNode.min_grade.is_(None),  # keine Stufenangabe = für alle
                and_(
                    ContextNode.min_grade <= grade,
                    ContextNode.max_grade >= grade,
                ),
            )
        )

    # owner=me: nur eigene Knoten
    if owner is not None:
        if owner != "me":
            raise HTTPException(status_code=400, detail="owner muss 'me' sein")
        query = query.where(ContextNode.owner_pseudonym == user.sub)

    if q:
        query = query.where(ContextNode.title.ilike(f"%{q}%"))
    if category:
        query = query.where(ContextNode.category == category)
    if content_type:
        query = query.where(ContextNode.content_type.in_(content_type))

    result = await db.execute(query.order_by(ContextNode.created_at.desc()))
    return result.scalars().all()


# ── GET /api/context/nodes/{id}/neighborhood ────────────────────────────────


@router.get("/nodes/{node_id}/neighborhood", response_model=NeighborhoodResponse)
async def get_neighborhood(
    node_id: UUID,
    depth: int = Query(default=2, ge=1, le=3),
    relation: list[str] | None = Query(default=None),
    category: list[str] | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    # Startknoten laden und prüfen
    node = await db.get(ContextNode, node_id)
    if node is None or node.status == "deleted":
        raise HTTPException(status_code=404, detail="Knoten nicht gefunden")

    # Recursive CTE für bidirektionale Traversierung
    neighborhood_cte = text("""
        WITH RECURSIVE nb AS (
            SELECT id, 0 AS depth
              FROM context_nodes WHERE id = :node_id
            UNION
            SELECT
                CASE WHEN e.from_node_id = nb.id THEN e.to_node_id
                     ELSE e.from_node_id END,
                nb.depth + 1
              FROM nb
              JOIN context_edges e
                ON e.from_node_id = nb.id OR e.to_node_id = nb.id
              JOIN context_nodes n
                ON n.id = CASE WHEN e.from_node_id = nb.id
                               THEN e.to_node_id ELSE e.from_node_id END
             WHERE nb.depth < :depth
               AND n.status = 'active'
        )
        SELECT DISTINCT id FROM nb
    """)
    result = await db.execute(neighborhood_cte, {"node_id": str(node_id), "depth": depth})
    neighbor_ids = [row[0] for row in result.fetchall()]

    # Knoten laden + Sichtbarkeitsfilter anwenden
    nodes_query = select(ContextNode).where(
        ContextNode.id.in_(neighbor_ids),
        ContextNode.status == "active",
        or_(
            ContextNode.read_scope.in_(["global", "school", "subject", "group"]),
            ContextNode.owner_pseudonym == user.sub,
        ),
    )
    if category:
        nodes_query = nodes_query.where(ContextNode.category.in_(category))
    nodes = (await db.execute(nodes_query)).scalars().all()
    visible_ids = {n.id for n in nodes}

    # Kanten zwischen sichtbaren Knoten laden
    edges_query = select(ContextEdge).where(
        ContextEdge.from_node_id.in_(visible_ids),
        ContextEdge.to_node_id.in_(visible_ids),
    )
    if relation:
        edges_query = edges_query.where(ContextEdge.relation.in_(relation))
    edges = (await db.execute(edges_query)).scalars().all()

    return NeighborhoodResponse(nodes=nodes, edges=edges)


# ── GET /api/context/nodes/{id}/archived-references ────────────────────────


@router.get(
    "/nodes/{node_id}/archived-references",
    response_model=list[ArchivedReferenceRead],
)
async def get_archived_references(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    # Startknoten laden
    node = await db.get(ContextNode, node_id)
    if node is None or node.status == "deleted":
        raise HTTPException(status_code=404, detail="Knoten nicht gefunden")

    sql = text("""
        SELECT
            n.id,
            n.title,
            n.category,
            n.content_type,
            n.archived_at,
            e.relation,
            (
                SELECT s.id FROM context_edges se
                  JOIN context_nodes s ON s.id = se.from_node_id
                 WHERE se.to_node_id = n.id
                   AND se.relation = 'supersedes'
                   AND s.status = 'active'
                 LIMIT 1
            ) AS suggested_successor_id
          FROM context_edges e
          JOIN context_nodes n ON n.id = e.to_node_id
         WHERE e.from_node_id = :node_id
           AND n.status = 'archived'
    """)
    result = await db.execute(sql, {"node_id": str(node_id)})
    rows = result.mappings().all()
    return [ArchivedReferenceRead(**dict(row)) for row in rows]


# ── POST /api/context/nodes/{id}/copy ───────────────────────────────────────


@router.post(
    "/nodes/{node_id}/copy",
    response_model=ContextNodeRead,
    status_code=201,
)
async def copy_node(
    node_id: UUID,
    payload: ContextNodeCopyRequest,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    # Quellknoten laden
    source = await db.get(ContextNode, node_id)
    if source is None or source.status == "deleted":
        raise HTTPException(status_code=404, detail="Knoten nicht gefunden")

    # Neuen Knoten anlegen
    new_node = ContextNode(
        category=source.category,
        content_type=source.content_type,
        title=source.title,
        content=source.content,
        metadata_=source.metadata_,
        owner_pseudonym=user.sub,
        read_scope=source.read_scope,
        write_scope=source.write_scope,
        read_scope_group_id=payload.read_scope_group_id or source.read_scope_group_id,
        write_scope_group_id=payload.write_scope_group_id or source.write_scope_group_id,
        valid_until=payload.valid_until,
        schuljahr=payload.schuljahr or source.schuljahr,
        status="active",
    )
    db.add(new_node)
    await db.commit()
    await db.refresh(new_node)
    await enqueue_embedding_job(new_node.id, db)
    return new_node


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
        subject_id=payload.subject_id,
        min_grade=payload.min_grade,
        max_grade=payload.max_grade,
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


# ── KS-Phase-5 Chat Context Nodes ──────────────────────────────────────────


async def _get_conversation_or_403(
    conversation_id: UUID,
    pseudonym: str,
    db: AsyncSession,
) -> None:
    """404 wenn Konversation nicht existiert, 403 wenn sie nicht dem Nutzer gehört."""
    conv = await db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden")
    if conv.pseudonym != pseudonym:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")


@router.get(
    "/conversations/{conversation_id}/nodes",
    response_model=list[ChatContextNodeRead],
)
async def list_chat_context_nodes(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await _get_conversation_or_403(conversation_id, user.sub, db)

    result = await db.execute(
        sa.select(
            ChatContextNode.node_id,
            ContextNode.category,
            ContextNode.title,
            ContextNode.content_type,
            ChatContextNode.added_at,
        )
        .join(ContextNode, ContextNode.id == ChatContextNode.node_id)
        .where(
            ChatContextNode.chat_id == conversation_id,
            ContextNode.status == "active",
        )
        .order_by(ChatContextNode.added_at)
    )
    rows = result.mappings().all()
    return [ChatContextNodeRead(**dict(row)) for row in rows]


@router.post(
    "/conversations/{conversation_id}/nodes",
    response_model=ChatContextNodeRead,
    status_code=201,
)
async def add_chat_context_node(
    conversation_id: UUID,
    payload: ChatContextNodeAdd,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await _get_conversation_or_403(conversation_id, user.sub, db)

    # Knoten existiert und ist aktiv?
    node = await db.get(ContextNode, payload.node_id)
    if node is None or node.status != "active":
        raise HTTPException(status_code=404, detail="Knoten nicht gefunden oder inaktiv")

    # Sichtbarkeit prüfen (kein privater Fremd-Knoten)
    if node.read_scope == "private" and node.owner_pseudonym != user.sub:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")

    existing = await db.get(ChatContextNode, (conversation_id, payload.node_id))
    if existing is not None:
        return ChatContextNodeRead(
            node_id=node.id,
            category=node.category,
            title=node.title,
            content_type=node.content_type,
            added_at=existing.added_at,
        )

    entry = ChatContextNode(chat_id=conversation_id, node_id=payload.node_id)
    db.add(entry)
    await db.flush()
    await db.commit()

    return ChatContextNodeRead(
        node_id=node.id,
        category=node.category,
        title=node.title,
        content_type=node.content_type,
        added_at=entry.added_at,
    )


@router.delete(
    "/conversations/{conversation_id}/nodes/{node_id}",
    status_code=204,
)
async def remove_chat_context_node(
    conversation_id: UUID,
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await _get_conversation_or_403(conversation_id, user.sub, db)

    entry = await db.get(ChatContextNode, (conversation_id, node_id))
    if entry is None:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    await db.delete(entry)
    await db.commit()


# ── KS-Phase-5 Semantic Search ──────────────────────────────────────────


@router.post("/search", response_model=list[ContextSearchResult])
async def search_context_nodes(
    request: ContextSearchRequest,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(get_current_user),
):
    """Semantische Suche über sichtbare Knoten anhand eines Freitexts."""
    from app.chat.router import _exec_search_context_nodes
    prefs = await get_preferences(db, user.sub)
    try:
        limit = max(5, min(30, int(prefs.get("context_search_limit", 8))))
    except (TypeError, ValueError):
        limit = 8
    results = await _exec_search_context_nodes(request.query, user.sub, db, limit=limit)
    return results


# ── KS-Phase-6 Curriculum Endpoints ──────────────────────────────────────


@router.get("/curricula/{curriculum_id}", response_model=CurriculumRead)
async def get_curriculum(
    curriculum_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(get_current_user),
):
    """Gibt das vollständige Curriculum als verschachteltes Objekt zurück."""
    import os
    
    # Curriculum-Knoten laden
    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.id == curriculum_id,
            ContextNode.status == "active",
            ContextNode.content_type == "curriculum",
        )
    )
    curriculum = result.scalar_one_or_none()
    
    if not curriculum:
        raise HTTPException(status_code=404, detail="Curriculum nicht gefunden oder inaktiv")
    
    # Sichtbarkeit prüfen
    if curriculum.read_scope == "private":
        if curriculum.owner_pseudonym != user.sub:
            raise HTTPException(status_code=403, detail="Keine Berechtigung")
    elif curriculum.read_scope == "subject":
        # Schüler dürfen nur mit ENV-Flag zugreifen
        if "student" in user.roles and "teacher" not in user.roles:
            if os.environ.get("CURRICULUM_VISIBLE_TO_STUDENTS", "false").lower() != "true":
                raise HTTPException(status_code=403, detail="Keine Berechtigung")
    
    # Alle Kapitel zu diesem Curriculum laden (via part_of-Kanten)
    result = await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(
            ContextEdge.to_node_id == curriculum_id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "kapitel",
            ContextNode.status == "active",
        )
        .order_by(ContextNode.metadata_["reihenfolge"].as_integer())
    )
    kapitel_nodes = result.scalars().all()

    kapitel_list = []
    for kap_node in kapitel_nodes:
        # Alle Lernsequenzen zu diesem Kapitel laden
        result = await db.execute(
            sa.select(ContextNode)
            .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
            .where(
                ContextEdge.to_node_id == kap_node.id,
                ContextEdge.relation == "part_of",
                ContextNode.content_type == "lernsequenz",
                ContextNode.status == "active",
            )
            .order_by(ContextNode.metadata_["reihenfolge"].as_integer())
        )
        lernsequenz_nodes = result.scalars().all()

        lernsequenzen_list = []
        for ls_node in lernsequenz_nodes:
            # IK-Referenzen laden
            result = await db.execute(
                sa.text("""
                    SELECT n.id, n.title, e.metadata->>'partiell' as partiell
                    FROM context_nodes n
                    JOIN context_edges e ON e.to_node_id = n.id
                    WHERE e.from_node_id = :ls_id
                      AND e.relation = 'references'
                      AND n.content_type = 'ik_kompetenz'
                      AND n.status = 'active'
                """),
                {"ls_id": str(ls_node.id)},
            )
            ik_refs = [
                {"node_id": str(row.id), "title": row.title, "partiell": row.partiell == "true"}
                for row in result.mappings().all()
            ]

            # PK-Referenzen laden
            result = await db.execute(
                sa.text("""
                    SELECT n.id, n.title
                    FROM context_nodes n
                    JOIN context_edges e ON e.to_node_id = n.id
                    WHERE e.from_node_id = :ls_id
                      AND e.relation = 'develops'
                      AND n.content_type = 'pk_kompetenz'
                      AND n.status = 'active'
                """),
                {"ls_id": str(ls_node.id)},
            )
            pk_refs = [
                {"node_id": str(row.id), "title": row.title}
                for row in result.mappings().all()
            ]

            # Leitperspektive-Referenzen laden
            result = await db.execute(
                sa.text("""
                    SELECT n.id, n.title, n.metadata->>'code' as lp_code
                    FROM context_nodes n
                    JOIN context_edges e ON e.to_node_id = n.id
                    WHERE e.from_node_id = :ls_id
                      AND e.relation = 'references'
                      AND n.content_type = 'leitperspektive'
                      AND n.status = 'active'
                """),
                {"ls_id": str(ls_node.id)},
            )
            leitperspektive_refs = [
                {"node_id": str(row.id), "title": row.title, "lp_code": row.lp_code}
                for row in result.mappings().all()
            ]
            
            lernsequenzen_list.append({
                "id": ls_node.id,
                "title": ls_node.title,
                "metadata": ls_node.metadata_ or {},
                "ik_refs": ik_refs,
                "pk_refs": pk_refs,
                "leitperspektive_refs": leitperspektive_refs,
            })
        
        kapitel_list.append({
            "id": kap_node.id,
            "title": kap_node.title,
            "metadata": kap_node.metadata_ or {},
            "lernsequenzen": lernsequenzen_list,
        })
    
    # Prüfe ob User editieren darf
    can_edit = False
    if "admin" in user.roles:
        can_edit = True
    elif curriculum.write_scope_group_id:
        result = await db.execute(
            sa.select(1).where(
                sa.exists().where(
                    GroupMembership.group_id == curriculum.write_scope_group_id,
                    GroupMembership.pseudonym == user.sub,
                )
            )
        )
        can_edit = result.scalar_one_or_none() is not None

    return {
        "id": curriculum.id,
        "title": curriculum.title,
        "metadata": curriculum.metadata_ or {},
        "subject_id": curriculum.subject_id,
        "write_scope_group_id": curriculum.write_scope_group_id,
        "kapitel": kapitel_list,
        "can_edit": can_edit,
    }


@router.get("/curricula/by-subject/{subject_id}", response_model=list[ContextNodeRead])
async def list_curricula_by_subject(
    subject_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(get_current_user),
):
    """Gibt alle Curriculum-Knoten eines Fachs zurück."""
    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "curriculum",
            ContextNode.subject_id == subject_id,
            ContextNode.status == "active",
            sa.or_(
                ContextNode.read_scope.in_(["global", "school", "subject"]),
                ContextNode.owner_pseudonym == user.sub,
            ),
        ).order_by(ContextNode.metadata_["jahrgangsstufe"])
    )
    curricula = result.scalars().all()
    return curricula


# ── KS-Phase-6 Curriculum Create (Stufe 2) ──────────────────────────────────

@router.post("/curricula", response_model=CurriculumRead, status_code=201)
async def create_curriculum(
    payload: CurriculumDraftConfirmed,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Speichert ein bestätigtes Curriculum aus dem Zwischenformat (Stufe 2).
    
    Nimmt das bestätigte Zwischenformat entgegen und erstellt alle Knoten und Kanten.
    """
    from app.context.service import import_curriculum_from_draft
    
    try:
        curriculum_id, stats = await import_curriculum_from_draft(
            db, payload, user.sub
        )
        
        # Log warnings
        for warning in stats.warnings:
            logger.warning(f"Curriculum-Import Warnung: {warning}")
        
        # Lade das erstellte Curriculum für die Rückgabe
        result = await db.execute(
            sa.select(ContextNode).where(ContextNode.id == curriculum_id)
        )
        curriculum = result.scalar_one()
        
        # Baue die verschachtelte Struktur (wie in get_curriculum)
        # Da wir gerade erstellt haben, können wir direkt die IDs verwenden
        kapitel_list = []
        for kap in payload.kapitel:
            # Finde kapitel_id
            kapitel_import_key = f"{payload.fachplan_id}_{payload.jahrgangsstufe}_kapitel_{kap.reihenfolge}"
            kap_result = await db.execute(
                sa.select(ContextNode.id).where(
                    ContextNode.content_type == "kapitel",
                    ContextNode.metadata_["import_key"].astext == kapitel_import_key
                )
            )
            kap_id = kap_result.scalar_one_or_none()
            
            if not kap_id:
                continue
                
            lernsequenzen_list = []
            for ls in kap.lernsequenzen:
                ls_reihenfolge = ls.reihenfolge if ls.reihenfolge is not None else 0
                ls_import_key = f"{kapitel_import_key}_ls_{ls_reihenfolge}"
                ls_result = await db.execute(
                    sa.select(ContextNode).where(
                        ContextNode.content_type == "lernsequenz",
                        ContextNode.metadata_["import_key"].astext == ls_import_key
                    )
                )
                ls_node = ls_result.scalar_one_or_none()
                
                if not ls_node:
                    continue
                
                # IK-Referenzen laden
                ik_result = await db.execute(
                    sa.text("""
                        SELECT n.id, n.title, e.metadata->>'partiell' as partiell
                        FROM context_nodes n
                        JOIN context_edges e ON e.to_node_id = n.id
                        WHERE e.from_node_id = :ls_id
                          AND e.relation = 'references'
                          AND n.content_type = 'ik_kompetenz'
                          AND n.status = 'active'
                    """),
                    {"ls_id": str(ls_node.id)},
                )
                ik_refs = [
                    {"node_id": str(row.id), "title": row.title, "partiell": row.partiell == "true"}
                    for row in ik_result.mappings().all()
                ]

                # PK-Referenzen laden
                pk_result = await db.execute(
                    sa.text("""
                        SELECT n.id, n.title
                        FROM context_nodes n
                        JOIN context_edges e ON e.to_node_id = n.id
                        WHERE e.from_node_id = :ls_id
                          AND e.relation = 'develops'
                          AND n.content_type = 'pk_kompetenz'
                          AND n.status = 'active'
                    """),
                    {"ls_id": str(ls_node.id)},
                )
                pk_refs = [
                    {"node_id": str(row.id), "title": row.title}
                    for row in pk_result.mappings().all()
                ]

                # Leitperspektive-Referenzen laden
                lp_result = await db.execute(
                    sa.text("""
                        SELECT n.id, n.title, n.metadata->>'code' as lp_code
                        FROM context_nodes n
                        JOIN context_edges e ON e.to_node_id = n.id
                        WHERE e.from_node_id = :ls_id
                          AND e.relation = 'references'
                          AND n.content_type = 'leitperspektive'
                          AND n.status = 'active'
                    """),
                    {"ls_id": str(ls_node.id)},
                )
                leitperspektive_refs = [
                    {"node_id": str(row.id), "title": row.title, "lp_code": row.lp_code}
                    for row in lp_result.mappings().all()
                ]
                
                lernsequenzen_list.append({
                    "id": ls_node.id,
                    "title": ls_node.title,
                    "metadata": ls_node.metadata_ or {},
                    "ik_refs": ik_refs,
                    "pk_refs": pk_refs,
                    "leitperspektive_refs": leitperspektive_refs,
                })
            
            kapitel_list.append({
                "id": kap_id,
                "title": kap_node.title if 'kap_node' in locals() else kap.titel,
                "metadata": {},  # Wird unten korrigiert
                "lernsequenzen": lernsequenzen_list,
            })
        
        # Korrigiere Kapitel-Metadata
        for kap in payload.kapitel:
            kapitel_import_key = f"{payload.fachplan_id}_{payload.jahrgangsstufe}_kapitel_{kap.reihenfolge}"
            kap_result = await db.execute(
                sa.select(ContextNode).where(
                    ContextNode.content_type == "kapitel",
                    ContextNode.metadata_["import_key"].astext == kapitel_import_key
                )
            )
            kap_node = kap_result.scalar_one_or_none()
            if kap_node:
                for k in kapitel_list:
                    if str(k["id"]) == str(kap_node.id):
                        k["metadata"] = kap_node.metadata_ or {}
                        k["title"] = kap_node.title
                        break
        
        # Prüfe can_edit
        department_group_id = curriculum.write_scope_group_id
        can_edit = False
        if "admin" in user.roles:
            can_edit = True
        elif department_group_id:
            result = await db.execute(
                sa.select(1).where(
                    sa.exists().where(
                        GroupMembership.group_id == department_group_id,
                        GroupMembership.pseudonym == user.sub,
                    )
                )
            )
            can_edit = result.scalar_one_or_none() is not None
        
        return {
            "id": curriculum.id,
            "title": curriculum.title,
            "metadata": curriculum.metadata_ or {},
            "subject_id": curriculum.subject_id,
            "write_scope_group_id": curriculum.write_scope_group_id,
            "kapitel": kapitel_list,
            "can_edit": can_edit,
        }
        
    except ValueError as e:
        logger.error(f"Validierungsfehler beim Curriculum-Import: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Fehler beim Curriculum-Import: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── KS-Phase-6 Edge CRUD Endpoints ──────────────────────────────────────


@router.post("/edges", response_model=ContextEdgeRead, status_code=201)
async def create_edge(
    payload: ContextEdgeCreate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Erstellt eine neue Kante zwischen zwei Knoten."""
    from app.db.models import ContextNode
    
    # Prüfe ob beide Knoten existieren
    from_node = await db.get(ContextNode, payload.from_node_id)
    to_node = await db.get(ContextNode, payload.to_node_id)
    
    if not from_node or from_node.status != "active":
        raise HTTPException(status_code=404, detail=f"Startknoten {payload.from_node_id} nicht gefunden")
    if not to_node or to_node.status != "active":
        raise HTTPException(status_code=404, detail=f"Zielknoten {payload.to_node_id} nicht gefunden")
    
    # Prüfe Schreibrecht auf from_node
    if from_node.write_scope == "private" and from_node.owner_pseudonym != user.sub:
        raise HTTPException(status_code=403, detail="Keine Schreibberechtigung auf Startknoten")
    if from_node.write_scope == "subject" or from_node.write_scope == "group":
        if from_node.write_scope_group_id:
            # Prüfe ob User Mitglied der Gruppe ist
            is_member = await db.execute(
                sa.select(1).where(
                    GroupMembership.group_id == from_node.write_scope_group_id,
                    GroupMembership.pseudonym == user.sub,
                )
            )
            if not is_member.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Keine Schreibberechtigung auf Startknoten")
    
    # Prüfe ob Kante bereits existiert (idempotent)
    existing = await db.execute(
        sa.select(ContextEdge).where(
            ContextEdge.from_node_id == payload.from_node_id,
            ContextEdge.to_node_id == payload.to_node_id,
            ContextEdge.relation == payload.relation,
        )
    )
    existing_edge = existing.scalar_one_or_none()
    if existing_edge:
        return existing_edge
    
    # Kante erstellen
    edge = ContextEdge(
        from_node_id=payload.from_node_id,
        to_node_id=payload.to_node_id,
        relation=payload.relation,
        metadata_=payload.metadata_,
    )
    db.add(edge)
    await db.commit()
    await db.refresh(edge)
    return edge


@router.delete("/edges/{edge_id}", status_code=204)
async def delete_edge(
    edge_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Löscht eine Kante."""
    edge = await db.get(ContextEdge, edge_id)
    if not edge:
        raise HTTPException(status_code=404, detail="Kante nicht gefunden")
    
    # Prüfe Schreibrecht auf from_node
    from_node = await db.get(ContextNode, edge.from_node_id)
    if not from_node or from_node.status != "active":
        raise HTTPException(status_code=404, detail="Startknoten nicht gefunden")
    
    if from_node.write_scope == "private" and from_node.owner_pseudonym != user.sub:
        raise HTTPException(status_code=403, detail="Keine Schreibberechtigung auf Startknoten")
    if from_node.write_scope == "subject" or from_node.write_scope == "group":
        if from_node.write_scope_group_id:
            is_member = await db.execute(
                sa.select(1).where(
                    GroupMembership.group_id == from_node.write_scope_group_id,
                    GroupMembership.pseudonym == user.sub,
                )
            )
            if not is_member.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Keine Schreibberechtigung auf Startknoten")
    
    await db.delete(edge)
    await db.commit()


@router.get("/nodes/{node_id}/edges", response_model=list[ContextEdgeRead])
async def get_node_edges(
    node_id: UUID,
    relation: list[str] | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(get_current_user),
):
    """Gibt alle ausgehenden Kanten eines Knotens zurück."""
    # Prüfe ob Knoten existiert und sichtbar ist
    node = await db.get(ContextNode, node_id)
    if not node or node.status != "active":
        raise HTTPException(status_code=404, detail="Knoten nicht gefunden")
    
    # Sichtbarkeitsprüfung
    if node.read_scope == "private" and node.owner_pseudonym != user.sub:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    
    query = select(ContextEdge).where(
        ContextEdge.from_node_id == node_id,
    )
    if relation:
        query = query.where(ContextEdge.relation.in_(relation))
    
    edges = (await db.execute(query)).scalars().all()
    return edges


# ── KS-Phase-6 Curriculum Create Endpoint ──────────────────────────────────


@router.post("/curricula/new", response_model=ContextNodeRead, status_code=201)
async def create_curriculum_node(
    payload: CurriculumCreate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Erstellt einen neuen leeren Curriculum-Knoten für den Editor."""
    from app.db.models import Group
    
    # Subject laden
    subject = await db.execute(
        sa.select(Group.subject_id).where(
            sa.or_(
                Group.type == "subject_department",
                Group.type == "subject",
            ),
            Group.metadata_["fach_code"].astext == payload.fach_code,
        ).limit(1)
    )
    subject_row = subject.fetchone()
    if not subject_row:
        # Alternative: direkt aus subjects Tabelle
        subj = await db.execute(
            sa.select(Subject.id).where(
                Subject.metadata_["fach_code"].astext == payload.fach_code
            ).limit(1)
        )
        subject_id = subj.scalar_one_or_none()
    else:
        subject_id = subject_row[0]
    
    if not subject_id:
        raise HTTPException(
            status_code=422,
            detail=f"Fach mit fach_code '{payload.fach_code}' nicht gefunden"
        )
    
    # Fachschafts-Gruppen-ID
    department_group = await db.execute(
        sa.select(Group.id).where(
            Group.subject_id == subject_id,
            Group.type == "subject_department",
        ).limit(1)
    )
    department_group_id = department_group.scalar_one_or_none()
    
    # Prüfe ob User Mitglied der Fachschaft ist
    if department_group_id:
        is_member = await db.execute(
            sa.select(1).where(
                GroupMembership.group_id == department_group_id,
                GroupMembership.pseudonym == user.sub,
            )
        )
        if not is_member.scalar_one_or_none() and "admin" not in user.roles:
            raise HTTPException(
                status_code=403,
                detail="Keine Berechtigung - Sie müssen Mitglied der Fachschaft sein"
            )
    
    # Fachplan laden
    fachplan = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "fachplan",
            ContextNode.metadata_["fachplan_id"].astext == payload.fachplan_id,
            ContextNode.status == "active",
        ).limit(1)
    )
    fachplan_node = fachplan.scalar_one_or_none()
    
    # Curriculum-Knoten erstellen
    import_key = f"new_{user.sub}_{payload.fach_code}_{payload.jahrgangsstufe}"
    
    curriculum = ContextNode(
        category="knowledge",
        content_type="curriculum",
        title=f"{payload.fach_code} {payload.schulart} Kl. {payload.jahrgangsstufe}",
        content=None,
        read_scope="school",
        write_scope="subject",
        write_scope_group_id=department_group_id,
        subject_id=subject_id,
        owner_pseudonym=user.sub,
        metadata_={
            "fachplan_id": payload.fachplan_id,
            "bp_version": payload.bp_version,
            "schule": payload.schule,
            "fach_code": payload.fach_code,
            "schulart": payload.schulart,
            "jahrgangsstufe": payload.jahrgangsstufe,
            "import_key": import_key,
        },
        status="active",
    )
    db.add(curriculum)
    await db.commit()
    await db.refresh(curriculum)
    
    # part_of-Kante zum Fachplan
    if fachplan_node:
        edge = ContextEdge(
            from_node_id=curriculum.id,
            to_node_id=fachplan_node.id,
            relation="part_of",
            metadata_={},
        )
        db.add(edge)
        await db.commit()
    
    return curriculum


# ── Bildungsplan Hierarchie Endpoint ────────────────────────────────────────


@router.get("/fachplan/by-subject/{subject_id}", response_model=FachplanTreeRead)
async def get_fachplan_by_subject(
    subject_id: int,
    grade: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(get_current_user),
):
    """Gibt die Bildungsplan-Hierarchie für ein Fach als verschachteltes Objekt zurück.
    
    Lädt den Fachplan und alle zugehörigen Leitideen mit IK-Kompetenz-Kindern
    sowie PK-Gruppen mit PK-Kompetenz-Kindern für das gegebene Fach und optional
    die angegebene Jahrgangsstufe.
    
    Die Hierarchie basiert auf part_of-Kanten:
    - leitidee -> part_of -> fachplan
    - ik_kompetenz -> part_of -> leitidee  
    - pk_gruppe -> part_of -> fachplan
    - pk_kompetenz -> part_of -> pk_gruppe
    """
    
    # Fachplan-Knoten für dieses Fach laden
    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "fachplan",
            ContextNode.subject_id == subject_id,
            ContextNode.status == "active",
        )
    )
    fachplan_node = result.scalar_one_or_none()
    
    if not fachplan_node:
        # Kein Fachplan für dieses Fach gefunden
        return FachplanTreeRead(
            fachplan=None,
            leitideen=[],
            pk_gruppen=[],
            can_edit=False,
        )
    
    # Alle Leitideen laden, die part_of -> fachplan sind
    leitideen_result = await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(
            ContextEdge.to_node_id == fachplan_node.id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "leitidee",
            ContextNode.status == "active",
        )
        .order_by(ContextNode.title)
    )
    leitideen_nodes = leitideen_result.scalars().all()
    
    # Für jede Leitidee die IK-Kompetenz-Kinder laden
    leitideen_list = []
    for ld_node in leitideen_nodes:
        # Prüfe grade-Filter aus metadata wenn vorhanden
        if grade and ld_node.metadata_.get("grade"):
            # Leitidee hat grade-Metadaten, aber wir filtern IK-Kompetenz nach grade
            pass
        
        # IK-Kompetenz-Kinder laden
        ik_result = await db.execute(
            sa.select(ContextNode)
            .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
            .where(
                ContextEdge.to_node_id == ld_node.id,
                ContextEdge.relation == "part_of",
                ContextNode.content_type == "ik_kompetenz",
                ContextNode.status == "active",
            )
            .order_by(
                sa.cast(ContextNode.metadata_["standard_nr"], sa.Integer).asc(),
                ContextNode.title,
            )
        )
        ik_nodes = ik_result.scalars().all()
        
        # Filter nach grade wenn angegeben
        if grade:
            ik_nodes = [
                n for n in ik_nodes
                if str(grade) in str(n.metadata_.get("grade_band", ""))
                or str(grade) in str(n.metadata_.get("jahrgangsstufe", ""))
            ]
        
        ik_list = [
            IkKompetenzRead(
                id=n.id,
                title=n.title,
                metadata_=n.metadata_,
            )
            for n in ik_nodes
        ]
        
        leitideen_list.append(
            LeitideeRead(
                id=ld_node.id,
                title=ld_node.title,
                metadata_=ld_node.metadata_,
                ik_kompetenzen=ik_list,
            )
        )
    
    # Alle PK-Gruppen laden, die part_of -> fachplan sind
    pk_gruppen_result = await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(
            ContextEdge.to_node_id == fachplan_node.id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "pk_gruppe",
            ContextNode.status == "active",
        )
        .order_by(ContextNode.title)
    )
    pk_gruppen_nodes = pk_gruppen_result.scalars().all()
    
    # Für jede PK-Gruppe die PK-Kompetenz-Kinder laden
    pk_gruppen_list = []
    for pg_node in pk_gruppen_nodes:
        # PK-Kompetenz-Kinder laden
        pk_result = await db.execute(
            sa.select(ContextNode)
            .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
            .where(
                ContextEdge.to_node_id == pg_node.id,
                ContextEdge.relation == "part_of",
                ContextNode.content_type == "pk_kompetenz",
                ContextNode.status == "active",
            )
            .order_by(ContextNode.title)
        )
        pk_nodes = pk_result.scalars().all()
        
        pk_list = [
            PkKompetenzRead(
                id=n.id,
                title=n.title,
                metadata_=n.metadata_,
            )
            for n in pk_nodes
        ]
        
        pk_gruppen_list.append(
            PkGruppeRead(
                id=pg_node.id,
                title=pg_node.title,
                metadata_=pg_node.metadata_,
                pk_kompetenzen=pk_list,
            )
        )
    
    return FachplanTreeRead(
        fachplan=ContextNodeRead.model_validate(fachplan_node),
        leitideen=leitideen_list,
        pk_gruppen=pk_gruppen_list,
        can_edit=False,  # Phase: read-only
    )


