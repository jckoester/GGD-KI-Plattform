"""Retrieval-Funktionen für den Kontextspeicher.

Alle Funktionen sind Stubs. Implementierung erfolgt in KS-Phase-3.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode


async def vector_search(
    query_embedding: list[float],
    db: AsyncSession,
    *,
    category: str | None = None,
    content_types: list[str] | None = None,
    read_scope_pseudonym: str | None = None,
    limit: int = 10,
) -> list[ContextNode]:
    """Vektorsuche über context_nodes mit optionalem category/content_type-Vorfilter.

    Nur aktive Knoten (status='active') werden berücksichtigt.
    Gibt leere Liste zurück bis KS-Phase-3.
    """
    return []


async def graph_traverse(
    start_node_id: UUID,
    db: AsyncSession,
    *,
    max_hops: int = 2,
    relation_filter: list[str] | None = None,
) -> list[ContextNode]:
    """Recursive-CTE-Traversierung des Wissensgraphen ab einem Startknoten.

    Folgt context_edges bis max_hops Tiefe.
    Relationstyp-gefiltert wenn relation_filter gesetzt (empfohlen — nie alle Kanten).
    Gibt leere Liste zurück bis KS-Phase-3.
    """
    return []
