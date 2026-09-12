"""Pydantic-Schemas für die Unterrichtsplanungs-API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional  # noqa: F401 — Any used in LessonRead
from uuid import UUID

from pydantic import BaseModel, Field


# ── Wochenmuster ──────────────────────────────────────────────────────────────

class WeekPatternItem(BaseModel):
    weekday: int = Field(..., ge=0, le=4, description="0=Montag, 4=Freitag")
    start_period: int = Field(..., ge=1, description="Schulstunde im Tagesraster (1-basiert)")
    periods: int = Field(1, ge=1, le=2, description="1=Einzelstunde, 2=Doppelstunde")
    # Vorgabe wöchentlich: Bestandsmuster kennen das Feld nicht und sind alle wöchentlich —
    # ein anderer Default änderte stillschweigend den Stundenplan aller Gruppen (UP-8).
    rhythmus: str = Field(
        "woechentlich",
        pattern="^(woechentlich|a_woche|b_woche)$",
        description="14-tägige Termine: a_woche | b_woche",
    )


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
    rhythmus: str = "woechentlich"

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
    # Ob der verknüpfte Stundenentwurf schon Phasen hat.
    #
    # ⚠️ **Kein Feld des Slots**, sondern eine Auskunft über den Knoten dahinter
    # (`context_nodes.metadata->'phasen'`) — deshalb setzt `get_overview` es
    # nachträglich und `from_attributes` füllt es nicht. Ohne diese Angabe sieht ein
    # angelegter, aber leerer Entwurf in der Jahresplanung genauso aus wie ein
    # ausgearbeiteter: Thema fett, verlinkt, fertig.
    #
    # `False` heißt „keine Phasen" **oder** „gar kein Entwurf" — welcher von beiden,
    # sagt `stunde_node_id`. Die Unterscheidung trifft das Frontend
    # (`entwurfsStand` in `lib/planner.js`), damit sie an einem Ort steht.
    hat_phasen: bool = False

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


class UnitUpdate(BaseModel):
    titel: Optional[str] = None
    kapitel_node_id: Optional[UUID] = None
    farbe: Optional[int] = Field(None, ge=0, le=7)


class UnitRead(BaseModel):
    id: UUID
    title: str
    metadata_: dict = Field(alias="metadata_")
    kapitel_node_id: Optional[UUID] = None
    kapitel_std: Optional[int] = None
    # Änderungssignal für Clients außerhalb des Browsers (Unterrichtsplanungs-Sync).
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


# ── Curriculum-Kapitel-Auswahl (UE-Picker) ────────────────────────────────────

class CurriculumKapitelOption(BaseModel):
    id: UUID
    titel: str
    std: Optional[int] = None
    reihenfolge: Optional[int] = None
    ues: list[str] = []


class CurriculumOption(BaseModel):
    curriculum_id: UUID
    titel: str
    jahrgangsstufe: Optional[str] = None
    kapitel: list[CurriculumKapitelOption] = []


class GroupCurriculaRead(BaseModel):
    curricula: list[CurriculumOption] = []
    grade: Optional[int] = None
    grade_unbekannt: bool = False


# ── Stunden-Knoten ────────────────────────────────────────────────────────────

class LessonCreate(BaseModel):
    titel: str
    slot_id: Optional[UUID] = None


VALID_PRIOS = {"kern", "uebung", "vertiefung"}


class LessonLinkedItem(BaseModel):
    typ: str  # "text" | "node"
    wert: Optional[str] = None
    node_id: Optional[UUID] = None
    titel: Optional[str] = None


class LessonPhaseItem(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=200)
    dauer_min: int = Field(..., ge=1, le=480)
    beschreibung: Optional[str] = None
    prio: str = Field("kern")
    sozialform: Optional[LessonLinkedItem] = None
    methode: Optional[LessonLinkedItem] = None
    material: list[LessonLinkedItem] = []

    def validate_prio(self) -> None:
        if self.prio not in VALID_PRIOS:
            raise ValueError(f"Ungültige Prio '{self.prio}'; erlaubt: {VALID_PRIOS}")


class LessonRefItem(BaseModel):
    node_id: UUID
    typ: str  # "ik" | "pk" | "concept"
    code: Optional[str] = None
    titel: Optional[str] = None
    partiell: bool = False


class LessonUpdate(BaseModel):
    titel: Optional[str] = Field(None, min_length=1, max_length=500)
    stundenziel: Optional[str] = None
    phasen: Optional[list[LessonPhaseItem]] = None
    refs: Optional[list[LessonRefItem]] = None
    refs_dismissed: Optional[list[UUID]] = None


class LessonSlotContext(BaseModel):
    id: UUID
    date: date
    start_period: Optional[int]
    periods: int
    verfuegbare_min: int


class LessonUeContext(BaseModel):
    id: UUID
    titel: str
    farbe: int


class LessonNav(BaseModel):
    prev_node_id: Optional[UUID]
    next_node_id: Optional[UUID]
    position: int
    total: int


class LessonRead(BaseModel):
    id: UUID
    titel: str
    stundenziel: Optional[str]
    phasen: list[Any]
    refs: list[Any]
    refs_dismissed: list[str]
    ue: Optional[LessonUeContext]
    slot: Optional[LessonSlotContext]
    nav: LessonNav
    group_id: int
    subject_id: Optional[int]
    grade: Optional[int] = None  # Jahrgang der Gruppe (für editionsbewusste Kompetenz-Auswahl)
    # `False` heißt: gelesen wird über das Eigentum, nicht über die Mitgliedschaft —
    # der Archiv-Fall. Die Oberfläche schaltet dann in den Lesezustand, statt einen
    # Editor anzubieten, dessen Speichern mit 403 endet.
    darf_bearbeiten: bool = True
    # Änderungssignal für Clients außerhalb des Browsers (Unterrichtsplanungs-Sync).
    updated_at: datetime


# ── Nachbereitung ────────────────────────────────────────────────────────────

class ReviewCreate(BaseModel):
    phasen_status: dict[str, str] = Field(
        default_factory=dict,
        description="phase_id → 'erledigt'|'offen'|'gestrichen'",
    )
    reflexion: Optional[str] = None
    refs_offen: list[UUID] = []


class ReviewResultRead(BaseModel):
    engagements_written: int
    engagements_skipped: int
    refs_offen: list[str]
    open_phases: list[str]


class ReviewStatusItem(BaseModel):
    slot_id: UUID
    date: date
    stunde_node_id: UUID
    titel: Optional[str]
    nachbereitet_auto: bool = False


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


class SondertagItem(BaseModel):
    """Feiertag oder unterrichtsfreier Tag (Einzeltag, optional benannt)."""
    name: Optional[str] = None
    datum: date


class OverviewRead(BaseModel):
    slots: list[SlotRead]
    patterns: list[WeekPatternRead]
    units: list[UnitRead]
    balance: BalanceRead
    schuljahr: str
    beginn: date
    ende: date
    halbjahreswechsel: date
    ferien: list[FerienItem] = []
    feiertage: list[SondertagItem] = []
    unterrichtsfreie_tage: list[SondertagItem] = []


# ── Jetzt (Gruppenübersicht, AP5) ─────────────────────────────────────────────

class JetztStunde(BaseModel):
    slot_id: UUID
    datum: date
    thema: Optional[str] = None
    kategorie: str
    hat_entwurf: bool
    nachbereitet: bool
    ist_heute: bool
    stunde_node_id: Optional[UUID] = None
    ue_node_id: Optional[UUID] = None


class JetztEinheit(BaseModel):
    node_id: UUID
    titel: str
    stunden_gesamt: int
    stunden_gehalten: int


class JetztRead(BaseModel):
    """Wo die Gruppe gerade steht — der erste Block der Übersicht.

    `hat_plan` unterscheidet „noch nichts geplant" von „geplant, aber gerade nichts
    anstehend": Ohne die Angabe sähe eine Gruppe ohne Wochenmuster genauso aus wie
    eine am Schuljahresende, und der Weg zur Planung fehlte genau dort, wo er
    gebraucht wird.
    """
    hat_plan: bool
    laufende_einheit: Optional[JetztEinheit] = None
    naechste_einheit: Optional[JetztEinheit] = None
    zuletzt: Optional[JetztStunde] = None
    kommende: list[JetztStunde] = []
