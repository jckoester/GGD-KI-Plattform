"""Persistenz-Store der Artefaktbibliothek (Phase 18).

Bytes auf Disk (`settings.artifact_storage_dir`), Metadaten in der Tabelle `artifacts`.
Speichern prüft die Per-User-Quota und friert `expires_at` aus der role-/jahrgangsbasierten
Aufbewahrung ein (kein Rollen-Lookup im Cleanup nötig). Muster analog `app/chat/image_store.py`.
"""
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.artifacts.limits import get_artifact_limits
from app.config import settings
from app.core.paths import aufloesen
from app.db.models import Artifact

logger = logging.getLogger(__name__)


_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "application/vnd.geogebra.file": ".ggb",
    "text/markdown": ".md",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.oasis.opendocument.text": ".odt",
    "application/pdf": ".pdf",
}

DOCUMENT_MIME = "text/markdown"


class QuotaExceeded(Exception):
    """Die Bibliothek der Nutzer:in ist voll (Quota überschritten)."""


def storage_dir() -> Path:
    """Ablageverzeichnis (repo-root-relativ, falls nicht absolut) — cwd-unabhängig.

    Wichtig für den Cleanup-Cron: der läuft nicht aus dem Backend-Verzeichnis, muss aber
    denselben Pfad auflösen wie das Backend beim Speichern (analog `image_store`)."""
    d = aufloesen(settings.artifact_storage_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file_path(artifact_id: UUID, mime_type: str) -> Path:
    return storage_dir() / f"{artifact_id}{_EXT_BY_MIME.get(mime_type, '.bin')}"


def _now(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now(timezone.utc)


async def used_bytes(db: AsyncSession, owner_pseudonym: str) -> int:
    """Aktuell belegte Gesamtgröße der Bibliothek dieser Nutzer:in."""
    result = await db.execute(
        select(func.coalesce(func.sum(Artifact.byte_size), 0)).where(
            Artifact.owner_pseudonym == owner_pseudonym
        )
    )
    return int(result.scalar_one())


async def find_by_origin_ref(
    db: AsyncSession, owner_pseudonym: str, origin_ref: str
) -> Optional[Artifact]:
    """Bereits gespeichertes Artefakt gleicher Herkunft (Idempotenz von „In Bibliothek speichern")."""
    result = await db.execute(
        select(Artifact).where(
            Artifact.owner_pseudonym == owner_pseudonym,
            Artifact.origin_ref == origin_ref,
        )
    )
    return result.scalars().first()


async def save_artifact(
    db: AsyncSession,
    *,
    owner_pseudonym: str,
    roles: list[str],
    grade: Optional[int],
    kind: str,
    mime_type: str,
    data: bytes,
    title: str,
    source: Optional[str] = None,
    origin_ref: Optional[str] = None,
    origin_conversation_id: Optional[UUID] = None,
    provider_model: Optional[str] = None,
    subject_id: Optional[int] = None,
    assistant_name: Optional[str] = None,
    derived_from: Optional[UUID] = None,
    now: Optional[datetime] = None,
) -> Artifact:
    """Speichert ein Artefakt: Quota prüfen → Bytes auf Disk → Row mit `expires_at`.

    Idempotent über `origin_ref`: existiert bereits ein Artefakt dieser Herkunft, wird es
    unverändert zurückgegeben (kein zweiter Disk-Write, kein Quota-Verbrauch). Wirft
    `QuotaExceeded`, wenn die Bibliothek der Nutzer:in durch das Speichern überliefe.
    """
    # Idempotenz: gleiche Herkunft → bestehendes Artefakt, ohne erneut zu schreiben.
    if origin_ref is not None:
        existing = await find_by_origin_ref(db, owner_pseudonym, origin_ref)
        if existing is not None:
            return existing

    retention_days, quota_bytes = get_artifact_limits(roles, grade)
    size = len(data)
    used = await used_bytes(db, owner_pseudonym)
    if used + size > quota_bytes:
        raise QuotaExceeded(
            f"Bibliothek voll: {used + size} > {quota_bytes} Bytes"
        )

    artifact_id = uuid4()
    _file_path(artifact_id, mime_type).write_bytes(data)

    ts = _now(now)
    artifact = Artifact(
        id=artifact_id,
        owner_pseudonym=owner_pseudonym,
        kind=kind,
        mime_type=mime_type,
        byte_size=size,
        title=title,
        source=source,
        origin_ref=origin_ref,
        origin_conversation_id=origin_conversation_id,
        provider_model=provider_model,
        subject_id=subject_id,
        assistant_name=assistant_name,
        derived_from=derived_from,
        created_at=ts,
        updated_at=ts,
        expires_at=ts + timedelta(days=retention_days),
    )
    db.add(artifact)
    try:
        await db.commit()
    except IntegrityError:
        # Wettlauf (Doppelklick): der Unique-Index hat den zweiten Insert verhindert.
        # Datei verwerfen, bestehendes Artefakt zurückgeben.
        await db.rollback()
        _file_path(artifact_id, mime_type).unlink(missing_ok=True)
        if origin_ref is not None:
            existing = await find_by_origin_ref(db, owner_pseudonym, origin_ref)
            if existing is not None:
                return existing
        raise
    return artifact


async def get_artifact(db: AsyncSession, artifact_id: UUID) -> Optional[Artifact]:
    return await db.get(Artifact, artifact_id)


def _clean_title(title: Optional[str]) -> str:
    return (title or "").strip()[:200] or "Dokument"


def document_origin_ref(message_id: Optional[UUID]) -> Optional[str]:
    """Herkunftsschlüssel eines aus einer Chatnachricht übernommenen Dokuments.

    ``None`` für ein leer angelegtes Dokument: Zweimal „Neues Dokument" soll **zwei**
    leere Dokumente ergeben, nicht zweimal dasselbe.
    """
    return f"message:{message_id}" if message_id is not None else None


async def create_document(
    db: AsyncSession,
    *,
    owner_pseudonym: str,
    roles: list[str],
    grade: Optional[int],
    title: str,
    markdown: str,
    origin_ref: Optional[str] = None,
    origin_conversation_id: Optional[UUID] = None,
    provider_model: Optional[str] = None,
    subject_id: Optional[int] = None,
    assistant_name: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Artifact:
    """Legt ein Text-Dokument (`kind='document'`, Markdown) an.

    Dokumente sind **veränderbar** — deshalb ist `origin_ref` hier kein Inhalts-Hash wie
    bei Diagrammen, sondern die **Herkunft** (`message:<id>`, siehe
    `document_origin_ref`). Die bleibt über jede Bearbeitung stabil, und genau das ist
    gewollt: Ein zweiter Klick auf „Als Dokument bearbeiten" oder „Als Baustein speichern"
    führt zurück in das vorhandene Dokument — mitsamt der bereits daran gemachten
    Änderungen — statt ein zweites anzulegen. Ein zweites hieße bei „Als Baustein
    speichern" ein zweiter Knoten statt einer neuen Fassung.
    """
    return await save_artifact(
        db,
        owner_pseudonym=owner_pseudonym,
        roles=roles,
        grade=grade,
        kind="document",
        mime_type=DOCUMENT_MIME,
        data=markdown.encode("utf-8"),
        title=_clean_title(title),
        source=markdown,
        origin_ref=origin_ref,
        origin_conversation_id=origin_conversation_id,
        provider_model=provider_model,
        subject_id=subject_id,
        assistant_name=assistant_name,
        now=now,
    )


def frist_erneuern(record: Artifact, roles: list[str], grade: Optional[int],
                   now: Optional[datetime] = None) -> None:
    """Wer ein Produkt benutzt, behält es (0.41, Schritt 6): Frist = jetzt + Aufbewahrung.

    Auslöser: Inhalt ändern, Angaben ändern, exportieren, als Baustein übernehmen. Nie
    kürzer als bisher — sinkt die Aufbewahrung in `artifact_limits.yaml`, soll ein
    Benutzen die Frist nicht vorziehen. Schreibt nicht fest; das tut der Aufrufer.
    """
    retention_days, _ = get_artifact_limits(roles, grade)
    neu = _now(now) + timedelta(days=retention_days)
    if record.expires_at is None or neu > record.expires_at:
        record.expires_at = neu


async def update_document(
    db: AsyncSession,
    *,
    record: Artifact,
    roles: list[str],
    grade: Optional[int],
    title: str,
    markdown: str,
    now: Optional[datetime] = None,
) -> Artifact:
    """Überschreibt ein Dokument in-place (Quelle/Bytes/Titel). Aufbewahrung wird bei aktiver
    Bearbeitung erneuert (`expires_at = now + retention`), Quota unter Abzug der alten Größe geprüft."""
    data = markdown.encode("utf-8")
    new_size = len(data)
    retention_days, quota_bytes = get_artifact_limits(roles, grade)
    used = await used_bytes(db, record.owner_pseudonym)
    if used - record.byte_size + new_size > quota_bytes:
        raise QuotaExceeded(
            f"Bibliothek voll: {used - record.byte_size + new_size} > {quota_bytes} Bytes"
        )

    _file_path(record.id, record.mime_type).write_bytes(data)
    ts = _now(now)
    record.title = _clean_title(title)
    record.source = markdown
    record.byte_size = new_size
    frist_erneuern(record, roles, grade, ts)
    record.updated_at = ts
    await db.commit()
    return record


#: Wie lang ein Thema sein darf — ein Stichwort, kein Text.
THEMA_MAX = 100

_UNVERAENDERT = object()


async def update_angaben(
    db: AsyncSession,
    record: Artifact,
    *,
    title=_UNVERAENDERT,
    subject_id=_UNVERAENDERT,
    topic=_UNVERAENDERT,
    roles: Optional[list[str]] = None,
    grade: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Artifact:
    """Titel, Fach, Thema eines Produkts ändern — für alle Arten (0.41, Schritt 3).

    Nur, was übergeben wird, ändert sich; ``None`` bei Fach oder Thema heißt „entfernen“.
    Ein leerer Titel ist nicht erlaubt (``ValueError``), ein leeres Thema heißt „keins“.
    Prüfen, ob das Produkt der Person gehört und das Fach existiert, ist Sache des Aufrufers.
    Mit ``roles`` erneuert sich die Frist (Schritt 6) — wer ordnet, benutzt.
    """
    if title is not _UNVERAENDERT:
        neu = (title or "").strip()[:200]
        if not neu:
            raise ValueError("Der Titel darf nicht leer sein.")
        record.title = neu
    if subject_id is not _UNVERAENDERT:
        record.subject_id = subject_id
    if topic is not _UNVERAENDERT:
        record.topic = (topic or "").strip()[:THEMA_MAX] or None
    record.updated_at = _now(now)
    if roles is not None:
        frist_erneuern(record, roles, grade, now)
    await db.commit()
    return record


async def eigene_themen(
    db: AsyncSession, owner_pseudonym: str, *, subject_id: int | None = None, limit: int = 50
) -> list[str]:
    """Die eigenen Themen, zuletzt benutzte zuerst — wahlweise nur in einem Fach."""
    zuletzt = sa.func.max(Artifact.updated_at)
    stmt = (
        select(Artifact.topic)
        .where(Artifact.owner_pseudonym == owner_pseudonym, Artifact.topic.is_not(None))
        .group_by(Artifact.topic)
        .order_by(zuletzt.desc(), Artifact.topic)
        .limit(limit)
    )
    if subject_id is not None:
        stmt = stmt.where(Artifact.subject_id == subject_id)
    return list((await db.execute(stmt)).scalars())


#: „Läuft bald ab“: Frist in höchstens so vielen Tagen.
BALD_TAGE = 30

#: Sortierungen der Werkstatt-Liste.
SORTIERUNGEN = ("updated", "created", "title")


@dataclass(frozen=True)
class Filter:
    """Was die Werkstatt-Liste eingrenzt (0.41, Schritt 4). Alles UND-verknüpft."""

    group_id: int | None = None
    subject_id: int | None = None
    q: str | None = None
    kinds: tuple[str, ...] = ()
    topic: str | None = None
    bald_ablaufend: bool = False
    als_baustein: bool = False


def _bedingungen(owner_pseudonym: str, f: Filter, now: datetime) -> list:
    # Lokale Importe: `Group`/`ContextNode` werden nur hier gebraucht.
    from app.db.models import ContextNode, Group

    # Abgeleitete Produkte (Exporte) stehen nicht für sich in der Liste, sondern an ihrem
    # Dokument (0.41, F5). Exporte aus der Zeit davor tragen keinen Verweis und bleiben sichtbar.
    wo = [Artifact.owner_pseudonym == owner_pseudonym, Artifact.derived_from.is_(None)]
    if f.group_id is not None:
        fach_der_gruppe = select(Group.subject_id).where(Group.id == f.group_id).scalar_subquery()
        wo.append(Artifact.subject_id == fach_der_gruppe)
    if f.subject_id is not None:
        wo.append(Artifact.subject_id == f.subject_id)
    if f.q:
        muster = "%" + f.q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        wo.append(sa.or_(Artifact.title.ilike(muster, escape="\\"),
                         Artifact.source.ilike(muster, escape="\\")))
    if f.kinds:
        wo.append(Artifact.kind.in_(f.kinds))
    if f.topic is not None:
        wo.append(Artifact.topic == f.topic)
    if f.bald_ablaufend:
        wo.append(Artifact.expires_at <= now + timedelta(days=BALD_TAGE))
    if f.als_baustein:
        wo.append(sa.exists().where(
            ContextNode.owner_pseudonym == owner_pseudonym,
            ContextNode.status == "active",
            ContextNode.metadata_["source_artifact_id"].astext == sa.cast(Artifact.id, sa.Text),
        ))
    return wo


_REIHENFOLGE = {
    "updated": (Artifact.updated_at.desc(), Artifact.id),
    "created": (Artifact.created_at.desc(), Artifact.id),
    "title": (sa.func.lower(Artifact.title), Artifact.id),
}


async def list_artifacts(
    db: AsyncSession,
    owner_pseudonym: str,
    *,
    group_id: int | None = None,
    subject_id: int | None = None,
    filter_: Filter | None = None,
    sort: str = "created",
    limit: int | None = None,
    offset: int = 0,
    now: Optional[datetime] = None,
) -> list[Artifact]:
    """Die eigene Werkstatt — wahlweise eingegrenzt und sortiert.

    **Woher der Fachbezug kommt (seit 0.41).** Das Produkt trägt ein eigenes Fach
    (`subject_id`, Alembic 0103): beim Speichern aus dem Chat kopiert, danach änderbar. Bis
    0.40 kam der Bezug allein über den Herkunfts-Chat — und fiel weg, sobald der nach
    spätestens 93 Tagen gelöscht war.

    **Gruppe heißt Fach der Gruppe** (Plan 0.41, F3 a). Ein Produkt gehört keiner Gruppe —
    die Werkstatt ist strikt privat, ein Gruppenbesitz wäre eine falsche Aussage. Die
    Gruppenseite zeigt deshalb die eigenen Produkte des Fachs; eine Lehrkraft mit mehreren
    Gruppen im selben Fach sieht dort dasselbe (das Thema unterscheidet bei Bedarf). Eine
    Gruppe ohne Fach liefert nichts.

    Ohne Fach (etwa ein leer angelegtes Dokument) erscheint ein Produkt in keinem Auszug,
    nur in der vollen Werkstatt. Der Eigentümerfilter steht immer davor: Fremde Produkte
    sind auch dann unerreichbar, wenn ihr Fach passt.

    ``group_id``/``subject_id`` direkt sind die Kurzform der Fach- und Gruppenseiten;
    ``filter_`` ist der volle Filter der Werkstatt (beides zusammen: UND).
    """
    f = filter_ or Filter()
    if group_id is not None:
        f = replace(f, group_id=group_id)
    if subject_id is not None:
        f = replace(f, subject_id=subject_id)
    stmt = (
        select(Artifact)
        .where(*_bedingungen(owner_pseudonym, f, _now(now)))
        .order_by(*_REIHENFOLGE.get(sort, _REIHENFOLGE["created"]))
        .offset(offset)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def count_artifacts(
    db: AsyncSession, owner_pseudonym: str, filter_: Filter | None = None,
    now: Optional[datetime] = None,
) -> int:
    """Wie viele Produkte der Filter trifft — für „12 von 40“ und „Mehr laden“."""
    stmt = select(func.count()).select_from(Artifact).where(
        *_bedingungen(owner_pseudonym, filter_ or Filter(), _now(now))
    )
    return (await db.execute(stmt)).scalar_one()


async def facetten(db: AsyncSession, owner_pseudonym: str) -> tuple[list[int], list[str]]:
    """Fächer und Themen, die in der eigenen Werkstatt vorkommen — die Auswahl der Filter.

    Über den **ganzen** Bestand, nicht über den gefilterten: Sonst verschwände ein Fach aus
    der Auswahl, sobald man ein anderes gewählt hat.
    """
    faecher = (await db.execute(
        select(Artifact.subject_id).where(
            Artifact.owner_pseudonym == owner_pseudonym, Artifact.subject_id.is_not(None)
        ).distinct()
    )).scalars().all()
    themen = (await db.execute(
        select(Artifact.topic).where(
            Artifact.owner_pseudonym == owner_pseudonym, Artifact.topic.is_not(None)
        ).distinct().order_by(Artifact.topic)
    )).scalars().all()
    return sorted(faecher), list(themen)


def read_artifact_bytes(record: Artifact) -> Optional[bytes]:
    path = _file_path(record.id, record.mime_type)
    if not path.exists():
        return None
    return path.read_bytes()


async def collect_pseudonym_artifact_paths(
    db: AsyncSession, pseudonym: str
) -> list[Path]:
    """Dateipfade aller Artefakte einer Person — für die Kontolöschung.

    Getrennt vom Löschen, weil die Reihenfolge zählt: Die Pfade werden **vor** der
    Transaktion gesammelt und die Dateien erst **nach** einem erfolgreichen Commit
    entfernt. Andersherum — wie in `delete_artifact` und `cleanup_artifacts`, wo es
    wegen der einzelnen Zeile folgenlos bleibt — stünde bei einem Rollback eine Zeile
    ohne ihre Datei in der Datenbank.
    """
    zeilen = (await db.execute(
        select(Artifact.id, Artifact.mime_type)
        .where(Artifact.owner_pseudonym == pseudonym)
    )).all()
    return [_file_path(artifact_id, mime_type) for artifact_id, mime_type in zeilen]


async def abgeleitete(db: AsyncSession, artifact_ids) -> list[tuple[UUID, str, UUID]]:
    """(id, mime_type, derived_from) der Produkte, die von diesen abgeleitet sind — etwa die
    Exporte eines Dokuments (0.41, F5).

    Eine Ebene genügt: Abgeleitet wird bislang nur aus Dokumenten, und ein Export hat
    selbst keine Exporte.
    """
    ids = list(artifact_ids)
    if not ids:
        return []
    return [tuple(z) for z in (await db.execute(
        select(Artifact.id, Artifact.mime_type, Artifact.derived_from)
        .where(Artifact.derived_from.in_(ids))
    )).all()]


async def exporte_zu(db: AsyncSession, dokument_ids) -> list[Artifact]:
    """Die Exporte dieser Dokumente, neueste zuerst — eine Abfrage für die ganze Liste."""
    ids = list(dokument_ids)
    if not ids:
        return []
    return list((await db.execute(
        select(Artifact).where(Artifact.derived_from.in_(ids))
        .order_by(Artifact.created_at.desc(), Artifact.id)
    )).scalars().all())


def _dateien_entfernen(paare) -> None:
    for artifact_id, mime_type in paare:
        try:
            _file_path(artifact_id, mime_type).unlink(missing_ok=True)
        except OSError:
            logger.warning("Artefakt-Datei nicht löschbar: %s", artifact_id)


async def delete_artifact(db: AsyncSession, record: Artifact) -> int:
    """Löscht ein Produkt samt allem, was davon abgeleitet ist; gibt deren Anzahl zurück.

    Die Zeilen der Exporte nimmt die Datenbank mit (`derived_from … ON DELETE CASCADE`,
    Alembic 0103) — **ihre Dateien nicht**. Deshalb werden sie hier vorher eingesammelt;
    sonst blieben sie verwaist auf der Platte und zählten in keiner Belegung mehr.
    """
    kinder = await abgeleitete(db, [record.id])
    _dateien_entfernen([(record.id, record.mime_type), *[(k[0], k[1]) for k in kinder]])
    await db.delete(record)
    await db.commit()
    return len(kinder)


@dataclass
class ArtifactCleanupStats:
    scanned: int
    expired_removed: int


async def cleanup_artifacts(
    db: AsyncSession, *, now: Optional[datetime] = None, dry_run: bool = False
) -> ArtifactCleanupStats:
    """Löscht abgelaufene Artefakte (`expires_at < now`) + ihre Dateien."""
    ts = _now(now)
    result = await db.execute(select(Artifact).where(Artifact.expires_at < ts))
    expired = list(result.scalars().all())
    # Was von einem abgelaufenen Produkt abgeleitet ist, geht mit (CASCADE) — auch wenn die
    # eigene Frist noch läuft. Seine Datei muss deshalb ebenfalls weg.
    abgelaufen = {a.id for a in expired}
    mitgenommen = [(k[0], k[1]) for k in await abgeleitete(db, abgelaufen) if k[0] not in abgelaufen]
    if not dry_run and expired:
        _dateien_entfernen([(a.id, a.mime_type) for a in expired] + mitgenommen)
        await db.execute(delete(Artifact).where(Artifact.expires_at < ts))
        await db.commit()
    entfernt = len(expired) + len(mitgenommen)
    return ArtifactCleanupStats(scanned=entfernt, expired_removed=entfernt)
