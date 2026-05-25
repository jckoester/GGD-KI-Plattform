"""Context-Service – öffentliche Schnittstelle des Kontextspeichers.

get_context_for_query() ist die einzige Funktion, die vom Chat-Router aufgerufen wird.
Sie wird in KS-Phase-3 vollständig implementiert.
"""

from sqlalchemy.ext.asyncio import AsyncSession


async def get_context_for_query(
    assistant_id: int,
    pseudonym: str,
    query_text: str,
    db: AsyncSession,
) -> str:
    """Assembliert den Kontext-String für einen Assistenten-Prompt.

    Kombiniert:
    - always_include-Knoten (vollständig injiziert, max. 15.000 Tokens gesamt)
    - retrieval_scope-Teilgraph (Vektorsuche, max. 2–3 Hops)
    - chat_context_nodes (explizit in dieser Session hinzugefügt)

    Gibt leeren String zurück bis KS-Phase-3.
    """
    return ""
