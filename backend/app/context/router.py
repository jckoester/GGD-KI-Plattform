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

from app.auth.dependencies import get_current_user, require_any_role, require_role
from app.auth.jwt import JwtPayload
from app.context.schemas import (
    ContextAnchorCreate,
    ContextAnchorRead,
    ContextEdgeRead,
    ContextEdgeCreate,
    ContextNodeCreate,
    ContextNodeRead,
    ContextNodeUpdate,
    ContextNodeTitleUpdate,
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
    BandRead,
    LeitideeRead,
    IkKompetenzRead,
    PkGruppeRead,
    PkKompetenzRead,
)
from app.context.editions import aktive_bp_version
from app.context.embedding import enqueue_embedding_job
from app.context.grades import parse_grade_band
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


async def _check_write_permission(
    node: ContextNode, user: JwtPayload, db: AsyncSession
) -> None:
    """403 wenn weder Admin noch Owner noch Gruppen-Lehrkraft (bei write_scope='group')."""
    if "admin" in user.roles:
        return
    if node.owner_pseudonym == user.sub:
        return
    if (
        node.write_scope == "group"
        and node.write_scope_group_id is not None
        and "teacher" in user.roles
    ):
        result = await db.execute(
            sa.select(sa.literal(1)).where(
                GroupMembership.group_id == node.write_scope_group_id,
                GroupMembership.pseudonym == user.sub,
                GroupMembership.role_in_group == "teacher",
            )
        )
        if result.scalar_one_or_none() is not None:
            return
    raise HTTPException(status_code=403, detail="Keine Berechtigung")


async def _check_read_permission(
    node: ContextNode, user: JwtPayload, db: AsyncSession
) -> None:
    """403 wenn der Knoten für die Nutzer:in nicht lesbar ist.

    `private` → **nur** Owner (auch Admins sehen fremde private Knoten NICHT — konsistent mit
    dem Listen-Filter `_read_scope_clause`); `group` → nur Gruppenmitglieder (Admin ausgenommen);
    `subject`/`school`/`global` → für alle eingeloggten Nutzer:innen lesbar. (Vorher prüfte der
    Lesepfad **nur** `private` → fremde group-Knoten waren per UUID lesbar/kopierbar — Audit #1.)
    """
    if node.owner_pseudonym == user.sub:
        return
    # Privat ist owner-only — bewusst VOR der Admin-Ausnahme, damit Admins fremde private
    # Knoten nicht lesen können (deckt sich mit `_read_scope_clause`, das private ausschließt).
    if node.read_scope == "private":
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    if "admin" in user.roles:
        return
    if node.read_scope == "group":
        if node.read_scope_group_id is None:
            raise HTTPException(status_code=403, detail="Keine Berechtigung")
        result = await db.execute(
            sa.select(sa.literal(1)).where(
                GroupMembership.group_id == node.read_scope_group_id,
                GroupMembership.pseudonym == user.sub,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail="Keine Berechtigung")


def _read_scope_clause(user: JwtPayload):
    """SQL-Klausel für die lesbaren Knoten (Liste/Nachbarschaft). Für Nicht-Admins werden
    `group`-Knoten auf die eigenen Gruppenmitgliedschaften eingeschränkt (Audit #1)."""
    if "admin" in user.roles:
        return or_(
            ContextNode.read_scope.in_(["global", "school", "subject", "group"]),
            ContextNode.owner_pseudonym == user.sub,
        )
    my_group_ids = (
        sa.select(GroupMembership.group_id)
        .where(GroupMembership.pseudonym == user.sub)
        .scalar_subquery()
    )
    return or_(
        ContextNode.read_scope.in_(["global", "school", "subject"]),
        ContextNode.owner_pseudonym == user.sub,
        and_(
            ContextNode.read_scope == "group",
            ContextNode.read_scope_group_id.in_(my_group_ids),
        ),
    )


def _check_curriculum_read_permission(tree: dict, user: JwtPayload) -> None:
    """Prüft Leseberechtigung anhand des tree-Dicts (read_scope + owner_pseudonym)."""
    read_scope = tree.get("read_scope", "school")
    if read_scope == "private":
        if tree.get("owner_pseudonym") != user.sub:
            raise HTTPException(status_code=403, detail="Keine Berechtigung")
    elif read_scope == "subject":
        if "student" in user.roles and "teacher" not in user.roles:
            if os.environ.get("CURRICULUM_VISIBLE_TO_STUDENTS", "false").lower() != "true":
                raise HTTPException(status_code=403, detail="Keine Berechtigung")


def _visibility_filter(query, user: JwtPayload, status_override: str | None = None):
    """Sichtbarkeitsfilter; status_override überschreibt den active-Default."""
    q = query.where(_read_scope_clause(user))
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
    subject_id: int | None = Query(default=None, description="Direkte Subject-ID-Filterung"),
    subject_id_or_global: int | None = Query(
        default=None,
        description="Knoten dieses Fachs ODER fach­unabhängige (subject_id IS NULL)",
    ),
    group_id: int | None = Query(default=None),
    grade: int | None = Query(default=None, ge=1, le=13, description="Jahrgangsstufe"),
    bp_version: str | None = Query(default=None, description="BP-Versionsfilter, z. B. '2016' oder '2016.V2'"),
    owner: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500, description="Maximale Anzahl Ergebnisse"),
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    query = select(ContextNode)
    query = _visibility_filter(query, user, status_override=status)

    # subject_id: direkte Filterung nach Subject-ID
    if subject_id is not None:
        query = query.where(ContextNode.subject_id == subject_id)

    # subject_id_or_global: dieses Fach plus fach­unabhängige Knoten (z. B. Vokabular)
    if subject_id_or_global is not None:
        query = query.where(
            or_(
                ContextNode.subject_id == subject_id_or_global,
                ContextNode.subject_id.is_(None),
            )
        )

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

    # bp_version: Bildungsplan-Versionsfilter (JSONB-Feld)
    if bp_version is not None:
        query = query.where(
            ContextNode.metadata_["bp_version"].astext == bp_version
        )

    # owner=me: nur eigene Knoten
    if owner is not None:
        if owner != "me":
            raise HTTPException(status_code=400, detail="owner muss 'me' sein")
        query = query.where(ContextNode.owner_pseudonym == user.sub)

    if q:
        like = f"%{q}%"
        # Titel ODER ein Synonym aus metadata_.aliase (JSONB-Textmatch). So sind
        # Aliase systemweit suchbar (Krücke bis zum echten Alias-Feld an Knoten).
        query = query.where(
            or_(
                ContextNode.title.ilike(like),
                ContextNode.metadata_["aliase"].astext.ilike(like),
            )
        )
    if category:
        query = query.where(ContextNode.category == category)
    if content_type:
        query = query.where(ContextNode.content_type.in_(content_type))

    query = query.order_by(ContextNode.created_at.desc())
    if limit is not None:
        query = query.limit(limit)

    result = await db.execute(query)
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
    await _check_read_permission(node, user, db)

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

    # Knoten laden + Sichtbarkeitsfilter anwenden (group-Knoten nur eigener Gruppen, Audit #1)
    nodes_query = select(ContextNode).where(
        ContextNode.id.in_(neighbor_ids),
        ContextNode.status == "active",
        _read_scope_clause(user),
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
    await _check_read_permission(node, user, db)

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
    # Nur lesbare Quellknoten dürfen kopiert werden (sonst Exfiltration per UUID, Audit #1).
    await _check_read_permission(source, user, db)

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
    await _check_read_permission(node, user, db)
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
        # Autorenschaft immer serverseitig aus dem JWT — kein Client-Override (Audit #1).
        owner_pseudonym=user.sub,
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
    await _check_write_permission(node, user, db)

    update_data = payload.model_dump(exclude_unset=True, by_alias=False)
    for field, value in update_data.items():
        # metadata_ → DB-Spalte 'metadata'
        attr = field if field != "metadata_" else "metadata_"
        setattr(node, attr, value)

    # Manuelle Titeländerung sperrt den Titel gegen einen BP-Re-Import (C1).
    if "title" in update_data:
        node.title_locked = True

    await db.commit()
    await db.refresh(node)
    return node


@router.patch("/nodes/{node_id}/title", response_model=ContextNodeRead)
async def update_node_title(
    node_id: UUID,
    payload: ContextNodeTitleUpdate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(require_role("admin")),
):
    """Korrigiert NUR den Titel eines (importierten) BP-Knotens und sperrt ihn gegen den
    Re-Import (C1). Admin-only — die BP-Curriculum-Daten sind schulweit/global."""
    node = await db.get(ContextNode, node_id)
    if node is None or node.status == "deleted":
        raise HTTPException(status_code=404, detail="Knoten nicht gefunden")
    node.title = payload.title
    node.title_locked = True
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
    await _check_write_permission(node, user, db)

    # Rekursiv alle untergeordneten Knoten einsammeln: Kinder zeigen per
    # 'part_of'-Kante (from_node = Kind, to_node = Elternteil) auf ihr Elternteil.
    # So wird z. B. ein ganzes Curriculum (Curriculum → Kapitel → Lernsequenz)
    # in einem Rutsch gelöscht, statt verwaiste Knoten zu hinterlassen. Die
    # Kanten selbst verschwinden über ON DELETE CASCADE der FK-Constraints.
    to_delete: set[UUID] = {node_id}
    frontier: list[UUID] = [node_id]
    while frontier:
        current = frontier.pop()
        child_rows = await db.execute(
            sa.select(ContextEdge.from_node_id).where(
                ContextEdge.to_node_id == current,
                ContextEdge.relation == "part_of",
            )
        )
        for (child_id,) in child_rows:
            if child_id not in to_delete:
                to_delete.add(child_id)
                frontier.append(child_id)

    for nid in to_delete:
        n = await db.get(ContextNode, nid)
        if n is not None:
            await db.delete(n)
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

    # Sichtbarkeit prüfen (kein privater/fremd-gruppen Knoten, Audit #1)
    await _check_read_permission(node, user, db)

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


@router.get("/curricula/{curriculum_id}/export")
async def export_curriculum(
    curriculum_id: UUID,
    format: str = Query("yaml", pattern="^(yaml|pdf)$"),
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(get_current_user),
):
    """Exportiert ein Curriculum als YAML oder PDF."""
    from app.context.service import load_curriculum_tree
    from app.context.curriculum_export import build_curriculum_export_dict, render_curriculum_pdf

    tree = await load_curriculum_tree(db, curriculum_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Curriculum nicht gefunden oder inaktiv")

    _check_curriculum_read_permission(tree, user)

    meta = tree.get("metadata", {})
    fach_code = meta.get("fach_code", "curriculum")
    jg = meta.get("jahrgangsstufe", "")
    from datetime import date
    date_str = date.today().isoformat()
    filename_base = f"curriculum_{fach_code}_{jg}_{date_str}".replace(" ", "_")

    if format == "yaml":
        import yaml
        from fastapi.responses import Response
        export_dict = await build_curriculum_export_dict(db, tree)
        yaml_text = yaml.safe_dump(export_dict, allow_unicode=True, sort_keys=False)
        return Response(
            content=yaml_text.encode("utf-8"),
            media_type="application/x-yaml",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.yaml"'},
        )
    else:
        from fastapi.responses import Response
        pdf_bytes = await render_curriculum_pdf(db, tree)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.pdf"'},
        )


@router.get("/curricula/{curriculum_id}", response_model=CurriculumRead)
async def get_curriculum(
    curriculum_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(get_current_user),
):
    """Gibt das vollständige Curriculum als verschachteltes Objekt zurück."""
    from app.context.service import load_curriculum_tree

    tree = await load_curriculum_tree(db, curriculum_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Curriculum nicht gefunden oder inaktiv")

    _check_curriculum_read_permission(tree, user)

    # Prüfe ob User editieren darf
    can_edit = False
    if "admin" in user.roles:
        can_edit = True
    elif tree.get("write_scope_group_id"):
        result = await db.execute(
            sa.select(1).where(
                sa.exists().where(
                    GroupMembership.group_id == tree["write_scope_group_id"],
                    GroupMembership.pseudonym == user.sub,
                )
            )
        )
        can_edit = result.scalar_one_or_none() is not None

    return {
        "id": tree["id"],
        "title": tree["title"],
        "metadata": tree["metadata"],
        "subject_id": tree["subject_id"],
        "write_scope_group_id": tree["write_scope_group_id"],
        "kapitel": tree["kapitel"],
        "can_edit": can_edit,
    }


@router.post("/curricula/{curriculum_id}/relink")
async def relink_curriculum_endpoint(
    curriculum_id: UUID,
    apply: bool = Query(default=False, description="false=Vorschau, true=anwenden"),
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(get_current_user),
):
    """Aktualisiert ein Curriculum auf die aktuelle Bildungsplan-Edition.

    ``apply=false`` liefert die Vorschau (Modus + je Kompetenz relink/outdated/current);
    ``apply=true`` wendet an — in-place, oder bei gespaltenem Jahrgangsband als migrierte
    **Kopie** (Original bleibt). Recht wie Curriculum-Bearbeitung: Admin oder Mitglied der
    ``write_scope_group``.
    """
    from app.context.relink import relink_curriculum

    if "teacher" not in user.roles and "admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Nur für Lehrkräfte/Admins")

    cur = await db.get(ContextNode, curriculum_id)
    if cur is None or cur.content_type != "curriculum" or cur.status != "active":
        raise HTTPException(status_code=404, detail="Curriculum nicht gefunden")

    if "admin" not in user.roles:
        allowed = False
        if cur.write_scope_group_id is not None:
            r = await db.execute(
                sa.select(1).where(sa.exists().where(
                    GroupMembership.group_id == cur.write_scope_group_id,
                    GroupMembership.pseudonym == user.sub,
                ))
            )
            allowed = r.scalar_one_or_none() is not None
        if not allowed:
            raise HTTPException(status_code=403, detail="Keine Berechtigung zum Bearbeiten dieses Curriculums")

    result = await relink_curriculum(db, curriculum_id, apply)
    if result is None:
        raise HTTPException(status_code=404, detail="Curriculum nicht gefunden")
    return result


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
    
    # Sichtbarkeitsprüfung (privat/fremd-gruppen ausgeschlossen, Audit #1)
    await _check_read_permission(node, user, db)

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
    from app.context.service import (
        get_subject_department_group_id,
        is_subject_department_member,
    )
    import uuid as _uuid

    # Fachplan laden per Node-UUID — Pflicht (subject_id wird von dort abgeleitet)
    try:
        fachplan_uuid = _uuid.UUID(payload.fachplan_node_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="fachplan_node_id ist keine gültige UUID")
    fachplan_node = await db.get(ContextNode, fachplan_uuid)
    if not fachplan_node or fachplan_node.content_type != "fachplan" or fachplan_node.status != "active":
        raise HTTPException(
            status_code=422,
            detail=f"Für Fach {payload.fach_code} / BP-Version {payload.bp_version} ist kein Bildungsplan importiert",
        )

    subject_id = fachplan_node.subject_id
    if not subject_id:
        raise HTTPException(
            status_code=422,
            detail=f"Fachplan nicht mit einem Fach verknüpft — bitte Bildungsplan neu importieren",
        )

    # Fachschafts-Gruppen-ID (deterministisch) — für write_scope_group_id unten.
    department_group_id = await get_subject_department_group_id(db, subject_id)

    # Fachschafts-Zugehörigkeit prüfen: Mitgliedschaft in IRGENDEINER
    # subject_department-Gruppe des Fachs (robust gegen Alt-/Doppelgruppen mit
    # abweichender sso_group_id). Existiert für das Fach gar keine Fachschaft,
    # wird nicht geprüft (Verhalten wie bisher). Admins sind ausgenommen.
    if department_group_id is not None and "admin" not in user.roles:
        if not await is_subject_department_member(db, subject_id, user.sub):
            raise HTTPException(
                status_code=403,
                detail="Keine Berechtigung - Sie müssen Mitglied der Fachschaft sein"
            )

    # Idempotenz: bestehenden aktiven Knoten zurückliefern
    import_key = f"new_{user.sub}_{payload.fach_code}_{payload.jahrgangsstufe}_{payload.bp_version}"
    existing = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.metadata_["import_key"].astext == import_key,
            ContextNode.status == "active",
        ).limit(1)
    )
    existing_node = existing.scalar_one_or_none()
    if existing_node:
        return existing_node

    cur_min_grade, cur_max_grade = parse_grade_band(payload.jahrgangsstufe)
    curriculum = ContextNode(
        category="knowledge",
        content_type="curriculum",
        title=f"{payload.fach_code} Kl. {payload.jahrgangsstufe}",
        content=None,
        read_scope="school",
        write_scope="subject",
        write_scope_group_id=department_group_id,
        subject_id=subject_id,
        min_grade=cur_min_grade,
        max_grade=cur_max_grade,
        owner_pseudonym=user.sub,
        metadata_={
            # Geschäftsschlüssel des Bildungsplans — konsistent mit dem Import-Pfad
            # (service.import_curriculum schreibt dasselbe Feld). Kann fehlen, wenn
            # der Fachplan-Knoten keinen trägt.
            "fachplan_id": (fachplan_node.metadata_ or {}).get("fachplan_id"),
            # Node-UUID des Fachplans (Primärschlüssel) — redundant zur part_of-Kante,
            # aber praktisch für direkte Lookups ohne Kanten-Query.
            "fachplan_node_id": str(fachplan_node.id),
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
    edge = ContextEdge(
        from_node_id=curriculum.id,
        to_node_id=fachplan_node.id,
        relation="part_of",
        metadata_={},
    )
    db.add(edge)
    await db.commit()
    
    return curriculum


# ── Fach-Code Lookup ─────────────────────────────────────────────────────────


@router.get("/subjects/by-code/{fach_code}")
async def get_subject_by_fach_code(
    fach_code: str,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Löst einen Fach-Code (z.B. 'M', 'CH', 'ETH') zu subject_id und subject_slug auf.

    Match über die Spalte subjects.fach_code (aus config/subjects.yaml geseedet),
    case-insensitiv normalisiert auf Großschreibung — NICHT über den Slug.
    """
    row = await db.execute(
        sa.select(Subject.id, Subject.slug)
        .where(Subject.fach_code == fach_code.strip().upper())
        .limit(1)
    )
    result = row.fetchone()
    if not result:
        raise HTTPException(status_code=404, detail=f"Kein Fach mit fach_code '{fach_code}' gefunden")
    return {"subject_id": result[0], "subject_slug": result[1]}


# ── Bildungsplan Hierarchie Endpoint ────────────────────────────────────────


def _band_label(min_g: int, max_g: int, niveau: str) -> str:
    grade = f"Kl. {min_g}" if min_g == max_g else f"Kl. {min_g}–{max_g}"
    suffix = {"basis": " · Basis", "leistung": " · Leistung"}.get(niveau, "")
    return grade + suffix


@router.get("/subjects/{subject_id}/active-bp-version")
async def get_active_bp_version(
    subject_id: int,
    grade: int = Query(..., ge=1, le=13, description="Jahrgangsstufe"),
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(get_current_user),
):
    """Berechnet die für (Fach, Stufe, aktuelles Schuljahr) geltende ``bp_version``.

    Verbindet den Editions-Fahrplan (``subjects.yaml``) + Schuljahr
    (``school_year.yaml``) mit dem tatsächlich importierten Editionsbestand des
    Fachs. Für editionsbewusste Editor-Filter (IK-Autocomplete): die zurückgegebene
    ``bp_version`` ist der Filterwert für die Knotensuche; ``null`` = Fach hat keine
    versionierten Knoten → nicht filtern.
    """
    _bp = ContextNode.metadata_["bp_version"].astext
    rows = await db.execute(
        sa.select(_bp)
        .where(
            ContextNode.subject_id == subject_id,
            ContextNode.status == "active",
            _bp.isnot(None),
            _bp != "",
        )
        .distinct()
    )
    available = sorted({r[0] for r in rows.all() if r[0]})
    return {
        "bp_version": aktive_bp_version(grade, set(available)),
        "available": available,
    }


@router.get("/fachplan/by-subject/{subject_id}", response_model=FachplanTreeRead)
async def get_fachplan_by_subject(
    subject_id: int,
    min_grade: int | None = None,
    max_grade: int | None = None,
    niveau: str | None = None,
    bp_version: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(get_current_user),
):
    """Gibt die Bildungsplan-Hierarchie für ein Fach als verschachteltes Objekt zurück.

    Unterstützt mehrere Fachpläne pro Fach (verschiedene BP-Editionen). Wählt über
    bp_version gezielt eine Edition; ohne bp_version wird die aktuellste genommen.
    Filtert Leitideen/IK/PK nach Band (min_grade, max_grade, niveau).
    """
    # ── Verfügbare (aktive) BP-Versionen für dieses Fach ──────────────────────
    _bp_ver_col = ContextNode.metadata_["bp_version"].astext.label("bp_version")
    vers_result = await db.execute(
        sa.select(_bp_ver_col)
        .where(
            ContextNode.content_type == "fachplan",
            ContextNode.subject_id == subject_id,
            ContextNode.status == "active",
        )
        .distinct()
        .order_by(_bp_ver_col)
    )
    available_versions = [r[0] for r in vers_result.all() if r[0]]

    # ── Default-Edition aus Fahrplan + Schuljahr berechnen ────────────────────
    # Ohne explizite bp_version und mit Stufenbezug (min_grade) wählt die
    # schuljahresabhängige Frontier die geltende Edition; sonst bleibt es bei der
    # neuesten aktiven (Verhalten wie bisher). Vor V3 ein No-Op (Frontier = V2).
    if not bp_version and min_grade is not None and available_versions:
        bp_version = aktive_bp_version(min_grade, set(available_versions)) or bp_version

    # ── Fachplan laden (mehr-versionsfest) ────────────────────────────────────
    q = (
        sa.select(ContextNode)
        .where(
            ContextNode.content_type == "fachplan",
            ContextNode.subject_id == subject_id,
            ContextNode.status == "active",
        )
        .order_by(ContextNode.updated_at.desc())
    )
    if bp_version:
        q = q.where(ContextNode.metadata_["bp_version"].astext == bp_version)

    result = await db.execute(q.limit(1))
    fachplan_node = result.scalar_one_or_none()

    if not fachplan_node:
        return FachplanTreeRead(fachplan=None, leitideen=[], pk_gruppen=[], can_edit=False)

    # ── Band-Liste (DISTINCT über direkte Leitideen des Fachplans) ────────────
    bands_result = await db.execute(
        sa.select(ContextNode.min_grade, ContextNode.max_grade, ContextNode.niveau)
        .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(
            ContextEdge.to_node_id == fachplan_node.id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "leitidee",
            ContextNode.status == "active",
            ContextNode.min_grade.isnot(None),
        )
        .distinct()
        .order_by(ContextNode.min_grade, ContextNode.niveau)
    )
    bands = [
        BandRead(
            min_grade=r.min_grade,
            max_grade=r.max_grade,
            niveau=r.niveau,
            label=_band_label(r.min_grade, r.max_grade, r.niveau),
        )
        for r in bands_result.all()
    ]

    # Default-Band: erstes aus der Liste wenn keines übergeben
    if min_grade is None and bands:
        selected = bands[0]
        min_grade = selected.min_grade
        max_grade = selected.max_grade
        niveau = selected.niveau
    elif min_grade is not None:
        selected = next(
            (b for b in bands if b.min_grade == min_grade
             and b.max_grade == max_grade and b.niveau == (niveau or "regulär")),
            bands[0] if bands else None,
        )
    else:
        selected = None

    # ── Rekursiver Leitideen-Baum ─────────────────────────────────────────────
    async def _build_leitidee_subtree(parent_node: ContextNode) -> LeitideeRead:
        # IK-Kinder laden, nach Band gefiltert
        ik_q = (
            sa.select(ContextNode)
            .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
            .where(
                ContextEdge.to_node_id == parent_node.id,
                ContextEdge.relation == "part_of",
                ContextNode.content_type == "ik_kompetenz",
                ContextNode.status == "active",
            )
            .order_by(
                sa.cast(ContextNode.metadata_["standard_nr"], sa.Integer).asc(),
                ContextNode.title,
            )
        )
        if min_grade is not None:
            ik_q = ik_q.where(
                ContextNode.min_grade == min_grade,
                ContextNode.max_grade == max_grade,
                ContextNode.niveau == (niveau or "regulär"),
            )
        ik_result = await db.execute(ik_q)
        ik_nodes = ik_result.scalars().all()

        ik_list = [
            IkKompetenzRead(
                id=n.id,
                title=n.title,
                min_grade=n.min_grade,
                max_grade=n.max_grade,
                niveau=n.niveau,
                metadata_=n.metadata_,
            )
            for n in ik_nodes
        ]

        # Unter-Leitideen laden, nach Band gefiltert
        unter_q = (
            sa.select(ContextNode)
            .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
            .where(
                ContextEdge.to_node_id == parent_node.id,
                ContextEdge.relation == "part_of",
                ContextNode.content_type == "leitidee",
                ContextNode.status == "active",
            )
            .order_by(ContextNode.title)
        )
        if min_grade is not None:
            unter_q = unter_q.where(
                ContextNode.min_grade == min_grade,
                ContextNode.max_grade == max_grade,
                ContextNode.niveau == (niveau or "regulär"),
            )
        unter_result = await db.execute(unter_q)
        unter_nodes = unter_result.scalars().all()

        unter_list = [await _build_leitidee_subtree(n) for n in unter_nodes]

        return LeitideeRead(
            id=parent_node.id,
            title=parent_node.title,
            content=parent_node.content or None,
            min_grade=parent_node.min_grade,
            max_grade=parent_node.max_grade,
            niveau=parent_node.niveau,
            metadata_=parent_node.metadata_,
            ik_kompetenzen=ik_list,
            unter_leitideen=unter_list,
        )

    # Oberste Leitideen (direkte Kinder des Fachplans)
    top_ld_q = (
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
    if min_grade is not None:
        top_ld_q = top_ld_q.where(
            ContextNode.min_grade == min_grade,
            ContextNode.max_grade == max_grade,
            ContextNode.niveau == (niveau or "regulär"),
        )
    top_ld_result = await db.execute(top_ld_q)
    top_leitideen = top_ld_result.scalars().all()

    leitideen_list = [await _build_leitidee_subtree(n) for n in top_leitideen]

    # ── PK-Gruppen ────────────────────────────────────────────────────────────
    pk_gruppen_q = (
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
    pk_gruppen_result = await db.execute(pk_gruppen_q)
    pk_gruppen_nodes = pk_gruppen_result.scalars().all()

    pk_gruppen_list = []
    for pg_node in pk_gruppen_nodes:
        pk_q = (
            sa.select(ContextNode)
            .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
            .where(
                ContextEdge.to_node_id == pg_node.id,
                ContextEdge.relation == "part_of",
                ContextNode.content_type == "pk_kompetenz",
                ContextNode.status == "active",
            )
            .order_by(
                sa.cast(ContextNode.metadata_["standard_nr"], sa.Integer).asc(),
                ContextNode.title,
            )
        )
        pk_result = await db.execute(pk_q)
        pk_list = [
            PkKompetenzRead(id=n.id, title=n.title, metadata_=n.metadata_)
            for n in pk_result.scalars().all()
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
        can_edit=False,
        bands=bands,
        selected_band=selected,
        bp_version=fachplan_node.metadata_.get("bp_version", ""),
        available_versions=available_versions,
    )


