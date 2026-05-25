"""Embedding-Generierung für Kontextspeicher-Knoten.

Alle Funktionen sind Stubs. Implementierung erfolgt in KS-Phase-2.
Embedding-Modell: text-embedding-3-small (OpenAI, 1536 Dimensionen) via LiteLLM.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def generate_embedding(text: str) -> list[float]:
    """Ruft text-embedding-3-small via LiteLLM auf und gibt den Vektor zurück.

    Für ik_kompetenz/pk_kompetenz muss der Aufrufer den Breadcrumb-Pfad voranstellen:
    "Gymnasium | Mathematik | Klasse 5/6 | Leitidee XY: <content>"
    Der Breadcrumb kommt aus metadata['breadcrumb'] des Knotens.

    Gibt Nullvektor zurück bis KS-Phase-2.
    """
    return [0.0] * 1536


async def enqueue_embedding_job(node_id: UUID, db: AsyncSession) -> None:
    """Stellt einen asynchronen Hintergrund-Job zur Embedding-Generierung in die Queue.

    Wird nach dem synchronen INSERT eines neuen Knotens aufgerufen.
    Der Job liest den Knoten, ruft generate_embedding() auf und schreibt das
    Ergebnis in context_nodes.embedding.

    No-op bis KS-Phase-2.
    """
    pass
