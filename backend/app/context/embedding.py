"""Embedding-Generierung fuer Kontextspeicher-Knoten.

Das Embedding-Modell ist nicht fest verdrahtet: Modellname, Vektorbreite und Input-Cap
kommen aus den Settings (``EMBEDDING_MODEL``, ``EMBEDDING_DIMENSIONS``,
``EMBEDDING_MAX_CHARS``). Angesprochen wird ausschliesslich der LiteLLM-Proxy, der den
Namen auf den tatsaechlichen Anbieter aufloest. Ein Modellwechsel ist damit reine
Konfiguration — erfordert aber Migration + Re-Embedding, wenn sich die Vektorbreite
aendert (siehe docs/runbooks/modellwechsel.md).
"""

import asyncio
import logging
from uuid import UUID

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode
from app.context.taxonomy import EMBEDDING_CONTENT_TYPES, EMBEDDING_ENRICHMENT

logger = logging.getLogger(__name__)

# Vorübergehende Zustände: Rate-Limit bzw. Dienst gerade nicht verfügbar. Alles andere
# (400 falscher Parameter, 401 Schlüssel, 404 Modell) wiederholt sich sinnlos.
_RETRY_STATUS = frozenset({429, 503})

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


class EmbeddingDimensionError(RuntimeError):
    """Das Modell lieferte eine andere Vektorbreite als konfiguriert.

    Eigener Typ, damit Aufrufer den Konfigurationsfehler von einem Netz-/HTTP-Fehler
    unterscheiden koennen: Ein Retry hilft hier nicht, es braucht Migration + Settings.
    """


def _wartezeit(response: httpx.Response, versuch: int, max_wait: float) -> float:
    """Wartezeit vor dem nächsten Versuch — ``Retry-After`` schlägt die Schätzung.

    Der Anbieter weiß besser als wir, wann sein Fenster wieder offen ist. Fehlt die
    Angabe (oder ist sie ein HTTP-Datum, das wir hier nicht auswerten), wird
    exponentiell gewartet: 1s, 2s, 4s … Beides wird auf ``max_wait`` gedeckelt, damit
    ein großzügiges ``Retry-After`` keinen laufenden Request blockiert.
    """
    kopf = response.headers.get("retry-after")
    if kopf:
        try:
            return min(float(kopf), max_wait)
        except ValueError:
            pass  # HTTP-Datum statt Sekunden → Schätzung verwenden
    return min(2.0 ** (versuch - 1), max_wait)


async def _post_mit_wiederholung(
    client: httpx.AsyncClient, payload: dict
) -> httpx.Response:
    """Sendet die Embedding-Anfrage und wiederholt sie bei 429/503.

    Ein Rate-Limit ist ein *vorübergehender* Zustand. Ohne Wiederholung wird daraus ein
    dauerhafter `embedding_error` am Knoten — genau der Fall, der nach einem großen
    Bildungsplan-Import auftritt, wenn der Backfill Tausende Knoten hintereinander
    einbettet.
    """
    from app.config import settings

    letzte: httpx.Response | None = None
    for versuch in range(1, settings.embedding_max_retries + 2):
        letzte = await client.post(
            f"{settings.litellm_proxy_url}/embeddings",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            json=payload,
        )
        if letzte.status_code not in _RETRY_STATUS:
            break
        if versuch > settings.embedding_max_retries:
            logger.warning(
                "Embedding: %d nach %d Versuchen — gebe auf",
                letzte.status_code, versuch,
            )
            break
        wartezeit = _wartezeit(letzte, versuch, settings.embedding_retry_max_wait_s)
        logger.info(
            "Embedding: %d (Versuch %d/%d), warte %.1fs",
            letzte.status_code, versuch, settings.embedding_max_retries + 1, wartezeit,
        )
        await asyncio.sleep(wartezeit)

    assert letzte is not None  # Schleife läuft mindestens einmal
    letzte.raise_for_status()
    return letzte


async def generate_embedding(text: str) -> list[float]:
    """Ruft das konfigurierte Embedding-Modell ueber den LiteLLM-Proxy auf.

    Konsistent mit dem Chat-Pfad: Das Backend spricht den LiteLLM-Proxy ausschliesslich
    ueber HTTP an (kein litellm-SDK), OpenAI-kompatibel. Modellname, Input-Cap und
    erwartete Vektorbreite kommen aus den Settings; Proxy-URL/Master-Key/SSL ebenso.

    Sehr langer Input wird auf ``EMBEDDING_MAX_CHARS`` gekuerzt — konservativer Zeichen-Cap
    (Zeichen != Token, sicher selbst bei dichter Tokenisierung) gegen 400er bei sehr langen
    Knoten; fuer die semantische Einbettung genuegt der Textanfang.

    Wirft ``httpx.HTTPError`` bei Transportfehlern und ``EmbeddingDimensionError``, wenn die
    gelieferte Vektorbreite nicht zu ``EMBEDDING_DIMENSIONS`` passt (Aufrufer behandeln).
    """
    from app.config import settings
    text = text[: settings.embedding_max_chars]
    payload: dict = {"model": settings.embedding_model, "input": [text]}
    # Nur fuer Modelle, die das Kuerzen unterstuetzen (OpenAI text-embedding-3-*);
    # andere Anbieter quittieren den unbekannten Parameter mit 400.
    if settings.embedding_send_dimensions:
        payload["dimensions"] = settings.embedding_dimensions
    async with httpx.AsyncClient(timeout=30.0, verify=settings.litellm_verify_ssl) as client:
        response = await _post_mit_wiederholung(client, payload)
        data = response.json()
    embedding = data["data"][0]["embedding"]
    expected = settings.embedding_dimensions
    if len(embedding) != expected:
        # Frueh und mit klarer Ansage abbrechen. Ohne diese Pruefung scheitert erst der
        # DB-Insert mit einer pgvector-Fehlermeldung, die die Ursache nicht nennt.
        raise EmbeddingDimensionError(
            f"Modell '{settings.embedding_model}' liefert {len(embedding)} Dimensionen, "
            f"erwartet werden {expected}. EMBEDDING_DIMENSIONS und die Spaltenbreite von "
            f"context_nodes.embedding pruefen (Migration + Re-Embedding noetig)."
        )
    return embedding


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
