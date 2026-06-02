"""Context-Service – öffentliche Schnittstelle des Kontextspeichers.

get_context_for_query() ist die einzige Funktion, die vom Chat-Router aufgerufen wird.
"""

import asyncio
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.retrieval import EngagementEntry, get_engagement_context, get_semantic_context
from app.db.models import AssistantContextAnchor, ChatContextNode, ContextNode


_RELATION_LABELS: dict[str, str] = {
    "introduced": "eingeführt",
    "knows": "bekannt",
    "mastered": "beherrscht",
    "struggles_with": "Schwierigkeiten",
}


def _assemble_context(
    semantic_nodes: list[ContextNode],
    engagement_entries: list[EngagementEntry],
    pinned_nodes: list[ContextNode],
) -> str:
    sections: list[str] = []

    if semantic_nodes:
        lines = ["## Relevante Lerninhalte\n"]
        for node in semantic_nodes:
            breadcrumb = ""
            if node.metadata_ and "breadcrumb" in node.metadata_:
                breadcrumb = " | ".join(node.metadata_["breadcrumb"]) + "\n"
            content = node.content or ""
            lines.append(f"### {node.title}\n{breadcrumb}{content}\n")
        sections.append("\n".join(lines))

    if engagement_entries:
        lines = ["## Vorwissen dieses Lernenden\n"]
        for entry in engagement_entries:
            label = " / ".join(
                _RELATION_LABELS.get(r, r) for r in entry.relations
            )
            lines.append(f"- **{entry.node.title}** ({label})")
        sections.append("\n".join(lines))

    if pinned_nodes:
        lines = ["## Explizit hinzugefügter Kontext\n"]
        for node in pinned_nodes:
            content = node.content or ""
            lines.append(f"### {node.title}\n{content}\n")
        sections.append("\n".join(lines))

    if not sections:
        return ""

    return "\n\n---\n\n".join(sections)


async def get_context_for_query(
    assistant_id: int | None,
    pseudonym: str,
    query_text: str,
    chat_id: UUID | None,
    db: AsyncSession,
) -> str:
    """Assembliert den Kontext-String für einen Chat-Prompt.

    Kombiniert semantische Suche, Engagement-Retrieval und explizit gepinnte Knoten.
    Pinned nodes werden unabhängig von einem Assistenten oder retrieval_scope geladen.
    """
    # Retrieval-Scope-Anker nur laden wenn ein Assistent aktiv ist
    anchor_ids: list[UUID] = []
    if assistant_id is not None:
        result = await db.execute(
            sa.select(AssistantContextAnchor.node_id)
            .where(
                AssistantContextAnchor.assistant_id == assistant_id,
                AssistantContextAnchor.role == "retrieval_scope",
            )
        )
        anchor_ids = [row[0] for row in result.all()]

    # Gepinnte Knoten immer laden (unabhängig von retrieval_scope)
    pinned_nodes: list[ContextNode] = []
    if chat_id is not None:
        pinned_result = await db.execute(
            sa.select(ContextNode)
            .join(ChatContextNode, ChatContextNode.node_id == ContextNode.id)
            .where(
                ChatContextNode.chat_id == chat_id,
                ContextNode.status == "active",
            )
        )
        pinned_nodes = list(pinned_result.scalars().all())

    # Semantische Suche nur wenn retrieval_scope-Anker vorhanden
    semantic_nodes: list[ContextNode] = []
    engagement_entries: list[EngagementEntry] = []
    if anchor_ids:
        semantic_nodes, engagement_entries = await asyncio.gather(
            get_semantic_context(anchor_ids, query_text, pseudonym, db),
            get_engagement_context(anchor_ids, pseudonym, db),
        )

    return _assemble_context(semantic_nodes, engagement_entries, pinned_nodes)
