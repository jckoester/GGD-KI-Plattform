"""Pydantic-Schemas für die Context-Nodes-API."""

from datetime import date, datetime
from typing import Any
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
    title: str
    content_type: str | None
    added_at: datetime
