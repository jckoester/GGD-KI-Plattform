"""Embedding-Generierung fuer Kontextspeicher-Knoten.

Embedding-Modell: text-embedding-3-small (OpenAI, 1536 Dimensionen) via LiteLLM.
"""

import logging
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode

logger = logging.getLogger(__name__)

# content_types die ein Embedding erhalten (Whitelist)
EMBEDDING_CONTENT_TYPES = frozenset({
    'ik_kompetenz',
    'pk_kompetenz',
    'pk_gruppe',
    'leitidee',
    'leitperspektive_aspekt',
})


def build_embedding_input(node: ContextNode) -> str:
    """Baut den Embedding-Input-String mit Breadcrumb-Praefix.

    Format: "Gymnasium | Chemie | Klasse 7/8 | Leitidee XY: <content>"
    Der Breadcrumb kommt aus node.metadata_['breadcrumb'].
    """
    breadcrumb: list[str] = node.metadata_.get('breadcrumb', [])
    prefix = ' | '.join(breadcrumb)
    content = node.content or node.title or ''
    return f"{prefix}: {content}" if prefix else content


async def generate_embedding(text: str) -> list[float]:
    """Ruft text-embedding-3-small via LiteLLM-Proxy auf.

    Liest LITELLM_PROXY_URL und LITELLM_MASTER_KEY aus der Umgebung.
    Wirft litellm.exceptions.APIError bei Fehlern (Aufrufer behandelt).
    """
    import os
    import litellm
    proxy_url = os.environ.get('LITELLM_PROXY_URL', 'http://localhost:4000')
    api_key = os.environ.get('LITELLM_MASTER_KEY', 'dummy')
    response = await litellm.aembedding(
        model='text-embedding-3-small',
        input=[text],
        api_base=proxy_url,
        api_key=api_key,
    )
    return response.data[0]['embedding']


async def enqueue_embedding_job(node_id: UUID, db: AsyncSession) -> None:
    """Generiert sofort ein Embedding fuer einen einzelnen neu angelegten Knoten.

    Wird nach dem INSERT eines neuen Knotens via API aufgerufen.
    Fehler werden geloggt aber nicht weitergeworfen (Embedding ist kein kritischer Pfad).
    """
    node = await db.get(ContextNode, node_id)
    if node is None:
        return
    if node.content_type not in EMBEDDING_CONTENT_TYPES:
        return
    try:
        text = build_embedding_input(node)
        embedding = await generate_embedding(text)
        await db.execute(
            update(ContextNode)
            .where(ContextNode.id == node_id)
            .values(embedding=embedding)
        )
        await db.commit()
    except Exception as exc:
        logger.error(f"Embedding-Fehler fuer Knoten {node_id}: {exc}")
        node.metadata_ = {**node.metadata_, 'embedding_error': str(exc)}
        await db.commit()
