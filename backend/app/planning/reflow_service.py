"""UP-6 Schritt 1: Reflow-Kontext-Service.

Liefert dem Verschiebe-Assistenten ein strukturiertes, token-kompaktes Datenpaket:
betroffene Slots (Auslöser) + Folge-Slots bis zum nächsten Fixpunkt, Fixpunkte mit
verbleibendem Slot-Vorrat, UE-Bilanz, bei offenen Phasen die Quellstunde, bei
Regeneration die alte Zuordnung + neue Tranche. Rein deterministisch (kein LLM).
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode, LessonSlot, SlotPlanSnapshot
from app.planning.calendar import load_school_year

VALID_TRIGGERS: frozenset[str] = frozenset(
    {"ausfall", "drag_drop", "open_phases", "regeneration", "manual"}
)
_VORRAT_KATEGORIEN: frozenset[str] = frozenset({"unterricht", "puffer", "vertretung"})
_PRIO_ORDER = ["kern", "uebung", "vertiefung"]


class SlotState(BaseModel):
    id: str
    date: str
    kw: int
    periods: int
    start_period: int | None
    kategorie: str
    pinned: bool
    ue_node_id: str | None
    ue_titel: str | None
    thema: str | None
    stunde_node_id: str | None
    planungsstand: str  # 'ungeplant' | 'nur_thema' | 'geplant'
    phasen_kurzform: str | None
    anpassung_noetig: bool


class FixpunktState(BaseModel):
    slot_id: str
    date: str
    kategorie: str
    pinned: bool
    ue_titel: str | None
    slots_dahinter: int


class UeBilanzItem(BaseModel):
    ue_node_id: str
    titel: str
    soll_std: int | None
    zugewiesen: int
    puffer: int


class OpenPhase(BaseModel):
    id: str
    name: str
    dauer_min: int
    prio: str
    status: str


class OpenPhasesInfo(BaseModel):
    lesson_id: str
    slot_id: str
    phasen: list[OpenPhase]
    refs_offen: list[str]


class ReflowContext(BaseModel):
    trigger: str
    schuljahresende: str
    halbjahr: int
    betroffene: list[SlotState]
    folge_slots: list[SlotState]
    fixpunkte: list[FixpunktState]
    bilanz: list[UeBilanzItem]
    offene_phasen: OpenPhasesInfo | None = None
    regeneration: dict | None = None


class OverhangFinding(BaseModel):
    ue_node_id: str
    titel: str
    ueberhang: int  # zugewiesene Std über Soll
    fixpunkt_datum: str | None  # nächster Prüfungs-Fixpunkt, auf den die UE zuläuft
    fixpunkt_kategorie: str | None


async def detect_overhang(
    db: AsyncSession, group_id: int, *, today: date | None = None
) -> list[OverhangFinding]:
    """Pro UE: zugewiesene Std über Soll, verknüpft mit dem nächsten Prüfungs-Fixpunkt,
    auf den die UE zuläuft. Basis für die Assistenten-Hinweisleiste (UP-6 Schritt 8)."""
    from app.planning.router import _build_balance, _load_units

    all_slots = list(
        (
            await db.execute(
                sa.select(LessonSlot)
                .where(LessonSlot.group_id == group_id)
                .order_by(LessonSlot.date, LessonSlot.start_period)
            )
        ).scalars().all()
    )
    units = await _load_units(db, group_id)
    balance = await _build_balance(db, group_id, units, all_slots)

    pruefungen = [s for s in all_slots if s.kategorie == "pruefung"]
    findings: list[OverhangFinding] = []
    for item in balance.items:
        if item.puffer <= 0:
            continue
        ue_slots = [s for s in all_slots if s.ue_node_id == item.ue_node_id]
        if not ue_slots:
            continue
        ue_start = min(s.date for s in ue_slots)
        # Nächste Prüfung ab Beginn der UE = die KA, auf die die UE zuläuft.
        next_pruefung = next((p for p in pruefungen if p.date >= ue_start), None)
        findings.append(
            OverhangFinding(
                ue_node_id=str(item.ue_node_id),
                titel=item.titel,
                ueberhang=item.puffer,
                fixpunkt_datum=next_pruefung.date.isoformat() if next_pruefung else None,
                fixpunkt_kategorie="pruefung" if next_pruefung else None,
            )
        )
    return findings


def _phasen_kurzform(phasen: list[dict]) -> str | None:
    counts: dict[str, int] = {}
    for p in phasen:
        prio = p.get("prio", "kern")
        counts[prio] = counts.get(prio, 0) + 1
    if not counts:
        return None
    parts = [f"{k}×{counts[k]}" for k in _PRIO_ORDER if k in counts]
    parts += [f"{k}×{v}" for k, v in counts.items() if k not in _PRIO_ORDER]
    return "[" + ", ".join(parts) + "]"


def _planungsstand(slot: LessonSlot, stunde: ContextNode | None) -> tuple[str, str | None]:
    if slot.stunde_node_id is not None and stunde is not None:
        phasen = (stunde.metadata_ or {}).get("phasen") or []
        if phasen:
            return "geplant", _phasen_kurzform(phasen)
        return "nur_thema", None
    if slot.thema or slot.ue_node_id:
        return "nur_thema", None
    return "ungeplant", None


def _slot_state(slot, ue_map, stunde_map) -> SlotState:
    stunde = stunde_map.get(slot.stunde_node_id) if slot.stunde_node_id else None
    stand, kurz = _planungsstand(slot, stunde)
    return SlotState(
        id=str(slot.id),
        date=slot.date.isoformat(),
        kw=slot.date.isocalendar()[1],
        periods=slot.periods,
        start_period=slot.start_period,
        kategorie=slot.kategorie,
        pinned=slot.pinned,
        ue_node_id=str(slot.ue_node_id) if slot.ue_node_id else None,
        ue_titel=ue_map.get(slot.ue_node_id),
        thema=slot.thema,
        stunde_node_id=str(slot.stunde_node_id) if slot.stunde_node_id else None,
        planungsstand=stand,
        phasen_kurzform=kurz,
        anpassung_noetig=slot.anpassung_noetig,
    )


def _is_fixpunkt(slot: LessonSlot) -> bool:
    return slot.pinned or slot.kategorie == "pruefung"


async def build_reflow_context(
    db: AsyncSession,
    group_id: int,
    *,
    trigger: str,
    slot_ids: list[UUID] | None = None,
    today: date | None = None,
) -> ReflowContext:
    if trigger not in VALID_TRIGGERS:
        raise ValueError(f"Unbekannter trigger: {trigger!r}")

    cfg = load_school_year()
    # Lokaler Import bricht den Zyklus router → (service/tools) → reflow_service.
    from app.planning.router import _build_balance, _load_units

    all_slots = list(
        (
            await db.execute(
                sa.select(LessonSlot)
                .where(LessonSlot.group_id == group_id)
                .order_by(LessonSlot.date, LessonSlot.start_period)
            )
        ).scalars().all()
    )
    slot_by_id = {s.id: s for s in all_slots}

    units = await _load_units(db, group_id)
    ue_map = {u.id: u.title for u in units}

    stunde_ids = [s.stunde_node_id for s in all_slots if s.stunde_node_id]
    stunde_map: dict[UUID, ContextNode] = {}
    if stunde_ids:
        rows = (
            await db.execute(sa.select(ContextNode).where(ContextNode.id.in_(stunde_ids)))
        ).scalars().all()
        stunde_map = {n.id: n for n in rows}

    betroffene_ids = (
        {UUID(str(s)) for s in slot_ids} & set(slot_by_id) if slot_ids else set()
    )
    betroffene_slots = sorted(
        (slot_by_id[i] for i in betroffene_ids),
        key=lambda s: (s.date, s.start_period or 0),
    )

    # Startdatum + Halbjahres-Horizont.
    if betroffene_slots:
        start_date = betroffene_slots[0].date
    elif trigger == "regeneration":
        start_date = cfg.halbjahreswechsel
    else:
        start_date = today or date.today()
    start_hj = 1 if start_date < cfg.halbjahreswechsel else 2
    hj_end = (cfg.halbjahreswechsel - timedelta(days=1)) if start_hj == 1 else cfg.ende

    # Nächster Fixpunkt nach dem Start begrenzt das Folge-Fenster.
    next_fix = next(
        (s for s in all_slots if start_date < s.date <= hj_end and _is_fixpunkt(s)), None
    )
    cutoff = next_fix.date if next_fix else hj_end + timedelta(days=1)
    folge_slots = [
        s
        for s in all_slots
        if start_date <= s.date < cutoff and s.id not in betroffene_ids
    ]

    # Fixpunkte im Horizont + verbleibender Slot-Vorrat dahinter.
    fix_slots = [s for s in all_slots if _is_fixpunkt(s) and start_date <= s.date <= hj_end]
    fixpunkte: list[FixpunktState] = []
    for idx, fs in enumerate(fix_slots):
        next_date = fix_slots[idx + 1].date if idx + 1 < len(fix_slots) else hj_end + timedelta(days=1)
        vorrat = sum(
            1
            for s in all_slots
            if fs.date < s.date < next_date and s.kategorie in _VORRAT_KATEGORIEN
        )
        fixpunkte.append(
            FixpunktState(
                slot_id=str(fs.id),
                date=fs.date.isoformat(),
                kategorie=fs.kategorie,
                pinned=fs.pinned,
                ue_titel=ue_map.get(fs.ue_node_id),
                slots_dahinter=vorrat,
            )
        )

    # Bilanz nur für die im Fenster betroffenen UEs.
    window_ue_ids = {
        s.ue_node_id for s in [*betroffene_slots, *folge_slots] if s.ue_node_id
    }
    balance = await _build_balance(db, group_id, units, all_slots)
    bilanz = [
        UeBilanzItem(
            ue_node_id=str(it.ue_node_id),
            titel=it.titel,
            soll_std=it.soll_std,
            zugewiesen=it.zugewiesen,
            puffer=it.puffer,
        )
        for it in balance.items
        if it.ue_node_id in window_ue_ids
    ]

    offene_phasen = None
    if trigger == "open_phases" and betroffene_slots:
        src = betroffene_slots[0]
        stunde = stunde_map.get(src.stunde_node_id) if src.stunde_node_id else None
        if stunde is not None:
            meta = stunde.metadata_ or {}
            offene_phasen = OpenPhasesInfo(
                lesson_id=str(stunde.id),
                slot_id=str(src.id),
                phasen=[
                    OpenPhase(
                        id=str(p.get("id") or ""),
                        name=p.get("name", ""),
                        dauer_min=p.get("dauer_min", 0),
                        prio=p.get("prio", "kern"),
                        status=p.get("status", "geplant"),
                    )
                    for p in meta.get("phasen", [])
                    if p.get("status") in ("offen", "gestrichen")
                ],
                refs_offen=[str(x) for x in meta.get("refs_offen", [])],
            )

    regeneration = None
    if trigger == "regeneration":
        snap = (
            await db.execute(
                sa.select(SlotPlanSnapshot)
                .where(
                    SlotPlanSnapshot.group_id == group_id,
                    SlotPlanSnapshot.reason == "regeneration",
                )
                .order_by(SlotPlanSnapshot.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        neue_tranche = [
            _slot_state(s, ue_map, stunde_map).model_dump()
            for s in all_slots
            if s.halbjahr == 2
        ]
        regeneration = {
            "alte_zuordnung": (snap.payload.get("slots") if snap else None),
            "neue_tranche": neue_tranche,
        }

    return ReflowContext(
        trigger=trigger,
        schuljahresende=cfg.ende.isoformat(),
        halbjahr=start_hj,
        betroffene=[_slot_state(s, ue_map, stunde_map) for s in betroffene_slots],
        folge_slots=[_slot_state(s, ue_map, stunde_map) for s in folge_slots],
        fixpunkte=fixpunkte,
        bilanz=bilanz,
        offene_phasen=offene_phasen,
        regeneration=regeneration,
    )
