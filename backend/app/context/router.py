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
    anzeige_felder,
    ContextSearchRequest,
    SearchEnvelope,
    CurriculumRead,
    CurriculumMetaUpdate,
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
from app.context.filters import Knotenfilter, wende_an
from app.context.visibility import read_scope_clause
from app.preferences.service import anzeige_limit
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
    """SQL-Klausel für die lesbaren Knoten (Liste/Nachbarschaft).

    Die Regel selbst steht in :mod:`app.context.visibility` — sie gilt auch für die
    Suchschicht, und zwei Kopien einer Rechteprüfung driften auseinander (siehe dort).
    """
    return read_scope_clause(user.sub, user.roles)


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


async def _require_curriculum_write(
    db: AsyncSession, curriculum_id: UUID, user: JwtPayload
) -> ContextNode:
    """Schreibrecht am Curriculum prüfen und den Knoten zurückgeben.

    Admin darf immer, sonst muss die Person Mitglied der `write_scope_group` sein — das
    ist die Fachschaft. Bis auf diese Stelle stand dieselbe Prüfung noch einmal wortgleich
    im Relink-Endpunkt; zwei Kopien einer Rechteprüfung driften irgendwann auseinander,
    und die Richtung, in die sie driften, merkt man erst zu spät.
    """
    if "teacher" not in user.roles and "admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Nur für Lehrkräfte/Admins")

    node = await db.get(ContextNode, curriculum_id)
    if node is None or node.content_type != "curriculum" or node.status != "active":
        raise HTTPException(status_code=404, detail="Curriculum nicht gefunden")

    if "admin" in user.roles:
        return node

    allowed = False
    if node.write_scope_group_id is not None:
        r = await db.execute(
            sa.select(1).where(
                sa.exists().where(
                    GroupMembership.group_id == node.write_scope_group_id,
                    GroupMembership.pseudonym == user.sub,
                )
            )
        )
        allowed = r.scalar_one_or_none() is not None
    if not allowed:
        raise HTTPException(
            status_code=403, detail="Keine Berechtigung zum Bearbeiten dieses Curriculums"
        )
    return node


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
    exclude_content_type: list[str] | None = Query(
        default=None,
        description="content_types, die ausgeschlossen werden (z. B. BP-Curriculum-Typen "
                    "in der freien /knowledge-Liste). NULL-Typen bleiben erhalten.",
    ),
    limit: int | None = Query(default=None, ge=1, le=500, description="Maximale Anzahl Ergebnisse"),
    offset: int | None = Query(default=None, ge=0, description="Versatz für Pagination"),
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    if owner is not None and owner != "me":
        raise HTTPException(status_code=400, detail="owner muss 'me' sein")

    # Die Feldfilter stehen in `app.context.filters` — dieselbe Übersetzung benutzt die
    # Aufzählung der Suchschicht (ADR-017). Zwei Fassungen derselben Bedingungen gäben
    # irgendwann verschiedene Antworten auf dieselbe Frage.
    query = _visibility_filter(select(ContextNode), user, status_override=status)
    query = wende_an(query, Knotenfilter(
        q=q,
        category=category,
        content_type=tuple(content_type or ()),
        exclude_content_type=tuple(exclude_content_type or ()),
        subject_id=subject_id,
        subject_id_or_global=subject_id_or_global,
        subject_slug=subject_slug,
        group_id=group_id,
        grade=grade,
        bp_version=bp_version,
        owner_pseudonym=user.sub if owner == "me" else None,
    ))

    # id als stabiler Tiebreaker → deterministische Reihenfolge für Pagination
    # (created_at allein hat bei gleichzeitig importierten/geseedeten Knoten viele Ties).
    query = query.order_by(ContextNode.created_at.desc(), ContextNode.id)
    if offset is not None:
        query = query.offset(offset)
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

    # Die Bildungsplan-Edition eines Curriculums ist kein Etikett: Sie bestimmt, gegen
    # welche Edition die IK-/PK-Verweise aufgelöst wurden. Über diesen generischen Weg
    # ließe sie sich mitsamt dem ganzen Metadaten-Dict überschreiben — die Verweise zeigten
    # danach still auf Knoten, die es in der neuen Edition anders oder gar nicht gibt.
    # Der geprüfte Weg ist `POST /curricula/{id}/relink`.
    if node.content_type == "curriculum" and "metadata_" in update_data:
        alt = (node.metadata_ or {}).get("bp_version")
        neu = (update_data["metadata_"] or {}).get("bp_version")
        if neu != alt:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Die Bildungsplan-Edition eines Curriculums lässt sich hier nicht "
                    "ändern. Nutzen Sie „Auf neue Edition aktualisieren“ (relink)."
                ),
            )

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
        sa.select(ContextNode, ChatContextNode.added_at)
        .join(ChatContextNode, ChatContextNode.node_id == ContextNode.id)
        .where(
            ChatContextNode.chat_id == conversation_id,
            ContextNode.status == "active",
        )
        .order_by(ChatContextNode.added_at)
    )
    return [
        ChatContextNodeRead(
            node_id=node.id,
            category=node.category,
            title=node.title,
            content_type=node.content_type,
            added_at=added_at,
            **anzeige_felder(node),
        )
        for node, added_at in result.all()
    ]


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
            **anzeige_felder(node),
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
        **anzeige_felder(node),
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


@router.post("/search", response_model=SearchEnvelope)
async def search_context_nodes(
    request: ContextSearchRequest,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(get_current_user),
):
    """Suche über sichtbare Knoten anhand eines Freitexts — als Ergebnisumschlag.

    Zwei Aufruferprofile teilen sich diesen Endpunkt:

    * **Vorschlagsfenster** (Suchknopf im Chat) — Identifikation und thematische Auswahl
      mit der Anzeigezahl aus dem Nutzerprofil. Dort ist die Trefferzahl eine Platzfrage.
    * **Suchseite** — dieselben Abschnitte großzügiger, plus die **Aufzählung**, sobald
      eine Facette gesetzt ist. Dann lautet die Frage „alle, die …", und darauf gehört
      eine Zahl statt einer stillschweigend gekürzten Liste.

    Die Facetten verfeinern das Ergebnis, sie sind keine Vorbedingung: Ohne sie liefert
    die Suchseite dasselbe wie der Suchknopf.
    """
    from app.chat.router import subject_of_conversation
    from app.context.filters import Knotenfilter
    from app.context.search import Suchprofil, aufzaehlung, suche

    # Ohne eigene Angabe die Anzeigezahl aus dem Nutzerprofil (Vorschlagsfenster).
    limit = request.limit or await anzeige_limit(db, user.sub)

    # Fachbezug nur aus einer Konversation, die der/die Suchende auch sehen darf — sonst
    # verriete die Trefferreihenfolge etwas über fremde Konversationen.
    subject_id = None
    if request.conversation_id is not None:
        conv = await db.get(Conversation, request.conversation_id)
        if conv is not None and conv.pseudonym == user.sub:
            subject_id = await subject_of_conversation(db, request.conversation_id)

    # Reihenfolge der Quellen: die Facette (sie filtert ohnehin), dann die gespeicherte
    # Konversation, zuletzt das Fach eines noch ungespeicherten Chats. Der letzte Fall
    # braucht keine Rechteprüfung — die Zahl kommt aus dem eigenen Browser und wirkt nur
    # auf die Sortierung; sichtbar wird dadurch kein Knoten, der es nicht ohnehin wäre.
    profil = Suchprofil(
        pseudonym=user.sub,
        rollen=user.roles,
        subject_id=request.subject_id or subject_id or request.conversation_subject_id,
        identifikation=limit,
        thematisch=limit,
        aufzaehlung=limit,
        grade=request.grade,
    )
    ergebnis = await suche(
        request.query, profil, db, nur_identifikation=request.identification_only
    )

    facetten = Knotenfilter(
        content_type=tuple(request.content_type or ()),
        subject_id=request.subject_id,
        grade=request.grade,
    )
    if request.content_type or request.subject_id or request.grade:
        ergebnis.aufzaehlung = await aufzaehlung(
            facetten, profil, db, gruppierung="fach"
        )

    return ergebnis


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


@router.patch("/curricula/{curriculum_id}", response_model=CurriculumRead)
async def update_curriculum_meta(
    curriculum_id: UUID,
    payload: CurriculumMetaUpdate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(get_current_user),
):
    """Titel und Jahrgangsband eines Curriculums ändern.

    Mehr geht hier bewusst nicht. Insbesondere bleibt `bp_version` unangetastet: Sie
    entscheidet, gegen welche Bildungsplan-Edition die IK-/PK-Verweise aufgelöst wurden,
    und ist deshalb kein Etikett, sondern Teil der Datenstruktur. Der geprüfte Weg auf eine
    neue Edition ist `POST /curricula/{id}/relink`.
    """
    from app.context.grades import parse_grade_band

    node = await _require_curriculum_write(db, curriculum_id, user)
    aenderungen = payload.model_dump(exclude_unset=True)

    if payload.title is not None:
        node.title = payload.title.strip()

    if payload.jahrgangsstufe is not None:
        neu = payload.jahrgangsstufe.strip()
        alt = (node.metadata_ or {}).get("jahrgangsstufe", "")
        if neu != alt:
            # Metadaten **zusammenführen**, nicht ersetzen: Ein neues Dict zuzuweisen
            # verlöre fach_code, fachplan_id, schulart — und bp_version.
            node.metadata_ = {**(node.metadata_ or {}), "jahrgangsstufe": neu}
            # Das Band ist auch strukturell hinterlegt (Editionsauflösung, Fachfilter).
            node.min_grade, node.max_grade = parse_grade_band(neu)
            await _import_keys_umschreiben(db, node, alt, neu)

    if aenderungen:
        await db.commit()

    from app.context.service import load_curriculum_tree

    tree = await load_curriculum_tree(db, curriculum_id)
    return {
        "id": tree["id"],
        "title": tree["title"],
        "metadata": tree["metadata"],
        "subject_id": tree["subject_id"],
        "write_scope_group_id": tree["write_scope_group_id"],
        "kapitel": tree["kapitel"],
        "can_edit": True,
    }


async def _import_keys_umschreiben(
    db: AsyncSession, node: ContextNode, alt: str, neu: str
) -> None:
    """`import_key` des Curriculums und seiner Kapitel/Lernsequenzen nachziehen.

    Warum das sein muss: Der Schlüssel enthält das Jahrgangsband und dient dem Anlegepfad
    als Idempotenz- bzw. Dublettenschlüssel. Bliebe er nach einer Umbenennung stehen,
    entstünde ein stiller Konflikt — wer später ein Curriculum für das **alte** Band
    anlegt, träfe auf dieses umbenannte hier und überschriebe es.

    ⚠️ **Es gibt zwei Schlüsselformate**, weil es zwei Anlegepfade gibt:

    * ``{fachplan_id}_{band}`` — `import_curriculum_from_draft` (YAML-/CLI-Import),
      Kapitel und Lernsequenzen hängen ihre Nummern hinten an;
    * ``new_{pseudonym}_{fach_code}_{band}_{bp_version}`` — `POST /curricula/new`, der Weg
      der Oberfläche. Hier steht das Band **in der Mitte**, und die Kapitel entstehen erst
      später im Editor und tragen gar keinen Schlüssel.

    Deshalb wird das Band als ganzes Segment zwischen Unterstrichen ersetzt, statt einen
    Präfix aus `fachplan_id` zu rekonstruieren: Das trägt beide Formate. Die Kinder werden
    anschließend über den **alten Schlüssel des Curriculums** als Präfix gefunden.
    """
    alt_schluessel = (node.metadata_ or {}).get("import_key") or ""
    if not alt_schluessel or not alt:
        return

    segmente = alt_schluessel.split("_")
    if alt not in segmente:
        # Unbekanntes Format — lieber nichts anfassen als etwas Falsches umschreiben.
        logger.warning(
            "import_key %r enthält das Band %r nicht als Segment — nicht umgeschrieben.",
            alt_schluessel, alt,
        )
        return
    neu_schluessel = "_".join(neu if s == alt else s for s in segmente)

    node.metadata_ = {**(node.metadata_ or {}), "import_key": neu_schluessel}

    # Kinder: bewusst in Python statt als UPDATE mit LIKE — `_` ist in LIKE ein
    # Platzhalter für ein beliebiges Zeichen, und die Schlüssel stecken voller
    # Unterstriche; ein LIKE-Präfix träfe damit auch fremde Curricula. Die Knotenzahl je
    # Curriculum ist klein.
    treffer = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type.in_(["kapitel", "lernsequenz"]),
            ContextNode.status == "active",
            ContextNode.metadata_["import_key"].isnot(None),
        )
    )
    for kind in treffer.scalars().all():
        schluessel = (kind.metadata_ or {}).get("import_key") or ""
        if not schluessel.startswith(f"{alt_schluessel}_"):
            continue
        kind.metadata_ = {
            **(kind.metadata_ or {}),
            "import_key": neu_schluessel + schluessel[len(alt_schluessel) :],
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

    await _require_curriculum_write(db, curriculum_id, user)

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


# ── Curriculum aus vollständigem Entwurf anlegen: ENTFERNT ──────────────────
#
# Hier stand `POST /curricula` (`create_curriculum`). Entfernt am 2026-08-08, weil der
# Endpunkt drei Eigenschaften auf einmal hatte:
#
#  * **Er schrieb nichts.** Weder er noch `import_curriculum_from_draft` noch `get_db`
#    haben committet — die Session wurde ohne Commit geschlossen, also verworfen. Der
#    Aufrufer bekam eine 201 mit vollständigem Curriculum zurück, in der Datenbank stand
#    nichts.
#  * **Ihn rief niemand auf.** `createCurriculumFromDraft` in `api.js` gab es zwar, aber
#    keine Seite benutzte sie, und kein Test deckte den Endpunkt ab. Deshalb ist das nie
#    aufgefallen.
#  * **Es gab ihn doppelt.** Denselben Weg — vollständiger Entwurf rein, Curriculum raus —
#    geht `scripts/import_curriculum.py`, bewusst als Admin-Vorgang auf der Kommandozeile
#    (`docs/runbooks/curriculum-transfer.md`).
#
# Ein Commit nachzureichen hätte einen ungenutzten Schreibpfad tief in den Wissensgraph
# wiederbelebt, den jede Lehrkraft hätte aufrufen können. Wird ein Import über die
# Oberfläche gewünscht, gehört er neu entworfen — mit Vorschau, Rechteprüfung und
# Konfliktanzeige —, nicht aus diesem Stumpf wiederhergestellt.
#
# Unberührt: `POST /curricula/new` (leeres Curriculum) und danach der Editor — der Weg,
# den die Oberfläche tatsächlich geht.


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


