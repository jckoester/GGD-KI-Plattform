"""Pydantic-Schemas für die Unterrichtsplanungs-API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Wochenmuster ──────────────────────────────────────────────────────────────

class WeekPatternItem(BaseModel):
    weekday: int = Field(..., ge=0, le=4, description="0=Montag, 4=Freitag")
    start_period: int = Field(..., ge=1, description="Schulstunde im Tagesraster (1-basiert)")
    periods: int = Field(1, ge=1, le=2, description="1=Einzelstunde, 2=Doppelstunde")


class WeekPatternSet(BaseModel):
    halbjahr: int = Field(..., ge=1, le=2)
    patterns: list[WeekPatternItem]


class WeekPatternRead(BaseModel):
    id: int
    group_id: int
    halbjahr: int
    weekday: int
    start_period: int
    periods: int

    class Config:
        from_attributes = True


# ── Slot ──────────────────────────────────────────────────────────────────────

class SlotGenerateRequest(BaseModel):
    halbjahr: int = Field(..., ge=1, le=2)
    regenerate: bool = False


class SlotGenStatsRead(BaseModel):
    created: int
    halbjahr: int
    used_hj1_fallback: bool


class SlotRead(BaseModel):
    id: UUID
    group_id: int
    date: date
    start_period: Optional[int]
    periods: int
    halbjahr: int
    kategorie: str
    ue_node_id: Optional[UUID]
    stunde_node_id: Optional[UUID]
    thema: Optional[str]
    pinned: bool
    anpassung_noetig: bool
    note: Optional[str]
    nachbereitet_at: Optional[datetime]
    nachbereitet_auto: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SlotUpdate(BaseModel):
    kategorie: Optional[str] = None
    thema: Optional[str] = None
    note: Optional[str] = None
    pinned: Optional[bool] = None
    anpassung_noetig: Optional[bool] = None
    ue_node_id: Optional[UUID] = None
    stunde_node_id: Optional[UUID] = None
    start_period: Optional[int] = None
    periods: Optional[int] = Field(None, ge=1, le=2)


class SlotSwapRequest(BaseModel):
    slot_a_id: UUID
    slot_b_id: UUID


# ── Unterrichtseinheit ────────────────────────────────────────────────────────

class UnitCreate(BaseModel):
    titel: str
    kapitel_node_id: Optional[UUID] = None
    farbe: Optional[int] = Field(None, ge=0, le=7)


class UnitRead(BaseModel):
    id: UUID
    title: str
    metadata_: dict = Field(alias="metadata_")
    kapitel_std: Optional[int] = None

    class Config:
        from_attributes = True
        populate_by_name = True


# ── Stunden-Knoten ────────────────────────────────────────────────────────────

class LessonCreate(BaseModel):
    titel: str
    slot_id: Optional[UUID] = None


# ── Bilanz ───────────────────────────────────────────────────────────────────

class UnitBalanceItem(BaseModel):
    ue_node_id: UUID
    titel: str
    soll_std: Optional[int]
    zugewiesen: int
    puffer: int


class BalanceRead(BaseModel):
    items: list[UnitBalanceItem]
    total_slots: int
    unzugewiesen: int


# ── Snapshot ──────────────────────────────────────────────────────────────────

class SnapshotCreate(BaseModel):
    label: Optional[str] = None


class SnapshotRead(BaseModel):
    id: UUID
    group_id: int
    reason: str
    label: Optional[str]
    created_by: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Overview ──────────────────────────────────────────────────────────────────

class FerienItem(BaseModel):
    name: str
    von: date
    bis: date


class OverviewRead(BaseModel):
    slots: list[SlotRead]
    patterns: list[WeekPatternRead]
    units: list[UnitRead]
    balance: BalanceRead
    schuljahr: str
    halbjahreswechsel: date
    ferien: list[FerienItem] = []
