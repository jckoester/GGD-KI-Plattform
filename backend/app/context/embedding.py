"""Embedding-Generierung fuer Kontextspeicher-Knoten.

Embedding-Modell: text-embedding-3-small (OpenAI, 1536 Dimensionen) via LiteLLM.
"""

import logging
from uuid import UUID

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode
from app.context.taxonomy import EMBEDDING_CONTENT_TYPES, EMBEDDING_ENRICHMENT

logger = logging.getLogger(__name__)

# Re-Export für Fremdimporte: from app.context.embedding import EMBEDDING_CONTENT_TYPES
__all__ = ["EMBEDDING_CONTENT_TYPES", "EMBEDDING_ENRICHMENT"]


def _build_signature_line(signatur: dict) -> str:
    """Rekonstruiert eine lesbare Signaturzeile aus dem signatur-Dict.

    Beispiel: 'digitalWrite(pin: int, value: int) -> void'
    Gibt leeren String zurueck wenn signatur leer oder unvollstaendig.
    """
    name = signatur.get("name", "")
    if not name:
        return ""
    params = signatur.get("parameter", [])
    rueckgabe = (signatur.get("rueckgabe") or {}).get("typ", "")
    param_str = ", ".join(
        f"{p.get('name', '?')}: {p.get('typ', '?')}" for p in params
    )
    arrow = f" -> {rueckgabe}" if rueckgabe else ""
    return f"{name}({param_str}){arrow}"


def _extract_metadata_field(metadata: dict, field_path: str) -> str:
    """Extrahiert einen Wert aus verschachteltem metadata anhand eines Punktpfades.

    Sonderfall: field_path == 'metadata.signatur' -> Signaturzeile rekonstruieren.
    """
    # Pfad ohne fuehrendes 'metadata.'
    path = field_path.removeprefix("metadata.")

    # Sonderfall: strukturierte Signaturzeile aus metadata.signatur
    if path == "signatur":
        return _build_signature_line(metadata.get("signatur", {}))

    # Generischer Punktpfad-Zugriff (z.B. 'schaltzeichen.beschreibung')
    parts = path.split(".")
    value = metadata
    for part in parts:
        if not isinstance(value, dict):
            return ""
        value = value.get(part, "")
    if isinstance(value, list):
        return " | ".join(str(v) for v in value) if value else ""
    return str(value) if value else ""


def _build_embedding_input(node: ContextNode) -> str:
    """Erstellt den Embedding-Input fuer einen Knoten.

    Reichert `content` mit content_type-spezifischen metadata-Feldern an,
    analog zur breadcrumb-Anreicherung fuer Bildungsplan-Knoten.
    """
    base = node.content or ""

    # Operatoren: das Verb (Titel) trägt die zentrale Semantik und steht NICHT im
    # content (= Definition/Erwartungshorizont). Titel + Synonyme (metadata.aliase)
    # voranstellen, damit die semantische Suche den Operator über sein Verb findet.
    if node.content_type == "operator":
        verbs = [node.title or ""] + list((node.metadata_ or {}).get("aliase", []) or [])
        prefix = ", ".join(v for v in verbs if v)
        return f"{prefix}\n{base}" if base else prefix

    enrichment_fields = EMBEDDING_ENRICHMENT.get((node.category, node.content_type), [])

    prefixes: list[str] = []
    for field_path in enrichment_fields:
        value = _extract_metadata_field(node.metadata_ or {}, field_path)
        if value:
            prefixes.append(value)

    if not prefixes:
        return base
    return "\n".join(prefixes) + "\n" + base


# text-embedding-3-small akzeptiert max. 8191 Tokens. Konservativer Zeichen-Cap
# (sicher selbst bei dichter Tokenisierung) gegen 400er bei sehr langen Knoten —
# für die semantische Einbettung genügt der Textanfang.
_MAX_EMBED_CHARS = 16000


async def generate_embedding(text: str) -> list[float]:
    """Ruft text-embedding-3-small ueber den LiteLLM-Proxy auf (HTTP, OpenAI-kompatibel).

    Konsistent mit dem Chat-Pfad: Das Backend spricht den LiteLLM-Proxy ausschliesslich
    ueber HTTP an (kein litellm-SDK). Proxy-URL/Master-Key/SSL aus den Settings.
    Sehr langer Input wird auf ``_MAX_EMBED_CHARS`` gekürzt (Token-Limit des Modells).
    Wirft httpx.HTTPError bei Fehlern (Aufrufer behandelt).
    """
    from app.config import settings
    text = text[:_MAX_EMBED_CHARS]
    async with httpx.AsyncClient(timeout=30.0, verify=settings.litellm_verify_ssl) as client:
        response = await client.post(
            f"{settings.litellm_proxy_url}/embeddings",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            json={"model": "text-embedding-3-small", "input": [text]},
        )
        response.raise_for_status()
        data = response.json()
    return data["data"][0]["embedding"]


async def enqueue_embedding_job(node_id: UUID, db: AsyncSession) -> None:
    """Generiert sofort ein Embedding fuer einen einzelnen neu angelegten Knoten.

    Wird nach dem INSERT eines neuen Knotens via API aufgerufen.
    Fehler werden geloggt aber nicht weitergeworfen (Embedding ist kein kritischer Pfad).
    """
    from app.config import settings
    if not settings.embeddings_enabled:
        return
    node = await db.get(ContextNode, node_id)
    if node is None:
        return
    if node.content_type not in EMBEDDING_CONTENT_TYPES:
        return
    try:
        text = _build_embedding_input(node)
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
