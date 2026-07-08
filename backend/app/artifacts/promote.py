"""Promotion von Chat-Inhalten in die persönliche Artefaktbibliothek (Phase 18, Schritt 2).

„In Bibliothek speichern" hebt einen flüchtigen Chat-Inhalt (an die Konversation gebunden,
90/93-Tage-Lifecycle) in die dauerhafte Bibliothek. Je Herkunft:

- **Bild** (`generate_image`): Bytes werden kopiert, der Bild-Prompt wandert als roher
  Quelltext (`source`) mit.
- **circuit/plot** (server-gerendert): aus dem rohen Quelltext **serverseitig neu gerendert**
  (deterministisch, nutzt den Render-Cache) — der Client-SVG wird bewusst nicht vertraut.
- **mermaid** (nur Client-Rendering verfügbar): der bereits im Browser gerenderte SVG wird
  übernommen; der rohe Quelltext (`source`) kommt mit. Die Auslieferung härtet SVGs per
  CSP/nosniff ab (siehe `router.get_artifact_file`).

Idempotenz, Eigentümer-Bindung und Quota liegen in `store.save_artifact` bzw. hier über den
`origin_ref` (Herkunftsschlüssel). Eigentümer:in ist stets die eingeloggte Nutzer:in.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.artifacts import store
from app.auth.jwt import JwtPayload
from app.chat import image_store
from app.render import service
from app.render.cache import svg_hash


class PromotionError(Exception):
    """Promotion nicht möglich (Quelle fehlt, Render-Fehler, unbekannter Typ)."""


_DIAGRAM_DEFAULT_TITLE = {
    "circuit": "Schaltplan",
    "plot": "Funktionsgraph",
    "mermaid": "Diagramm",
}
_SERVER_RENDER_KINDS = ("circuit", "plot")
DIAGRAM_KINDS = ("circuit", "plot", "mermaid")


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
) -> tuple:
    """Promotet ein gerendertes Diagramm. Gibt (Artefakt, created) zurück.

    circuit/plot werden serverseitig aus `source` neu gerendert; mermaid übernimmt den
    Client-`svg`. Wirft `PromotionError` (leere Quelle, Render-Fehler, unbekannter Typ)
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
    elif kind == "mermaid":
        if not svg or "<svg" not in svg:
            raise PromotionError("kein gerendertes Diagramm")
        svg_out = svg
    else:
        raise PromotionError(f"unbekannter Diagrammtyp: {kind}")

    origin_ref = f"{kind}:{svg_hash(kind, source)}"
    created = await store.find_by_origin_ref(db, user.sub, origin_ref) is None
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
    )
    return artifact, created
