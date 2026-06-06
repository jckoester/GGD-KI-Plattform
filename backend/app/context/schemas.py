"""Pydantic-Schemas für die Context-Nodes-API."""

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ContextNodeCreate(BaseModel):
    category: str
    content_type: str | None = None
    title: str
    content: str | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    owner_pseudonym: str | None = None
    read_scope: str = "school"
    write_scope: str = "private"
    read_scope_group_id: int | None = None
    write_scope_group_id: int | None = None
    assistant_id: int | None = None
    subject_id: int | None = None
    min_grade: int | None = None
    max_grade: int | None = None
    valid_until: date | None = None
    schuljahr: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class ContextNodeUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    read_scope: str | None = None
    write_scope: str | None = None
    read_scope_group_id: int | None = None
    write_scope_group_id: int | None = None
    subject_id: int | None = None
    min_grade: int | None = None
    max_grade: int | None = None
    valid_until: date | None = None
    schuljahr: str | None = None
    status: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class ContextNodeRead(BaseModel):
    id: UUID
    category: str
    content_type: str | None
    title: str
    content: str | None
    metadata_: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )
    owner_pseudonym: str | None
    read_scope: str
    write_scope: str
    read_scope_group_id: int | None
    write_scope_group_id: int | None
    assistant_id: int | None
    subject_id: int | None
    min_grade: int | None
    max_grade: int | None
    status: str
    valid_until: date | None
    archived_at: datetime | None
    schuljahr: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ── Context Anchor Schemas ──────────────────────────────────────────────────

from typing import Literal


class ContextAnchorCreate(BaseModel):
    node_id: UUID
    role: Literal["always_include", "retrieval_scope"]


class ContextAnchorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assistant_id: int
    node_id: UUID
    role: str
    node_title: str
    node_content_type: str | None = None


# ── KS-Phase-4 Schemas ────────────────────────────────────────────────────


class ContextEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    from_node_id: UUID
    to_node_id: UUID
    relation: str
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime


class NeighborhoodResponse(BaseModel):
    nodes: list[ContextNodeRead]
    edges: list[ContextEdgeRead]


class ArchivedReferenceRead(BaseModel):
    id: UUID
    title: str
    category: str
    content_type: str | None
    archived_at: datetime
    relation: str
    suggested_successor_id: UUID | None


class ContextNodeCopyRequest(BaseModel):
    schuljahr: str | None = None
    valid_until: date | None = None
    read_scope_group_id: int | None = None
    write_scope_group_id: int | None = None


# ── KS-Phase-5 Chat Context Nodes ────────────────────────────────────────


class ChatContextNodeAdd(BaseModel):
    node_id: UUID


class ChatContextNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: UUID
    category: str
    title: str
    content_type: str | None
    added_at: datetime


# ── KS-Phase-5 Semantic Search ──────────────────────────────────────────


class ContextSearchRequest(BaseModel):
    query: str


class ContextSearchResult(BaseModel):
    node_id: UUID
    title: str
    category: str
    content_type: str | None


# ── KS-Phase-6 Edge Schemas ─────────────────────────────────────────────


class ContextEdgeCreate(BaseModel):
    from_node_id: UUID
    to_node_id: UUID
    relation: str
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    model_config = ConfigDict(populate_by_name=True)


class ContextEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    from_node_id: UUID
    to_node_id: UUID
    relation: str
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime


# ── KS-Phase-6 Curriculum Create ─────────────────────────────────────────


class CurriculumCreate(BaseModel):
    """Schema für das Anlegen eines neuen Curriculum-Knotens über die UI.

    fachplan_node_id ist die ContextNode-UUID des fachplan-Knotens (Primärschlüssel) —
    nicht zu verwechseln mit dem Geschäftsschlüssel metadata.fachplan_id der
    Bildungsplan-Importe.
    """
    fach_code: str
    schulart: str
    jahrgangsstufe: str
    bp_version: str
    schule: str
    fachplan_node_id: str
    model_config = ConfigDict(populate_by_name=True)


# ── KS-Phase-6 Curriculum ───────────────────────────────────────────────


class CurriculumDraftEntry(BaseModel):
    """Ein einzelner Eintrag in einer Lernsequenz-Tabelle."""
    ik: str | None = None
    ik_partiell: bool = False
    pk: list[str | dict] = Field(default_factory=list)
    konkretisierung: str | None = None
    hinweise: str | None = None
    lp: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, description="Konfidenz der Extraktion (0.0-1.0)")
    warnings: list[str] = Field(default_factory=list, description="Warnungen für diesen Eintrag")


class CurriculumDraftLernsequenz(BaseModel):
    """Eine Lernsequenz im Zwischenformat."""
    bp_titel: str | None = None
    bp_leitidee: str | None = None
    reihenfolge: int | None = None
    eintraege: list[CurriculumDraftEntry] = Field(default_factory=list)
    confidence: float = Field(default=1.0, description="Konfidenz der Extraktion")
    warnings: list[str] = Field(default_factory=list)


class CurriculumDraftKapitel(BaseModel):
    """Ein Kapitel im Zwischenformat."""
    titel: str
    reihenfolge: int
    std: str | None = None
    hinweis: str | None = None
    konkretisierung: list[str] = Field(default_factory=list)
    lernsequenzen: list[CurriculumDraftLernsequenz] = Field(default_factory=list)
    confidence: float = Field(default=1.0)
    warnings: list[str] = Field(default_factory=list)
class CurriculumDraftConfirmed(BaseModel):
    """Bestätigtes Zwischenformat für die Speicherung (Stufe 2)."""
    schule: str
    fach_code: str
    fach: str | None = None
    schulart: str
    jahrgangsstufe: str
    fachplan_id: str
    bp_version: str
    vorwort: str | None = None
    kapitel: list[CurriculumDraftKapitel]


# -- KS-Phase-6 Curriculum Read Models -----------------------------------------


class LernsequenzRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    metadata_: dict = Field(
        validation_alias="metadata",
        serialization_alias="metadata",
    )
    ik_refs: list[dict]  # [{node_id, title, partiell}, ...]
    pk_refs: list[dict]  # [{node_id, title}, ...]
    leitperspektive_refs: list[dict]  # [{node_id, title, lp_code}, ...]


class KapitelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    metadata_: dict = Field(
        validation_alias="metadata",
        serialization_alias="metadata",
    )
    lernsequenzen: list[LernsequenzRead]


class CurriculumRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    metadata_: dict = Field(
        validation_alias="metadata",
        serialization_alias="metadata",
    )
    subject_id: int | None
    write_scope_group_id: int | None
    kapitel: list[KapitelRead]
    can_edit: bool


# ── Bildungsplan Hierarchie Schemas ────────────────────────────────────────


class IkKompetenzRead(BaseModel):
    """Inhaltsbezogene Kompetenz (IK) für Bildungsplan-Hierarchie."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    min_grade: int | None = None
    max_grade: int | None = None
    niveau: str = "regulär"
    metadata_: dict = Field(
        default_factory=dict,
        validation_alias="metadata",
        serialization_alias="metadata",
    )


class LeitideeRead(BaseModel):
    """Leitidee mit IK-Kompetenz-Kindern und optionalen Unter-Leitideen (rekursiv)."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    content: str | None = None
    min_grade: int | None = None
    max_grade: int | None = None
    niveau: str = "regulär"
    metadata_: dict = Field(
        default_factory=dict,
        validation_alias="metadata",
        serialization_alias="metadata",
    )
    ik_kompetenzen: list[IkKompetenzRead] = Field(default_factory=list)
    unter_leitideen: list["LeitideeRead"] = Field(default_factory=list)


LeitideeRead.model_rebuild()


class BandRead(BaseModel):
    """Ein Jahrgangsstufen-Niveau-Band, z. B. Kl. 5–6 oder Kl. 11–12 · Basis."""

    min_grade: int
    max_grade: int
    niveau: str
    label: str


class PkKompetenzRead(BaseModel):
    """Prozessbezogene Kompetenz (PK) für Bildungsplan-Hierarchie."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    metadata_: dict = Field(
        default_factory=dict,
        validation_alias="metadata",
        serialization_alias="metadata",
    )


class PkGruppeRead(BaseModel):
    """PK-Gruppe mit ihren PK-Kompetenz-Kindern."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    metadata_: dict = Field(
        default_factory=dict,
        validation_alias="metadata",
        serialization_alias="metadata",
    )
    pk_kompetenzen: list[PkKompetenzRead] = Field(default_factory=list)


class FachplanTreeRead(BaseModel):
    """Verschachtelte Bildungsplan-Hierarchie für ein Fach."""
    model_config = ConfigDict(from_attributes=True)

    fachplan: ContextNodeRead | None = None
    leitideen: list[LeitideeRead] = Field(default_factory=list)
    pk_gruppen: list[PkGruppeRead] = Field(default_factory=list)
    can_edit: bool = False
    bands: list[BandRead] = Field(default_factory=list)
    selected_band: BandRead | None = None
    bp_version: str = ""
    available_versions: list[str] = Field(default_factory=list)
