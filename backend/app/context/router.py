"""CRUD-API für context_nodes.

Minimalimplementierung für KS-Phase-1 und -2-Tests.
Sichtbarkeitsfilter werden in KS-Phase-3 um group_memberships-Prüfung erweitert.
"""

import logging
import os
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
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
    CurriculumDraft,
    CurriculumDraftConfirmed,
    CurriculumCreate,
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


# ── KS-Phase-6 Curriculum Convert (Stufe 1) ─────────────────────────────────

@router.post("/curricula/convert", response_model=CurriculumDraft)
async def convert_curriculum(
    file: UploadFile,
    fachplan_id: str = Form(...),
    bp_version: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Konvertiert PDF/Word-Dokument zu strukturiertem Zwischenformat (Stufe 1).
    
    Nimmt ein PDF- oder Word-Dokument entgegen und extrahiert die Curriculum-Struktur
    mit LLM-Unterstützung. Das Ergebnis ist ein CurriculumDraft für den Prüfungsschritt.
    """
    import re
    from fastapi import UploadFile, Form
    
    # Datei-Inhalt lesen
    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Fehler beim Lesen der Datei: {e}")
        raise HTTPException(status_code=400, detail="Datei konnte nicht gelesen werden")
    
    # Dateityp erkennen
    filename = file.filename or ""
    is_pdf = filename.lower().endswith(".pdf")
    is_word = filename.lower().endswith((".docx", ".doc"))
    
    if not is_pdf and not is_word:
        raise HTTPException(
            status_code=400,
            detail="Nur PDF oder Word-Dokumente (.docx, .doc) werden unterstützt"
        )
    
    # Text extrahieren
    text_content = ""
    try:
        if is_pdf:
            text_content = _extract_text_from_pdf(content)
        elif is_word:
            text_content = _extract_text_from_word(content)
    except Exception as e:
        logger.error(f"Fehler bei der Textextraktion: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Textextraktion fehlgeschlagen: {str(e)}"
        )
    
    # Format erkennen
    format_detected, warnings = _detect_format(text_content)
    
    if format_detected is None:
        return CurriculumDraft(
            unsupported_format=True,
            format_detected=None,
            warnings=[
                "Dokument hat ein nicht unterstütztes Format (Kompetenzmatrix). "
                "Bitte als statischen 'document'-Knoten hochladen."
            ],
            data=None
        )
    
    # LLM-Extraktion (vereinfacht - in Produktion mit echtem LLM-Aufruf)
    try:
        draft_data = _extract_curriculum_structure(text_content, format_detected, fachplan_id, bp_version)
        return CurriculumDraft(
            unsupported_format=False,
            format_detected=format_detected,
            warnings=warnings,
            data=draft_data
        )
    except Exception as e:
        logger.error(f"LLM-Extraktion fehlgeschlagen: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Strukturextraktion fehlgeschlagen: {str(e)}"
        )


def _extract_text_from_pdf(content: bytes) -> str:
    """Extrahiert Text aus PDF-Datei."""
    try:
        import pdfplumber
        import io
        
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text_parts = []
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
            return "\n".join(text_parts)
    except ImportError:
        logger.warning("pdfplumber nicht installiert - verwende Fallback")
        # Fallback: versuche mit PyPDF2
        try:
            from PyPDF2 import PdfReader
            import io
            reader = PdfReader(io.BytesIO(content))
            text_parts = []
            for page in reader.pages:
                text_parts.append(page.extract_text() or "")
            return "\n".join(text_parts)
        except ImportError:
            raise ImportError("Weder pdfplumber noch PyPDF2 installiert")


def _extract_text_from_word(content: bytes) -> str:
    """Extrahiert Text aus Word-Dokument."""
    try:
        from docx import Document
        import io
        
        doc = Document(io.BytesIO(content))
        return "\n".join([p.text for p in doc.paragraphs])
    except ImportError:
        logger.warning("python-docx nicht installiert - versuche textract")
        try:
            import textract
            return textract.process(content).decode("utf-8", errors="replace")
        except ImportError:
            raise ImportError("Weder python-docx noch textract installiert")


def _detect_format(text_content: str) -> tuple[str | None, list[str]]:
    """Erkennt das Dokumentenformat (A, B oder nicht unterstützt).
    
    Rückgabe: (format_detected, warnings)
    """
    warnings = []
    lines = text_content.split("\n")
    
    # Zeilen analysieren
    has_4_columns = False
    has_lernsequenz_header = False
    has_ik_column = False
    has_pk_column = False
    has_kompetenzmatrix = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Prüfe auf 4-Spalten-Struktur (Format A und B)
        # Typische Trennzeichen: Tab, |, oder feste Spaltenbreiten
        parts = [p.strip() for p in re.split(r'[\t|]', line) if p.strip()]
        if len(parts) >= 4:
            has_4_columns = True
            # Prüfe ob erste Spalte PK-ähnlich ist
            if re.match(r'^(PK|pK|P\.?K\.?)', parts[0], re.IGNORECASE):
                has_pk_column = True
            # Prüfe ob IK-ähnliche Einträge in der Zeile sind
            if re.search(r'\bIK\s*\d+', line, re.IGNORECASE) or re.search(r'\b[1-9]\d*\.\d+', line):
                has_ik_column = True
        
        # Prüfe auf Lernsequenz-Header (fett in Spalte 3)
        # In PDFs oft als **Text** oder mit speziellen Markern
        if re.search(r'\*\*(.+?)\*\*', line) or re.search(r'\bLernsequenz\b', line, re.IGNORECASE):
            has_lernsequenz_header = True
        
        # Prüfe auf Kompetenzmatrix-Format (nicht unterstützt)
        if re.search(r'Kompetenzmatrix', line, re.IGNORECASE) or \
           (re.search(r'IK\s*[1-9]', line) and not has_4_columns):
            has_kompetenzmatrix = True
    
    # Entscheidungslogik
    if has_kompetenzmatrix:
        return None, ["Kompetenzmatrix-Format erkannt - nicht unterstützt"]
    
    if has_4_columns and has_ik_column:
        if has_lernsequenz_header:
            return "A", []
        else:
            return "B", ["Format B erkannt - Lernsequenzen ohne explizite Header"]
    
    # Fallback: wenn wir IK- und PK-Referenzen finden
    if has_ik_column and has_pk_column:
        return "B", ["Format B angenommen (keine Lernsequenz-Header gefunden)"]
    
    return None, ["Format konnte nicht eindeutig erkannt werden"]


def _extract_curriculum_structure(
    text_content: str,
    format_detected: str,
    fachplan_id: str,
    bp_version: str
) -> "CurriculumDraftData":
    """Extrahiert die Curriculum-Struktur aus dem Text.
    
    Vereinfachte Version ohne echtes LLM - in Produktion würde hier ein LLM-Aufruf
    die strukturierte Extraktion durchführen.
    """
    from app.context.schemas import CurriculumDraftData, CurriculumDraftKapitel, CurriculumDraftLernsequenz, CurriculumDraftEntry
    
    lines = text_content.split("\n")
    
    # Vereinfachte Extraktion für Demo/Testing
    # In Produktion: LLM-Prompt für strukturierte Extraktion
    
    # Suche nach Schul- und Fachinformationen in den ersten Zeilen
    schule = ""
    schulart = ""
    jahrgangsstufe = ""
    fach_code = ""
    fach = ""
    
    for line in lines[:20]:
        line = line.strip()
        # Schulname
        if re.search(r'(Schule|Gymnasium|Realschule|Grundschule|Gemeinschaftsschule)', line, re.IGNORECASE):
            schule = line
        # Schulart
        if re.search(r'\b(G8|G9|GMS|Realschule|Gymnasium|Berufliches Gymnasium)\b', line, re.IGNORECASE):
            schulart = line
        # Jahrgangsstufe
        match = re.search(r'\b(Klasse|Kl\.?|Jg\.?|Jahrgangsstufe)\s*(\d{1,2})', line, re.IGNORECASE)
        if match:
            jahrgangsstufe = match.group(2)
        # Fachcode
        match = re.search(r'\b(BW|DE|EN|FR|M|MA|PH|CH|BI|GE|GK|SP|RE|ETH|KU|MU|SPT)\b', line)
        if match:
            fach_code = match.group(1)
        # Fachname
        if re.search(r'\b(Mathematik|Deutsch|Englisch|Französisch|Physik|Chemie|Biologie|Gemeinschaftskunde|Geographie|Religion|Ethik|Kunst|Musik|Sport)\b', line, re.IGNORECASE):
            fach = line
    
    # Vereinfachte Kapitel-Extraktion
    # Suche nach Kapitel-Headern (typischerweise fett oder mit Stundenangabe)
    kapitel_list = []
    current_kapitel = None
    current_lernsequenz = None
    
    for line in lines[20:]:  # Skip header
        line = line.strip()
        if not line:
            continue
        
        # Kapitel-Header erkennen (z.B. "Kapitel 1: Titel" oder "1. Titel (X Stunden)")
        kapitel_match = re.match(
            r'^(?:Kapitel\s+\d+|\d+\.|\d+)\.?\s+(.+?)(?:\s+\(\d+\s*Stunden?\))?$',
            line,
            re.IGNORECASE
        )
        if kapitel_match:
            if current_kapitel:
                kapitel_list.append(current_kapitel)
            current_kapitel = CurriculumDraftKapitel(
                titel=kapitel_match.group(1).strip(),
                reihenfolge=len(kapitel_list) + 1,
                std=None,
                hinweis=None,
                konkretisierung=[],
                lernsequenzen=[],
                confidence=0.8,
                warnings=[]
            )
            current_lernsequenz = None
            continue
        
        # Lernsequenz-Header erkennen (fett in Spalte 3)
        ls_match = re.match(r'\*\*(.+?)\*\*|^(?:LS|Lernsequenz)\s+\d+\.?\s+(.+)$', line, re.IGNORECASE)
        if ls_match:
            ls_title = ls_match.group(1) or ls_match.group(2)
            if current_kapitel:
                if current_lernsequenz:
                    current_kapitel.lernsequenzen.append(current_lernsequenz)
                current_lernsequenz = CurriculumDraftLernsequenz(
                    bp_titel=ls_title.strip(),
                    bp_leitidee=None,
                    reihenfolge=len(current_kapitel.lernsequenzen) + 1,
                    eintraege=[],
                    confidence=0.7,
                    warnings=[]
                )
            continue
        
        # Tabellenzeilen (4 Spalten)
        parts = [p.strip() for p in re.split(r'[\t|]', line) if p.strip()]
        if len(parts) >= 4 and current_kapitel and current_lernsequenz:
            entry = CurriculumDraftEntry(
                ik=parts[1] if len(parts) > 1 and parts[1] else None,
                ik_partiell="[" in (parts[1] if len(parts) > 1 else ""),
                pk=[parts[0]] if len(parts) > 0 else [],
                konkretisierung=parts[2] if len(parts) > 2 else None,
                hinweise=parts[3] if len(parts) > 3 else None,
                lp=_extract_lp_codes(parts[3] if len(parts) > 3 else ""),
                confidence=0.6,
                warnings=[]
            )
            current_lernsequenz.eintraege.append(entry)
    
    # Letzte Elemente hinzufügen
    if current_lernsequenz and current_kapitel:
        current_kapitel.lernsequenzen.append(current_lernsequenz)
    if current_kapitel:
        kapitel_list.append(current_kapitel)
    
    return CurriculumDraftData(
        schule=schule or "Unbekannte Schule",
        fach_code=fach_code or "UNKNOWN",
        fach=fach or None,
        schulart=schulart or "G8",
        jahrgangsstufe=jahrgangsstufe or "5",
        fachplan_id=fachplan_id,
        bp_version=bp_version,
        vorwort=None,
        kapitel=kapitel_list
    )


def _extract_lp_codes(text: str) -> list[str]:
    """Extrahiert Leitperspektive-Codes aus Text."""
    # Muster: L BO, (L) BTV, LP-XX, etc.
    patterns = [
        r'\bL\s+[A-Z]{2,3}\b',  # L BO
        r'\(L\)\s+[A-Z]{2,4}',  # (L) BTV
        r'\bLP[-_]?[A-Z0-9]+\b',  # LP-XX
    ]
    codes = []
    for pattern in patterns:
        codes.extend(re.findall(pattern, text, re.IGNORECASE))
    return codes


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
