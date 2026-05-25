"""Pydantic-Schemas für die Context-Nodes-API."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    metadata_: dict[str, Any] = Field(alias="metadata")
    owner_pseudonym: str | None
    read_scope: str
    write_scope: str
    read_scope_group_id: int | None
    write_scope_group_id: int | None
    assistant_id: int | None
    status: str
    valid_until: date | None
    archived_at: datetime | None
    schuljahr: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
