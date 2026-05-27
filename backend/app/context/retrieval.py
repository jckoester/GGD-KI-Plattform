"""Retrieval-Funktionen fuer den Kontextspeicher (KS-Phase-3)."""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.embedding import generate_embedding
from app.db.models import ContextNode

# Nur strukturell sinnvolle Einstiegspunkte als retrieval_scope zulässig
VALID_SCOPE_ANCHOR_TYPES: frozenset[str] = frozenset({
    "fachplan", "leitidee", "pk_gruppe", "curriculum", "themengebiet",
    "unterrichtseinheit", "unterrichtsstunde",
})


_SCOPE_CTE = """
WITH RECURSIVE descendants AS (
    SELECT id FROM context_nodes
    WHERE id = ANY(:anchor_ids) AND status = 'active'
    UNION ALL
    SELECT e.from_node_id
    FROM context_edges e
    JOIN descendants d ON e.to_node_id = d.id
    WHERE e.relation = 'part_of'
),
referenced AS (
    SELECT e.to_node_id AS id
    FROM context_edges e
    WHERE e.from_node_id = ANY(:anchor_ids)
      AND e.relation IN ('references', 'develops')
),
scope AS (
    SELECT id FROM descendants
    UNION
    SELECT id FROM referenced
)
"""


async def get_semantic_context(
    anchor_ids: list[UUID],
    query_text: str,
    pseudonym: str,
    db: AsyncSession,
    top_k: int = 10,
) -> list[ContextNode]:
    """Semantische Suche im durch anchor_ids definierten Scope-Subgraphen.

    Gibt leere Liste zurueck wenn keine Anker oder kein Embedding vorhanden.
    """
    if not anchor_ids:
        return []

    query_embedding: list[float] = await generate_embedding(query_text)

    # anchor_ids als Liste von Strings fuer asyncpg ARRAY-Binding
    anchor_id_strs = [str(aid) for aid in anchor_ids]

    # Embedding als pgvector-kompatibler String
    embedding_str = "[" + ",".join(f"{v:.10f}" for v in query_embedding) + "]"

    sql = sa.text(
        _SCOPE_CTE
        + """
        SELECT n.id, n.category, n.content_type, n.title, n.content,
               n.metadata AS metadata, n.embedding, n.owner_pseudonym,
               n.read_scope, n.write_scope,
               n.read_scope_group_id, n.write_scope_group_id,
               n.assistant_id, n.status, n.valid_until,
               n.archived_at, n.schuljahr,
               n.created_at, n.updated_at
        FROM context_nodes n
        WHERE n.id IN (SELECT id FROM scope)
          AND n.status = 'active'
          AND n.embedding IS NOT NULL
          AND (
              n.read_scope IN ('global', 'school')
              OR (n.read_scope = 'private' AND n.owner_pseudonym = :pseudonym)
          )
        ORDER BY n.embedding <=> CAST(:embedding AS vector)
        LIMIT :top_k
        """
    )

    result = await db.execute(
        sql,
        {
            "anchor_ids": anchor_id_strs,
            "pseudonym": pseudonym,
            "embedding": embedding_str,
            "top_k": top_k,
        },
    )
    rows = result.mappings().all()
    nodes = []
    for row in rows:
        row_dict = dict(row)
        # metadata Spalte heisst in der DB 'metadata', im ORM aber 'metadata_'
        if 'metadata' in row_dict:
            row_dict['metadata_'] = row_dict.pop('metadata')
        nodes.append(ContextNode(**row_dict))
    return nodes
