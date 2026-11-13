"""Promotion von Chat-Inhalten in die persönliche Artefaktbibliothek (Phase 18, Schritt 2).

„In Bibliothek speichern" hebt einen flüchtigen Chat-Inhalt (an die Konversation gebunden,
90/93-Tage-Lifecycle) in die dauerhafte Bibliothek. Je Herkunft:

- **Bild** (`generate_image`): Bytes werden kopiert, der Bild-Prompt wandert als roher
  Quelltext (`source`) mit.
- **circuit/plot/smiles/mermaid** (server-gerendert): aus dem rohen Quelltext **serverseitig neu
  gerendert** (deterministisch, nutzt den Render-Cache) — der Client-SVG wird bewusst nicht
  vertraut. Mermaid seit 0.36 (Pele im Sidecar); bis dahin übernahm die Bibliothek das im Browser
  gerenderte SVG. Ein mitgeschicktes `svg` wird ignoriert. Die Auslieferung härtet SVGs zusätzlich
  per CSP/nosniff ab (siehe `router.get_artifact_file`).

Idempotenz, Eigentümer-Bindung und Quota liegen in `store.save_artifact` bzw. hier über den
`origin_ref` (Herkunftsschlüssel). Eigentümer:in ist stets die eingeloggte Nutzer:in.
"""
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.artifacts import store
from app.db.models import Assistant, Conversation, Group, Message
from app.auth.jwt import JwtPayload
from app.chat import image_store
from app.render import service
from app.render.cache import svg_hash


class PromotionError(Exception):
    """Promotion nicht möglich (Quelle fehlt, Render-Fehler, unbekannter Typ)."""


@dataclass(frozen=True)
class Herkunft:
    """Woher ein Inhalt stammt — vom Backend ermittelt, nie vom Client behauptet.

    ``provider_model`` nur über eine Nachricht (das Modell steht an ihr); Fach und Assistent
    über die Konversation. Das Fach ist das der Konversation, sonst das ihrer Gruppe
    (Schüler-Chats tragen oft nur die Gruppe).
    """

    provider_model: Optional[str] = None
    conversation_id: Optional[UUID] = None
    subject_id: Optional[int] = None
    assistant_name: Optional[str] = None


KEINE_HERKUNFT = Herkunft()


async def herkunft(
    db: AsyncSession,
    *,
    pseudonym: str,
    message_id: Optional[UUID] = None,
    conversation_id: Optional[UUID] = None,
) -> Herkunft:
    """Herkunft über die Nachricht (bevorzugt) oder die Konversation — oder keine.

    **Warum über die ID und nicht über eine Angabe des Clients.** Diagramme und Dokumente
    entstehen aus dem Text einer Chat-Antwort; Modell, Fach und Assistent dahinter kennt nur
    das Backend. Ließe man den Browser sie mitschicken, stünde in einer Quellenangabe eine
    Behauptung — ausgerechnet dort, wo Verlässlichkeit der ganze Zweck ist.

    Die Konversation muss **dieser** Nutzer:in gehören; sonst ließe sich über eine fremde ID
    zwar kein Inhalt lesen, aber erraten, welches Modell, Fach und welcher Assistent dort im
    Einsatz waren. Fremde oder unbekannte ID → keine Herkunft, kein Fehler: Das Speichern
    soll daran nicht scheitern.

    ⚠️ Bis 0.40 bekamen Dokumente und Diagramme aus dem Chat **keine** Herkunfts-Konversation —
    der Client schickte nur die Nachrichten-ID, und daraus wurde allein das Modell gelesen.
    """
    if message_id is None and conversation_id is None:
        return KEINE_HERKUNFT
    spalten = [
        Message.provider_model if message_id is not None else literal(None),
        Conversation.id,
        func.coalesce(Conversation.subject_id, Group.subject_id),
        Assistant.name,
    ]
    stmt = select(*spalten).select_from(Conversation)
    if message_id is not None:
        stmt = stmt.join(Message, Message.conversation_id == Conversation.id).where(
            Message.id == message_id
        )
    else:
        stmt = stmt.where(Conversation.id == conversation_id)
    stmt = (
        stmt.outerjoin(Group, Group.id == Conversation.group_id)
        .outerjoin(Assistant, Assistant.id == Conversation.assistant_id)
        .where(Conversation.pseudonym == pseudonym)
    )
    zeile = (await db.execute(stmt)).first()
    if zeile is None:
        return KEINE_HERKUNFT
    return Herkunft(*zeile)


_DIAGRAM_DEFAULT_TITLE = {
    "circuit": "Schaltplan",
    "plot": "Funktionsgraph",
    "smiles": "Strukturformel",
    "mermaid": "Diagramm",
}
_SERVER_RENDER_KINDS = ("circuit", "plot", "smiles", "mermaid")
DIAGRAM_KINDS = ("circuit", "plot", "smiles", "mermaid")


def _title(explicit: Optional[str], default: str) -> str:
    t = (explicit or "").strip()
    return t[:200] if t else default


async def promote_image(
    db: AsyncSession, *, user: JwtPayload, image_id: UUID, title: Optional[str] = None
) -> tuple:
    """Promotet ein generiertes Bild. Gibt (Artefakt, created) zurück.

    `created=False` ⇒ war bereits in der Bibliothek (idempotent). Wirft `PermissionError`
    bei fremdem Bild, `PromotionError`, wenn Referenz/Datei fehlen, `store.QuotaExceeded`.
    """
    record = await image_store.get_image_record(db, image_id)
    if record is None:
        raise PromotionError("Bild nicht gefunden")
    if record.pseudonym != user.sub:
        raise PermissionError("fremdes Bild")
    data = image_store.read_image_bytes(record)
    if data is None:
        raise PromotionError("Bilddatei nicht gefunden")

    origin_ref = f"image:{image_id}"
    created = await store.find_by_origin_ref(db, user.sub, origin_ref) is None
    quelle = await herkunft(db, pseudonym=user.sub, conversation_id=record.conversation_id)
    artifact = await store.save_artifact(
        db,
        owner_pseudonym=user.sub,
        roles=user.roles,
        grade=user.grade,
        kind="image",
        mime_type=record.mime_type,
        data=data,
        title=_title(title, "Bild"),
        source=record.prompt,
        origin_ref=origin_ref,
        origin_conversation_id=record.conversation_id,
        # Herkunft mitkopieren: Die generated_images-Zeile stirbt mit der Konversation,
        # das Artefakt nicht (Alembic 0050). Fach und Assistent ebenso (0103).
        provider_model=record.provider_model,
        subject_id=quelle.subject_id,
        assistant_name=quelle.assistant_name,
    )
    return artifact, created


async def promote_diagram(
    db: AsyncSession,
    *,
    user: JwtPayload,
    kind: str,
    source: str,
    svg: Optional[str] = None,
    title: Optional[str] = None,
    message_id: Optional[UUID] = None,
) -> tuple:
    """Promotet ein gerendertes Diagramm. Gibt (Artefakt, created) zurück.

    Alle Diagramme werden serverseitig aus `source` neu gerendert (mermaid seit 0.36); `svg`
    bleibt aus Rückwärtsverträglichkeit im Aufruf, wird aber nicht mehr verwendet. Wirft `PromotionError` (leere Quelle, Render-Fehler, unbekannter Typ)
    bzw. `store.QuotaExceeded`.
    """
    source = (source or "").strip()
    if not source:
        raise PromotionError("leere Quelle")

    if kind in _SERVER_RENDER_KINDS:
        result = await service.render(db, kind, source)
        if result.get("error"):
            raise PromotionError(result["error"])
        svg_out = result["svg"]
    else:
        raise PromotionError(f"unbekannter Diagrammtyp: {kind}")

    origin_ref = f"{kind}:{svg_hash(kind, source)}"
    created = await store.find_by_origin_ref(db, user.sub, origin_ref) is None
    quelle = await herkunft(db, pseudonym=user.sub, message_id=message_id)
    artifact = await store.save_artifact(
        db,
        owner_pseudonym=user.sub,
        roles=user.roles,
        grade=user.grade,
        kind=kind,
        mime_type="image/svg+xml",
        data=svg_out.encode("utf-8"),
        title=_title(title, _DIAGRAM_DEFAULT_TITLE.get(kind, "Diagramm")),
        source=source,
        origin_ref=origin_ref,
        origin_conversation_id=quelle.conversation_id,
        provider_model=quelle.provider_model,
        subject_id=quelle.subject_id,
        assistant_name=quelle.assistant_name,
    )
    return artifact, created
