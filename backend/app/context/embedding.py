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
import re
from dataclasses import dataclass
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


# Fuehrende Gliederungsnummer: "3.6.1(13) Text", "(13) Text", "2.1 Text".
_GLIEDERUNGSNUMMER = re.compile(r"^\s*(?:\d+(?:\.\d+)*)?\s*(?:\(\d+\))?\s*")


def _titel_traegt_eigene_information(titel: str, text: str) -> bool:
    """Steht im Titel etwas, das der Text nicht ohnehin schon sagt?

    Der Bildungsplan verhaelt sich hier je Knotenart voellig unterschiedlich (gemessen am
    Gesamtbestand):

    * Bei ``ik_kompetenz``, ``pk_kompetenz`` und ``leitperspektive_aspekt`` ist der Titel
      **ausnahmslos** der Inhalt plus Gliederungsnummer (`3.6.1(13) … erlaeutern` gegen
      `(13) … erlaeutern`). Ihn voranzustellen wuerde den Text nur verdoppeln und den
      Vektor verzerren — ohne ein Byte neue Information.
    * Bei ``leitidee``, ``pk_gruppe`` und ``kapitel`` benennt der Titel dagegen das Thema
      (`3.1.2.2 Malerei`), das im beschreibenden Inhalt oft gar nicht vorkommt. Und wo der
      Inhalt fehlt, ist der Titel das Einzige, was der Knoten hat: Ohne ihn wurde er
      uebersprungen und war fuer die semantische Suche unsichtbar.

    Die Gliederungsnummer wird vor dem Vergleich entfernt, sonst schlaegt er bei genau den
    Kompetenzen fehl, um die es geht.
    """
    if not titel:
        return False
    kern = " ".join(_GLIEDERUNGSNUMMER.sub("", titel).lower().split())
    return bool(kern) and kern not in " ".join((text or "").lower().split())


def _build_embedding_input(node: ContextNode) -> str:
    """Erstellt den Embedding-Input fuer einen Knoten.

    Reichert `content` mit content_type-spezifischen metadata-Feldern an,
    analog zur breadcrumb-Anreicherung fuer Bildungsplan-Knoten, und stellt den Titel
    voran, wo er eigene Information traegt (siehe ``_titel_traegt_eigene_information``).
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

    teile: list[str] = []
    for field_path in enrichment_fields:
        value = _extract_metadata_field(node.metadata_ or {}, field_path)
        if value:
            teile.append(value)
    if base:
        teile.append(base)

    # Gegen den bereits zusammengesetzten Text pruefen, nicht nur gegen `content`: Steht
    # der Titel schon in einer Anreicherung (Breadcrumb), waere er sonst doppelt drin.
    if _titel_traegt_eigene_information(node.title or "", "\n".join(teile)):
        teile.insert(0, node.title)

    return "\n".join(teile)


class EmbeddingDimensionError(RuntimeError):
    """Das Modell lieferte eine andere Vektorbreite als konfiguriert.

    Eigener Typ, damit Aufrufer den Konfigurationsfehler von einem Netz-/HTTP-Fehler
    unterscheiden koennen: Ein Retry hilft hier nicht, es braucht Migration + Settings.
    """


class EmbeddingResponseError(RuntimeError):
    """Die Antwort passt nicht zur Anfrage — falsche Anzahl oder Indizes.

    Betrifft nur den Stapelbetrieb. Eigener Typ, weil hier NICHTS uebernommen werden darf:
    Ohne verlaessliche 1:1-Zuordnung bekaemen Knoten fremde Vektoren, und das faellt
    danach nirgends mehr auf.
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


def _batch_timeout(anzahl: int) -> float:
    """Zeitbudget fuer eine Anfrage mit ``anzahl`` Texten.

    Ein fester 30s-Wert passt zum Einzelaufruf, nicht zu einem Stapel: Der Anbieter
    rechnet laenger, und ein Timeout mitten im Stapel verwirft die Arbeit fuer ALLE
    darin enthaltenen Texte. Deshalb waechst das Budget mit der Stapelgroesse.
    """
    return min(300.0, 30.0 + 1.5 * max(0, anzahl - 1))


@dataclass(frozen=True)
class EmbeddingStapel:
    """Vektoren einer Stapelanfrage plus deren tatsaechlicher Tokenverbrauch.

    Der Verbrauch dient dem Aufrufer zum Takten (siehe
    ``EMBEDDING_TOKENS_PER_SECOND``). Er kommt aus ``usage.total_tokens`` der Antwort;
    liefert ein Anbieter das Feld nicht, wird aus der Zeichenzahl geschaetzt.
    """

    vektoren: list[list[float]]
    tokens: int


# Grobe Schaetzung, nur als Rueckfallebene. Bewusst niedrig angesetzt (deutscher Fachtext
# tokenisiert dichter als englischer): Sie ueberschaetzt damit den Verbrauch, und eine zu
# langsame Taktung ist harmloser als eine zu schnelle.
_ZEICHEN_JE_TOKEN = 3


async def generate_embeddings(texts: list[str]) -> EmbeddingStapel:
    """Bettet mehrere Texte in EINER Anfrage ein — Rueckgabe in Eingabereihenfolge.

    Die OpenAI-kompatible API nimmt eine Liste entgegen. Ein Aufruf je Knoten macht aus
    einem Re-Embedding des Bildungsplans (~14.000 Knoten) einen mehrstuendigen Lauf; im
    Stapel sind es Minuten. Aufrufer, die genau einen Text haben, nutzen
    ``generate_embedding``.

    Sehr langer Input wird je Text auf ``EMBEDDING_MAX_CHARS`` gekuerzt — konservativer
    Zeichen-Cap (Zeichen != Token, sicher selbst bei dichter Tokenisierung) gegen 400er bei
    sehr langen Knoten; fuer die semantische Einbettung genuegt der Textanfang.

    Wirft ``httpx.HTTPError`` bei Transportfehlern und ``EmbeddingDimensionError``, wenn die
    gelieferte Vektorbreite nicht zu ``EMBEDDING_DIMENSIONS`` passt (Aufrufer behandeln).
    """
    if not texts:
        return EmbeddingStapel(vektoren=[], tokens=0)

    from app.config import settings
    gekuerzt = [t[: settings.embedding_max_chars] for t in texts]
    payload: dict = {"model": settings.embedding_model, "input": gekuerzt}
    # Nur fuer Modelle, die das Kuerzen unterstuetzen (OpenAI text-embedding-3-*);
    # andere Anbieter quittieren den unbekannten Parameter mit 400.
    if settings.embedding_send_dimensions:
        payload["dimensions"] = settings.embedding_dimensions

    async with httpx.AsyncClient(
        timeout=_batch_timeout(len(gekuerzt)), verify=settings.litellm_verify_ssl
    ) as client:
        response = await _post_mit_wiederholung(client, payload)
        data = response.json()

    eintraege = data.get("data") or []
    if len(eintraege) != len(gekuerzt):
        # Ein unvollstaendiger Stapel darf NICHT teilweise verarbeitet werden: Ohne
        # 1:1-Zuordnung waere unklar, welcher Vektor zu welchem Knoten gehoert.
        raise EmbeddingResponseError(
            f"Modell '{settings.embedding_model}' lieferte {len(eintraege)} Vektoren fuer "
            f"{len(gekuerzt)} Texte."
        )

    # NACH `index` sortieren, wo es ihn gibt — nicht auf die Listenreihenfolge vertrauen.
    # Ein vertauschter Vektor faellt nirgends auf: Er wirft keinen Fehler, er macht die
    # semantische Suche still schlechter.
    indizes = [e.get("index") for e in eintraege]
    if all(isinstance(i, int) for i in indizes):
        if sorted(indizes) != list(range(len(gekuerzt))):
            raise EmbeddingResponseError(
                f"Modell '{settings.embedding_model}' lieferte unerwartete Indizes: "
                f"{indizes!r} fuer {len(gekuerzt)} Texte."
            )
        eintraege = sorted(eintraege, key=lambda e: e["index"])
    elif any(isinstance(i, int) for i in indizes):
        # Teils mit, teils ohne — hier laesst sich nicht entscheiden, was gilt.
        raise EmbeddingResponseError(
            f"Modell '{settings.embedding_model}' lieferte teils indizierte, teils "
            f"unindizierte Eintraege: {indizes!r}"
        )
    elif len(eintraege) > 1:
        # Kein `index` vorhanden: Die Listenreihenfolge ist das einzig Verfuegbare.
        logger.warning(
            "Embedding-Antwort von '%s' ohne `index` — Zuordnung folgt der "
            "Listenreihenfolge.", settings.embedding_model,
        )

    expected = settings.embedding_dimensions
    vektoren = [e["embedding"] for e in eintraege]
    for vektor in vektoren:
        if len(vektor) != expected:
            # Frueh und mit klarer Ansage abbrechen. Ohne diese Pruefung scheitert erst der
            # DB-Insert mit einer pgvector-Fehlermeldung, die die Ursache nicht nennt.
            raise EmbeddingDimensionError(
                f"Modell '{settings.embedding_model}' liefert {len(vektor)} Dimensionen, "
                f"erwartet werden {expected}. EMBEDDING_DIMENSIONS und die Spaltenbreite von "
                f"context_nodes.embedding pruefen (Migration + Re-Embedding noetig)."
            )

    tokens = ((data.get("usage") or {}).get("total_tokens")) or 0
    if not tokens:
        tokens = sum(len(t) for t in gekuerzt) // _ZEICHEN_JE_TOKEN
    return EmbeddingStapel(vektoren=vektoren, tokens=int(tokens))


async def generate_embedding(text: str) -> list[float]:
    """Ruft das konfigurierte Embedding-Modell ueber den LiteLLM-Proxy auf.

    Konsistent mit dem Chat-Pfad: Das Backend spricht den LiteLLM-Proxy ausschliesslich
    ueber HTTP an (kein litellm-SDK), OpenAI-kompatibel. Modellname, Input-Cap und
    erwartete Vektorbreite kommen aus den Settings; Proxy-URL/Master-Key/SSL ebenso.

    Einzelaufruf — fuer mehrere Texte ``generate_embeddings`` verwenden.
    """
    return (await generate_embeddings([text])).vektoren[0]


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
