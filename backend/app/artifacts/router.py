"""Artefaktbibliothek-Endpunkte (Phase 18).

Schritt 1: Auslieferung der Artefakt-Bytes (Pseudonym-Auth, analog `GET /images/{id}`).
Schritt 2: „In Bibliothek speichern" — Promotion von Chat-Inhalten (Bild/Diagramm).
Liste/Löschen/Download-Varianten kommen in Schritt 3.
"""
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

import re

from app.artifacts import geogebra, im_chat, promote, store, uebernahme
from app.assistants import produkte
from app.artifacts.limits import get_artifact_limits
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.context.embedding import enqueue_embedding_job
from app.db.models import Artifact
from app.db.session import get_db
from app.export import document as doc_export
from app.export import pandoc
from app.export import templates as export_templates
from app.litellm.deployments import zitiername
from app.config import settings
from app.render.errors import RenderError

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

_GGB_MIME = "application/vnd.geogebra.file"


def _slug(title: str | None, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:60]
    return slug or fallback


def _ggb_filename(title: str | None) -> str:
    return f"{_slug(title, 'funktionsgraph')}.ggb"


def _ggb_response(data: bytes, title: str | None) -> Response:
    return Response(
        content=data,
        media_type=_GGB_MIME,
        headers={"Content-Disposition": f'attachment; filename="{_ggb_filename(title)}"'},
    )

# SVG-Artefakte können (mermaid) aus Client-gerendertem Markup stammen. Auslieferung nur an
# die Eigentümer:in, aber zusätzlich gehärtet: kein Skript, kein aktiver Inhalt, kein Sniffing.
_SVG_HARDENING = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "X-Content-Type-Options": "nosniff",
}


class SavedArtifact(BaseModel):
    """Antwort nach „In Bibliothek speichern"."""

    id: UUID
    kind: str
    mime_type: str
    title: str
    byte_size: int
    created_at: datetime
    expires_at: datetime
    created: bool  # False ⇒ war bereits in der Bibliothek (idempotent)


# ⚠️ Vor `ArtifactItem`: Python 3.12 (Prod-Image) wertet Annotationen im Klassenrumpf sofort aus,
# erst 3.14 (Dev) aufgeschoben (PEP 649). Umgekehrt angeordnet startete das Backend auf Prod nicht.
class ExportItem(BaseModel):
    """Ein Export am Dokument (0.41, F5) — eingeklappt an dessen Karte."""

    id: UUID
    kind: str
    mime_type: str
    title: str
    byte_size: int
    created_at: datetime


class ArtifactItem(BaseModel):
    """Ein Bibliotheks-Eintrag (Metadaten + roher Quelltext für Kopieren/Download)."""

    id: UUID
    kind: str
    mime_type: str
    title: str
    byte_size: int
    source: str | None
    created_at: datetime
    expires_at: datetime
    # Anbietermodell, mit dem der Inhalt erzeugt wurde — Grundlage der Quellenangabe.
    # None heißt „nicht bekannt": bei leer angelegten Dokumenten, bei Diagrammen und
    # Dokumenten aus der Zeit vor 0.41 und bei Artefakten aus der Zeit vor Alembic 0050.
    provider_model: str | None = None
    # Ordnung der Werkstatt (0.41): eigenes Fach, Thema, zuletzt bearbeitet, Assistent der Herkunft.
    subject_id: int | None = None
    topic: str | None = None
    updated_at: datetime | None = None
    assistant_name: str | None = None
    # Exporte dieses Dokuments (0.41, F5); sie stehen nicht mehr für sich in der Liste.
    exporte: list[ExportItem] = []
    # Lässt sich daraus ein Baustein machen (AP8)? Die Antwort kommt vom Server, damit
    # der Knopf in der Bibliothek nicht nach eigener Rechnung erscheint.
    uebernehmbar: bool = False
    # Der Baustein, der daraus geworden ist — Grundlage des Badges „als Baustein
    # übernommen →". None heißt: noch keiner, oder der letzte wurde gelöscht.
    baustein_id: UUID | None = None
    baustein_titel: str | None = None


class LibraryResponse(BaseModel):
    items: list[ArtifactItem]
    used_bytes: int
    quota_bytes: int
    # 0.41: Treffer des Filters insgesamt (für „Mehr laden“) und die Auswahl der Filter —
    # Fächer und Themen über den ganzen Bestand, nicht über den gefilterten.
    total: int = 0
    faecher: list[int] = []
    themen: list[str] = []


class FromImageRequest(BaseModel):
    image_id: UUID
    title: str | None = None


class FromDiagramRequest(BaseModel):
    kind: str            # circuit | plot | mermaid
    source: str
    svg: str | None = None   # nur mermaid: bereits im Browser gerendertes SVG
    title: str | None = None
    # Nachricht, aus der das Diagramm stammt. Das Backend schlägt darüber das
    # Anbietermodell nach — der Client nennt nur die ID, nicht das Modell.
    message_id: UUID | None = None


class GgbRequest(BaseModel):
    source: str          # rohe Plot-Spec (YAML)
    title: str | None = None


class DocumentCreateRequest(BaseModel):
    title: str | None = None
    markdown: str = ""
    origin_conversation_id: UUID | None = None
    # Wie bei FromDiagramRequest: nur die ID, das Modell schlägt das Backend nach.
    message_id: UUID | None = None


class DocumentUpdateRequest(BaseModel):
    title: str | None = None
    markdown: str = ""


class DocumentResponse(BaseModel):
    """Ein Text-Dokument fürs Bearbeiten (Quelle = Markdown)."""

    id: UUID
    title: str
    kind: str
    source: str
    byte_size: int
    created_at: datetime
    expires_at: datetime


class AngabenUpdate(BaseModel):
    """Titel, Fach, Thema ändern (0.41). Nur gesendete Felder zählen; `null` bei Fach oder
    Thema entfernt es."""

    title: str | None = None
    subject_id: int | None = None
    topic: str | None = None


class AngabenAntwort(BaseModel):
    id: UUID
    title: str
    subject_id: int | None
    topic: str | None
    updated_at: datetime
    expires_at: datetime


class ThemenAntwort(BaseModel):
    """Vorschläge fürs Thema: eigene frühere Themen; für Lehrkräfte dazu die Titel der
    Einheiten ihrer Gruppen (als Text, keine Kante zur Planung — Plan F8)."""

    eigene: list[str]
    einheiten: list[str]


def _saved(artifact: Artifact, created: bool) -> SavedArtifact:
    return SavedArtifact(
        id=artifact.id,
        kind=artifact.kind,
        mime_type=artifact.mime_type,
        title=artifact.title,
        byte_size=artifact.byte_size,
        created_at=artifact.created_at,
        expires_at=artifact.expires_at,
        created=created,
    )


@router.post("/from-image", response_model=SavedArtifact)
async def save_image_to_library(
    req: FromImageRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedArtifact:
    """Promotet ein generiertes Bild in die Bibliothek der eingeloggten Nutzer:in."""
    try:
        artifact, created = await promote.promote_image(
            db, user=current_user, image_id=req.image_id, title=req.title
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    except store.QuotaExceeded:
        raise HTTPException(
            status_code=409,
            detail="Deine Werkstatt ist voll. Bitte lösche zuerst ältere Produkte.",
        )
    except promote.PromotionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _saved(artifact, created)


@router.post("/from-diagram", response_model=SavedArtifact)
async def save_diagram_to_library(
    req: FromDiagramRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedArtifact:
    """Promotet ein gerendertes Diagramm (circuit/plot server-, mermaid client-gerendert)."""
    if req.kind not in promote.DIAGRAM_KINDS:
        raise HTTPException(status_code=422, detail="unbekannter Diagrammtyp")
    try:
        artifact, created = await promote.promote_diagram(
            db, user=current_user, kind=req.kind, source=req.source,
            svg=req.svg, title=req.title, message_id=req.message_id,
        )
    except store.QuotaExceeded:
        raise HTTPException(
            status_code=409,
            detail="Deine Werkstatt ist voll. Bitte lösche zuerst ältere Produkte.",
        )
    except promote.PromotionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _saved(artifact, created)


@router.get("/topics", response_model=ThemenAntwort)
async def themen_vorschlaege(
    subject_id: int | None = Query(default=None, description="nur Themen dieses Fachs"),
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThemenAntwort:
    """Themen zum Vorschlagen. Vor `/{artifact_id}` registriert — sonst hielte FastAPI
    „topics“ für eine ID.

    Schüler:innen bekommen nur die eigenen (F8): Die Titel der Einheiten sind Planung der
    Lehrkraft. Eigene Gruppen nur über `vorschau.mitglied()` — in der Vorschau ist die
    Lehrkraft dort Schüler:in und bekommt deshalb keine Einheiten.
    """
    eigene = await store.eigene_themen(db, current_user.sub, subject_id=subject_id)
    einheiten: list[str] = []
    if uebernahme.ist_lehrkraft(current_user.roles):
        import sqlalchemy as sa
        from app.auth import vorschau
        from app.db.models import ContextNode, Group, GroupMembership

        gruppen = (
            sa.select(GroupMembership.group_id)
            .join(Group, Group.id == GroupMembership.group_id)
            .where(vorschau.mitglied(current_user.sub, "teacher"))
        )
        if subject_id is not None:
            gruppen = gruppen.where(Group.subject_id == subject_id)
        einheiten = list((await db.execute(
            sa.select(ContextNode.title)
            .where(
                ContextNode.content_type == "unterrichtseinheit",
                ContextNode.status == "active",
                ContextNode.write_scope.in_(("group", "group_teachers")),
                ContextNode.write_scope_group_id.in_(gruppen),
            )
            .distinct()
            .order_by(ContextNode.title)
        )).scalars())
        bekannt = set(eigene)
        einheiten = [t for t in einheiten if t and t not in bekannt]
    return ThemenAntwort(eigene=eigene, einheiten=einheiten)


# ── Produkte im Chat (0.41, Schritt 10) ──────────────────────────────────────
#
# Vor `/{artifact_id}` registriert (wie `/topics`), sonst hielte FastAPI „anhaengbar“ und
# „chats“ für eine ID. Rollenoffen; in der Vorschau sperrt `vorschau.ERLAUBT` das Anhängen.


class AnhangItem(BaseModel):
    artifact_id: UUID
    kind: str
    title: str
    subject_id: int | None = None
    added_at: datetime | None = None


class AnhangRequest(BaseModel):
    artifact_id: UUID


def _anhang(r: Artifact, added_at: datetime | None = None) -> AnhangItem:
    return AnhangItem(artifact_id=r.id, kind=r.kind, title=r.title, subject_id=r.subject_id,
                      added_at=added_at)


async def _eigener_chat(db: AsyncSession, conversation_id: UUID, user: JwtPayload):
    from app.auth import vorschau
    from app.db.models import Conversation

    conv = await db.get(Conversation, conversation_id)
    if not vorschau.darf_chat_sehen(conv, user):
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden")
    return conv


@router.get("/anhaengbar", response_model=list[AnhangItem])
async def anhaengbare_produkte(
    q: str = Query(default="", max_length=200, description="Teil des Titels"),
    limit: int = Query(default=8, ge=1, le=20),
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AnhangItem]:
    """Eigene Produkte, die sich an einen Chat hängen lassen (`@`-Dropdown)."""
    return [_anhang(r) for r in await im_chat.anhaengbare(db, current_user.sub, q, limit=limit)]


@router.get("/chats/{conversation_id}", response_model=list[AnhangItem])
async def produkte_im_chat(
    conversation_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AnhangItem]:
    import sqlalchemy as sa
    from app.db.models import ChatArtifact

    await _eigener_chat(db, conversation_id, current_user)
    zeilen = (await db.execute(
        sa.select(Artifact, ChatArtifact.added_at)
        .join(ChatArtifact, ChatArtifact.artifact_id == Artifact.id)
        .where(ChatArtifact.chat_id == conversation_id,
               Artifact.owner_pseudonym == current_user.sub)
        .order_by(ChatArtifact.added_at, Artifact.id)
    )).all()
    return [_anhang(r, added) for r, added in zeilen]


@router.post("/chats/{conversation_id}", response_model=AnhangItem, status_code=201)
async def produkt_anhaengen(
    conversation_id: UUID,
    req: AnhangRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnhangItem:
    """Ein eigenes Produkt an einen eigenen Chat hängen. Zweimal dasselbe: kein zweiter Eintrag."""
    from app.db.models import ChatArtifact

    await _eigener_chat(db, conversation_id, current_user)
    r = await _eigenes_artefakt(db, req.artifact_id, current_user)
    if not im_chat.ist_anhaengbar(r):
        raise HTTPException(
            status_code=422,
            detail="Dieses Produkt lässt sich nicht im Chat verwenden — möglich sind Dokumente und Diagramme.",
        )
    vorhanden = await db.get(ChatArtifact, (conversation_id, r.id))
    if vorhanden is None:
        vorhanden = ChatArtifact(chat_id=conversation_id, artifact_id=r.id)
        db.add(vorhanden)
        await db.commit()
        await db.refresh(vorhanden)
    return _anhang(r, vorhanden.added_at)


@router.delete("/chats/{conversation_id}/{artifact_id}", status_code=204)
async def produkt_abhaengen(
    conversation_id: UUID,
    artifact_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    from app.db.models import ChatArtifact

    await _eigener_chat(db, conversation_id, current_user)
    eintrag = await db.get(ChatArtifact, (conversation_id, artifact_id))
    if eintrag is None:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    await db.delete(eintrag)
    await db.commit()
    return Response(status_code=204)


@router.get("", response_model=LibraryResponse)
async def list_library(
    group_id: int | None = Query(
        default=None, description="nur Produkte im Fach dieser Unterrichtsgruppe"
    ),
    subject_id: int | None = Query(
        default=None, description="nur Produkte dieses Fachs"
    ),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200, description="Suche in Titel und Inhalt"),
    art: str | None = Query(default=None, description="image | diagram | document | file"),
    topic: str | None = Query(default=None, max_length=100),
    bald_ablaufend: bool = Query(default=False, description=f"Frist in höchstens {store.BALD_TAGE} Tagen"),
    als_baustein: bool = Query(default=False, description="als Baustein übernommen"),
    sort: str = Query(default="created", pattern="^(updated|created|title)$"),
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LibraryResponse:
    """Die eigene Werkstatt + Belegung/Quota für die Anzeige.

    Seit 0.41 mit Suche, Filtern, Sortierung und Blättern. Die Vorgabe-Sortierung bleibt
    „zuletzt angelegt“ — so liest die Gruppenseite „zuletzt entstanden“; die Werkstatt
    schickt ihre eigene Wahl mit.

    `group_id`/`subject_id` verengen auf ein Fach (die Gruppe über ihr Fach), siehe
    :func:`app.artifacts.store.list_artifacts`.

    **`used_bytes` und `quota_bytes` bleiben dabei unverfiltert.** Sie beschreiben die
    Belegung der *ganzen* Bibliothek, nicht die des Auszugs; eine mitgefilterte
    Belegungsanzeige beantwortete eine Frage, die niemand stellt („wie viel Platz
    belegen meine Mathe-Artefakte?"), und verwirrte bei der, die zählt.
    """
    if art is not None and art not in produkte.WERKSTATT_ARTEN:
        raise HTTPException(status_code=422, detail="Unbekannte Art")
    filter_ = store.Filter(
        group_id=group_id, subject_id=subject_id, q=(q or "").strip() or None,
        kinds=tuple(produkte.kinds_der_art(art)) if art else (),
        topic=topic, bald_ablaufend=bald_ablaufend, als_baustein=als_baustein,
    )
    records = await store.list_artifacts(
        db, current_user.sub, filter_=filter_, sort=sort, limit=limit, offset=offset
    )
    total = await store.count_artifacts(db, current_user.sub, filter_)
    faecher, themen = await store.facetten(db, current_user.sub)
    used = await store.used_bytes(db, current_user.sub)
    _, quota_bytes = get_artifact_limits(current_user.roles, current_user.grade)
    # Eine Abfrage für alle Karten, nicht eine je Karte.
    bausteine = await uebernahme.bausteine_zu_artefakten(
        db, artifact_ids=[r.id for r in records], pseudonym=current_user.sub
    )
    exporte_je_dokument: dict[UUID, list[ExportItem]] = {}
    for kind_ in await store.exporte_zu(db, [r.id for r in records if r.kind == "document"]):
        exporte_je_dokument.setdefault(kind_.derived_from, []).append(ExportItem(
            id=kind_.id, kind=kind_.kind, mime_type=kind_.mime_type, title=kind_.title,
            byte_size=kind_.byte_size, created_at=kind_.created_at,
        ))

    def _item(r: Artifact) -> ArtifactItem:
        baustein = bausteine.get(str(r.id))
        return ArtifactItem(
            id=r.id, kind=r.kind, mime_type=r.mime_type, title=r.title,
            byte_size=r.byte_size, source=r.source,
            created_at=r.created_at, expires_at=r.expires_at,
            provider_model=r.provider_model,
            subject_id=r.subject_id, topic=r.topic, updated_at=r.updated_at,
            assistant_name=r.assistant_name,
            exporte=exporte_je_dokument.get(r.id, []),
            uebernehmbar=uebernahme.uebernehmbar_fuer(r, current_user.roles),
            baustein_id=baustein.id if baustein else None,
            baustein_titel=baustein.title if baustein else None,
        )

    return LibraryResponse(
        items=[_item(r) for r in records], used_bytes=used, quota_bytes=quota_bytes,
        total=total, faecher=faecher, themen=themen,
    )


# ── Text-Dokumente (Material-Werkstatt, Phase 19) ─────────────────────────────

@router.post("/document", response_model=SavedArtifact)
async def create_document(
    req: DocumentCreateRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedArtifact:
    """Legt ein neues Markdown-Dokument an (leer oder aus dem Chat promotet).

    Aus dem Chat übernommene Dokumente sind über die Nachricht idempotent: Ein zweiter
    Klick liefert dasselbe Dokument (`created=False`), kein zweites.
    """
    origin_ref = store.document_origin_ref(req.message_id)
    # Herkunft vom Backend: Eine mitgeschickte `origin_conversation_id` gilt nur, wenn die
    # Konversation der Nutzer:in gehört (bis 0.41 wurde sie ungeprüft gespeichert).
    quelle = await promote.herkunft(
        db, pseudonym=current_user.sub,
        message_id=req.message_id, conversation_id=req.origin_conversation_id,
    )
    created = origin_ref is None or (
        await store.find_by_origin_ref(db, current_user.sub, origin_ref) is None
    )
    try:
        artifact = await store.create_document(
            db,
            owner_pseudonym=current_user.sub,
            roles=current_user.roles,
            grade=current_user.grade,
            title=req.title,
            markdown=req.markdown,
            origin_ref=origin_ref,
            origin_conversation_id=quelle.conversation_id,
            provider_model=quelle.provider_model,
            subject_id=quelle.subject_id,
            assistant_name=quelle.assistant_name,
        )
    except store.QuotaExceeded:
        raise HTTPException(
            status_code=409,
            detail="Deine Werkstatt ist voll. Bitte lösche zuerst ältere Produkte.",
        )
    return _saved(artifact, created)


@router.get("/{artifact_id}/document", response_model=DocumentResponse)
async def get_document(
    artifact_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Lädt ein Dokument zum Bearbeiten (Quelle = Markdown)."""
    record = await store.get_artifact(db, artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
    if record.owner_pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    if record.kind != "document":
        raise HTTPException(status_code=422, detail="Kein Text-Dokument")
    return DocumentResponse(
        id=record.id, title=record.title, kind=record.kind, source=record.source or "",
        byte_size=record.byte_size, created_at=record.created_at, expires_at=record.expires_at,
    )


@router.patch("/{artifact_id}", response_model=AngabenAntwort)
async def update_angaben(
    artifact_id: UUID,
    req: AngabenUpdate,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AngabenAntwort:
    """Titel, Fach, Thema eines Produkts ändern — jede Art, nur die Eigentümer:in (0.41)."""
    record = await store.get_artifact(db, artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
    if record.owner_pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    gesendet = req.model_fields_set
    if "subject_id" in gesendet and req.subject_id is not None:
        from app.db.models import Subject

        if await db.get(Subject, req.subject_id) is None:
            raise HTTPException(status_code=422, detail="Unbekanntes Fach")
    try:
        record = await store.update_angaben(
            db, record, **{feld: getattr(req, feld) for feld in gesendet},
            roles=current_user.roles, grade=current_user.grade,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return AngabenAntwort(
        id=record.id, title=record.title, subject_id=record.subject_id, topic=record.topic,
        updated_at=record.updated_at, expires_at=record.expires_at,
    )


@router.put("/{artifact_id}", response_model=SavedArtifact)
async def update_document(
    artifact_id: UUID,
    req: DocumentUpdateRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedArtifact:
    """Überschreibt ein Dokument (nur die Eigentümer:in, nur `kind='document'`)."""
    record = await store.get_artifact(db, artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
    if record.owner_pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    if record.kind != "document":
        raise HTTPException(status_code=422, detail="Kein Text-Dokument")
    try:
        artifact = await store.update_document(
            db, record=record, roles=current_user.roles, grade=current_user.grade,
            title=req.title, markdown=req.markdown,
        )
    except store.QuotaExceeded:
        raise HTTPException(
            status_code=409,
            detail="Deine Werkstatt ist voll. Bitte lösche zuerst ältere Produkte.",
        )
    return _saved(artifact, False)


@router.post("/{artifact_id}/export")
async def export_document(
    artifact_id: UUID,
    format: str = Query(..., pattern="^(pdf|docx|odt)$"),
    save: bool = Query(False),
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Exportiert ein Dokument (PDF via weasyprint, DOCX/ODT via Pandoc).

    `save=false` → Datei-Download; `save=true` → zusätzlich als `export_*`-Artefakt ablegen
    (Antwort dann JSON mit den Artefakt-Metadaten).
    """
    record = await store.get_artifact(db, artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
    if record.owner_pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    if record.kind != "document":
        raise HTTPException(status_code=422, detail="Kein Text-Dokument")

    # Schulweite Vorlagen (Schritt 6): CSS für PDF, reference-doc für DOCX/ODT.
    extra_css = await export_templates.get_export_css(db) if format == "pdf" else ""
    ref = export_templates.vorlage(format)

    # Herkunftszeile — schulweit abschaltbar, und nur wenn ein Modell bekannt ist.
    herkunft = None
    if await export_templates.get_export_provenance(db):
        herkunft = doc_export.herkunftszeile(
            werkzeug=settings.public_school_name or settings.export_school_name or None,
            modell=zitiername(record.provider_model),
            zeitpunkt=record.created_at.strftime("%d.%m.%Y") if record.created_at else None,
        )
    try:
        data, mime = await doc_export.export_document(
            db, markdown=record.source or "", title=record.title, fmt=format,
            reference_doc=ref, extra_css=extra_css,
            herkunft=herkunft,
        )
    except pandoc.PandocUnavailable:
        raise HTTPException(status_code=503, detail="Office-Export ist auf diesem Server nicht verfügbar.")
    except pandoc.PandocError as exc:
        raise HTTPException(status_code=422, detail=f"Export fehlgeschlagen: {exc}")

    if save:
        # Erst die Frist des Dokuments (Schritt 6), dann der Export — `save_artifact` schreibt
        # beides in einem Zug fest.
        store.frist_erneuern(record, current_user.roles, current_user.grade)
        try:
            artifact = await store.save_artifact(
                db,
                owner_pseudonym=current_user.sub,
                roles=current_user.roles,
                grade=current_user.grade,
                kind=f"export_{format}",
                mime_type=mime,
                data=data,
                title=record.title,
                source=None,
                origin_ref=None,
                # Der Export hängt am Dokument (0.41, F5): Die Werkstatt zeigt ihn dort, und er
                # geht mit ihm. Fach und Thema wie das Dokument.
                derived_from=record.id,
                subject_id=record.subject_id,
            )
        except store.QuotaExceeded:
            raise HTTPException(
                status_code=409,
                detail="Deine Werkstatt ist voll. Bitte lösche zuerst ältere Produkte.",
            )
        return JSONResponse(jsonable_encoder(_saved(artifact, True)))

    # Exportieren heißt benutzen (Schritt 6): Die Frist des Dokuments erneuert sich.
    store.frist_erneuern(record, current_user.roles, current_user.grade)
    await db.commit()

    filename = f"{_slug(record.title, 'dokument')}.{format}"
    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Übernahme in den Wissensgraphen (AP8) ────────────────────────────────────


class BausteinVorschlag(BaseModel):
    """Was sich aus diesem Artefakt machen lässt — Grundlage des Übernahme-Formulars."""

    kind: str
    uebernehmbar: bool
    grund: str | None = None            # gesetzt, wenn `uebernehmbar` false ist
    typen: list[str]                    # Bausteinarten, die diese Rolle wählen darf
    vorgabe_typ: str | None = None
    scopes_erzwungen: list[str] | None = None   # [read, write] bei Schüler:innen
    # Der bereits übernommene Baustein — dann heißt der Knopf „Baustein aktualisieren".
    vorhandener_baustein_id: UUID | None = None
    vorhandener_baustein_titel: str | None = None


class BausteinRequest(BaseModel):
    content_type: str
    title: str | None = None
    read_scope: str | None = None
    write_scope: str | None = None
    read_scope_group_id: int | None = None
    write_scope_group_id: int | None = None
    subject_id: int | None = None
    valid_until: date | None = None
    schuljahr: str | None = None


class BausteinAntwort(BaseModel):
    node_id: UUID
    title: str
    content_type: str
    # Die abgelöste Fassung: archiviert und per `supersedes` mit der neuen verbunden.
    ersetzt_node_id: UUID | None = None
    # False ⇒ es gab den Baustein schon und nichts hat sich geändert (idempotent).
    created: bool


async def _eigenes_artefakt(
    db: AsyncSession, artifact_id: UUID, current_user: JwtPayload
) -> Artifact:
    record = await store.get_artifact(db, artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
    if record.owner_pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    return record


# ── Produktansicht (0.41, Schritt 8) ──────────────────────────────────────────


class ProduktInfo(ArtifactItem):
    """Alles, was die Produktansicht `/workshop/<id>` braucht — ohne die Bytes."""

    # Herkunft: Der Chat ist nur verlinkbar, solange es ihn gibt (93 Tage).
    origin_conversation_id: UUID | None = None
    chat_vorhanden: bool = False
    # Ursprungsprodukt, etwa das Dokument eines Exports.
    derived_from: UUID | None = None
    derived_from_title: str | None = None


@router.get("/{artifact_id}/info", response_model=ProduktInfo)
async def produkt_info(
    artifact_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProduktInfo:
    """Angaben eines Produkts für die Produktansicht — nur die Eigentümer:in."""
    from app.db.models import Conversation

    r = await _eigenes_artefakt(db, artifact_id, current_user)
    baustein = await uebernahme.vorhandener_baustein(db, artifact_id=r.id, pseudonym=current_user.sub)
    exporte = [
        ExportItem(id=e.id, kind=e.kind, mime_type=e.mime_type, title=e.title,
                   byte_size=e.byte_size, created_at=e.created_at)
        for e in await store.exporte_zu(db, [r.id])
    ] if r.kind == "document" else []
    chat_vorhanden = False
    if r.origin_conversation_id is not None:
        conv = await db.get(Conversation, r.origin_conversation_id)
        chat_vorhanden = conv is not None and conv.pseudonym == current_user.sub
    ursprung = await store.get_artifact(db, r.derived_from) if r.derived_from else None
    return ProduktInfo(
        id=r.id, kind=r.kind, mime_type=r.mime_type, title=r.title, byte_size=r.byte_size,
        source=r.source, created_at=r.created_at, expires_at=r.expires_at,
        provider_model=r.provider_model, subject_id=r.subject_id, topic=r.topic,
        updated_at=r.updated_at, assistant_name=r.assistant_name, exporte=exporte,
        uebernehmbar=uebernahme.uebernehmbar_fuer(r, current_user.roles),
        baustein_id=baustein.id if baustein else None,
        baustein_titel=baustein.title if baustein else None,
        origin_conversation_id=r.origin_conversation_id if chat_vorhanden else None,
        chat_vorhanden=chat_vorhanden,
        derived_from=r.derived_from,
        derived_from_title=ursprung.title if ursprung else None,
    )


@router.post("/{artifact_id}/kopie", response_model=SavedArtifact)
async def als_kopie_speichern(
    artifact_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedArtifact:
    """„Als Kopie speichern“ — ein neues Dokument mit gleichem Inhalt und gleichen Angaben.

    Nur Dokumente (die einzige Art, die sich bisher bearbeiten lässt). Die Kopie hat keine
    Herkunft aus einer Nachricht (`origin_ref`): Sonst führte ein zweites „Als Dokument
    bearbeiten“ im Chat in die Kopie statt ins Original. Exporte gehen nicht mit.
    """
    r = await _eigenes_artefakt(db, artifact_id, current_user)
    if r.kind != "document":
        raise HTTPException(status_code=422, detail="Nur Dokumente lassen sich als Kopie speichern")
    try:
        kopie = await store.create_document(
            db, owner_pseudonym=current_user.sub, roles=current_user.roles, grade=current_user.grade,
            title=f"{r.title} (Kopie)"[:200], markdown=r.source or "",
            origin_conversation_id=r.origin_conversation_id, provider_model=r.provider_model,
            subject_id=r.subject_id, assistant_name=r.assistant_name,
        )
        if r.topic:
            kopie = await store.update_angaben(db, kopie, topic=r.topic)
    except store.QuotaExceeded:
        raise HTTPException(
            status_code=409,
            detail="Deine Werkstatt ist voll. Bitte lösche zuerst ältere Produkte.",
        )
    return _saved(kopie, True)


@router.get("/{artifact_id}/baustein", response_model=BausteinVorschlag)
async def baustein_vorschlag(
    artifact_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Vorbelegung des Übernahme-Formulars — ohne etwas anzulegen."""
    record = await _eigenes_artefakt(db, artifact_id, current_user)

    typen = list(uebernahme.angebotene_typen(current_user.roles))
    vorhanden = await uebernahme.vorhandener_baustein(
        db, artifact_id=artifact_id, pseudonym=current_user.sub
    )
    return BausteinVorschlag(
        kind=record.kind,
        uebernehmbar=uebernahme.uebernehmbar_fuer(record, current_user.roles),
        grund=uebernahme.ablehnungsgrund(record, current_user.roles),
        typen=typen,
        # Beim zweiten Mal die Art des vorhandenen Bausteins, sonst die erste der Liste:
        # Wer aktualisiert, will fast nie die Art wechseln.
        vorgabe_typ=(vorhanden.content_type if vorhanden else (typen[0] if typen else None)),
        scopes_erzwungen=(
            list(erzwungen)
            if (erzwungen := uebernahme.erzwungene_scopes(current_user.roles))
            else None
        ),
        vorhandener_baustein_id=vorhanden.id if vorhanden else None,
        vorhandener_baustein_titel=vorhanden.title if vorhanden else None,
    )


@router.post("/{artifact_id}/baustein", response_model=BausteinAntwort, status_code=201)
async def baustein_aus_artefakt(
    artifact_id: UUID,
    req: BausteinRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """„Als Baustein speichern" — der Redaktionsakt aus Bibliothek und Chat (AP8).

    **Warum ein eigener Endpunkt statt `POST /context/nodes`.** Der generische Weg ist
    teacher/admin und nimmt jede Bausteinart und jede Sichtbarkeit entgegen. Schüler:innen
    sollen hier durchkommen — aber nur mit ihren vier Arten und nur `private`. Denselben
    Endpunkt dafür zu öffnen hieße, den Rollenriegel gegen eine Sammlung von
    Sonderfällen einzutauschen; derselbe Schnitt wie bei `PATCH /nodes/{id}/verwalten`.
    """
    record = await _eigenes_artefakt(db, artifact_id, current_user)

    try:
        node, ersetzt, angelegt = await uebernahme.uebernimm(
            db,
            user=current_user,
            artifact=record,
            content_type=req.content_type,
            title=req.title,
            read_scope=req.read_scope,
            write_scope=req.write_scope,
            read_scope_group_id=req.read_scope_group_id,
            write_scope_group_id=req.write_scope_group_id,
            subject_id=req.subject_id,
            valid_until=req.valid_until,
            schuljahr=req.schuljahr,
        )
    except uebernahme.UebernahmeFehler as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))

    # Übernehmen heißt benutzen (Schritt 6): Das Produkt bleibt so lange wie ein frisch
    # bearbeitetes.
    store.frist_erneuern(record, current_user.roles, current_user.grade)
    await db.commit()
    await db.refresh(node)
    await enqueue_embedding_job(node.id, db)

    return BausteinAntwort(
        node_id=node.id,
        title=node.title,
        content_type=node.content_type,
        ersetzt_node_id=ersetzt.id if ersetzt else None,
        created=angelegt,
    )


@router.get("/{artifact_id}")
async def get_artifact_file(
    artifact_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Liefert die Artefakt-Bytes — nur an die Eigentümer:in (Pseudonym-Autorisierung)."""
    record = await store.get_artifact(db, artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
    if record.owner_pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    data = store.read_artifact_bytes(record)
    if data is None:
        raise HTTPException(status_code=404, detail="Datei des Produkts nicht gefunden")
    headers = _SVG_HARDENING if record.mime_type == "image/svg+xml" else None
    return Response(content=data, media_type=record.mime_type, headers=headers)


@router.delete("/{artifact_id}")
async def delete_artifact_endpoint(
    artifact_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Löscht ein Produkt samt seinen Exporten (Zeilen und Dateien) — nur die Eigentümer:in."""
    record = await store.get_artifact(db, artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
    if record.owner_pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    mitgeloescht = await store.delete_artifact(db, record)
    return {"ok": True, "mitgeloescht": mitgeloescht}


@router.post("/ggb")
async def ggb_from_source(
    req: GgbRequest,
    _: JwtPayload = Depends(get_current_user),
) -> Response:
    """Konvertiert eine rohe Plot-Spec direkt in eine `.ggb`-Datei (Download im Chat).

    Zustandslos (kein Persistenzbezug) — nur eingeloggt. 422 bei ungültiger Plot-Spec.
    """
    try:
        data = geogebra.ggb_bytes_from_source(req.source)
    except RenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _ggb_response(data, req.title)


@router.get("/{artifact_id}/ggb")
async def ggb_from_artifact(
    artifact_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """`.ggb`-Export eines gespeicherten Plot-Artefakts (aus dessen `source`)."""
    record = await store.get_artifact(db, artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
    if record.owner_pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    if record.kind != "plot" or not record.source:
        raise HTTPException(status_code=422, detail="Kein GeoGebra-Export für dieses Produkt")
    try:
        data = geogebra.ggb_bytes_from_source(record.source)
    except RenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _ggb_response(data, record.title)
