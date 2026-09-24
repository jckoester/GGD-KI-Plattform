"""CRUD-API für die Unterrichtsplanung.

Alle Endpoints erfordern Lehrkraft-Mitgliedschaft in der betroffenen teaching_group
(require_group_teacher). Kein Admin-Sonderfall — ohne Mitgliedschaft kein Zugriff.

Auto-Snapshot-Regel:
- PATCH Slot mit Zuordnungsfeldern (ue_node_id, stunde_node_id, thema, kategorie)
- POST swap, POST generate(regenerate), POST restore
lösen jeweils einen Snapshot aus.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_any_role
from app.auth.jwt import JwtPayload
from app.config import settings
from app.context.taxonomy import validate_content_type, validate_unterrichtsstunde_metadata
from app.db.models import (
    ContextEdge,
    ContextNode,
    Group,
    GroupMembership,
    GroupWeekPattern,
    LessonSlot,
    ParkedLessonContent,
    SlotPlanSnapshot,
    Subject,
)
from app.db.session import get_db
from app.planning.calendar import ab_schultage, load_school_year
from app.planning.curriculum_resolver import resolve_group_curricula
from app.planning.material_edges import synchronisiere_materialkanten
from app.planning import jetzt as jetzt_modul
from app.planning import mein_tag as mein_tag_modul
from app.planning import vorbedingung
from app.planning.permissions import require_group_teacher, zugang_zur_stunde
from app.planning.operations import apply_operations, parse_operations
from app.planning.phasen import sichere_phasen_kennungen
from app.planning.schemas import (
    AbWochenRead,
    BalanceRead,
    JetztEinheit,
    JetztRead,
    JetztStunde,
    CurriculumKapitelOption,
    CurriculumOption,
    FerienItem,
    SondertagItem,
    GroupCurriculaRead,
    LessonCreate,
    LessonNav,
    LessonRead,
    LessonSlotContext,
    LessonUeContext,
    LessonUpdate,
    OverviewRead,
    ReviewCreate,
    ReviewResultRead,
    ReviewStatusItem,
    SlotGenStatsRead,
    SlotGenerateRequest,
    SlotRead,
    SlotSwapRequest,
    SlotUpdate,
    SnapshotCreate,
    SnapshotRead,
    UnitBalanceItem,
    UnitCreate,
    UnitUpdate,
    UnitRead,
    WeekPatternRead,
    WeekPatternSet,
)
from app.planning.service import create_unit_node, delete_unit_node, update_unit_node
from app.planning.reflow_service import OverhangFinding, detect_overhang
from app.planning.snapshots import create_snapshot, restore_snapshot
from app.planning.slot_generator import generate_slots

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/planning", tags=["planning"])

_TEACHER_OR_ADMIN = require_any_role(["teacher", "admin"])

_SNAPSHOT_ASSIGNMENT_FIELDS = frozenset(
    {"ue_node_id", "stunde_node_id", "thema", "kategorie"}
)



async def _kapitel_std(db: AsyncSession, kapitel_node_id: UUID) -> int | None:
    """Gibt metadata.std eines Kapitel-Knotens zurück (None wenn nicht vorhanden)."""
    node = await db.get(ContextNode, kapitel_node_id)
    if node is None:
        return None
    return (node.metadata_ or {}).get("std")


async def _kapitel_ref(db: AsyncSession, ue_id: UUID) -> tuple[UUID | None, int | None]:
    """Verknüpftes Curriculum-Kapitel einer UE: (kapitel_node_id, std) oder (None, None)."""
    edges = await db.execute(
        sa.select(ContextEdge).where(
            ContextEdge.from_node_id == ue_id,
            ContextEdge.relation == "references",
        )
    )
    for edge in edges.scalars().all():
        kap = await db.get(ContextNode, edge.to_node_id)
        if kap and kap.content_type == "kapitel":
            return kap.id, (kap.metadata_ or {}).get("std")
    return None, None


async def _build_balance(
    db: AsyncSession,
    group_id: int,
    units: list[ContextNode],
    slots: list[LessonSlot],
) -> BalanceRead:
    # Ausgefallene Stunden zählen nicht zum Unterrichtsbudget: sie fanden nicht
    # statt. Die UE-Zuordnung bleibt am Slot erhalten (Nachvollziehbarkeit, einfaches
    # Zurücksetzen), wird hier aber komplett aus der Bilanz herausgerechnet.
    aktive_slots = [s for s in slots if s.kategorie != "ausfall"]
    total_slots = len(aktive_slots)
    assigned_slot_ids: set[UUID] = set()
    items: list[UnitBalanceItem] = []

    for ue_node in units:
        ue_slots = [s for s in aktive_slots if s.ue_node_id == ue_node.id]
        # Curriculum-Stunden sind Einzelstunden; ein Doppelstunden-Slot (periods=2)
        # zählt entsprechend als 2 Stunden. Daher Summe der periods, nicht Slot-Anzahl.
        zugewiesen = sum(s.periods for s in ue_slots)
        for s in ue_slots:
            assigned_slot_ids.add(s.id)

        soll_std: int | None = None
        kapitel_edge = await db.execute(
            sa.select(ContextEdge).where(
                ContextEdge.from_node_id == ue_node.id,
                ContextEdge.relation == "references",
            )
        )
        for edge in kapitel_edge.scalars().all():
            kapitel = await db.get(ContextNode, edge.to_node_id)
            if kapitel and kapitel.content_type == "kapitel":
                soll_std = (kapitel.metadata_ or {}).get("std")
                break

        puffer = 0
        if soll_std is not None:
            puffer = max(0, zugewiesen - soll_std)

        items.append(
            UnitBalanceItem(
                ue_node_id=ue_node.id,
                titel=ue_node.title,
                soll_std=soll_std,
                zugewiesen=zugewiesen,
                puffer=puffer,
            )
        )

    unzugewiesen = total_slots - len(assigned_slot_ids)
    return BalanceRead(items=items, total_slots=total_slots, unzugewiesen=unzugewiesen)


async def _load_units(db: AsyncSession, group_id: int) -> list[ContextNode]:
    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "unterrichtseinheit",
            ContextNode.write_scope == "group",
            ContextNode.write_scope_group_id == group_id,
            ContextNode.status == "active",
        ).order_by(ContextNode.created_at)
    )
    return result.scalars().all()


# ── GET /planning/groups/{group_id}/overview ──────────────────────────────────


async def _stunden_mit_phasen(db: AsyncSession, slots) -> set[UUID]:
    """Welche der verknüpften Stundenentwürfe schon Phasen haben.

    **Eine Abfrage für alle Slots**, nicht eine je Slot: Ein Schuljahr einer Gruppe
    bringt rund 40 bis 120 Slots mit, und die Jahresübersicht lädt sie in einem Zug.

    Gefiltert wird in der Datenbank (`jsonb_array_length > 0`) statt im Python — so
    wandern nur die Treffer über die Leitung, und die Regel „leer heißt Idee" steht
    an einer Stelle.
    """
    ids = {s.stunde_node_id for s in slots if s.stunde_node_id}
    if not ids:
        return set()

    phasen = sa.func.coalesce(
        ContextNode.metadata_["phasen"], sa.text("'[]'::jsonb")
    )
    treffer = await db.execute(
        sa.select(ContextNode.id).where(
            ContextNode.id.in_(ids),
            sa.func.jsonb_array_length(phasen) > 0,
        )
    )
    return set(treffer.scalars())


@router.get("/groups/{group_id}/overview", response_model=OverviewRead)
async def get_overview(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    slots_result = await db.execute(
        sa.select(LessonSlot)
        .where(LessonSlot.group_id == group_id)
        .order_by(LessonSlot.date, LessonSlot.start_period)
    )
    slots = slots_result.scalars().all()

    patterns_result = await db.execute(
        sa.select(GroupWeekPattern)
        .where(GroupWeekPattern.group_id == group_id)
        .order_by(GroupWeekPattern.halbjahr, GroupWeekPattern.weekday, GroupWeekPattern.start_period)
    )
    patterns = patterns_result.scalars().all()

    ausgearbeitet = await _stunden_mit_phasen(db, slots)

    units = await _load_units(db, group_id)
    balance = await _build_balance(db, group_id, units, slots)

    unit_reads = []
    for ue in units:
        kapitel_node_id, kapitel_std = await _kapitel_ref(db, ue.id)
        unit_reads.append(
            UnitRead(
                id=ue.id,
                title=ue.title,
                metadata_=ue.metadata_ or {},
                kapitel_node_id=kapitel_node_id,
                kapitel_std=kapitel_std,
                updated_at=ue.updated_at,
            )
        )

    from app.planning.calendar import load_school_year
    cfg = load_school_year()

    return OverviewRead(
        slots=[
            SlotRead.model_validate(s).model_copy(
                update={"hat_phasen": s.stunde_node_id in ausgearbeitet}
            )
            for s in slots
        ],
        patterns=[WeekPatternRead.model_validate(p) for p in patterns],
        units=unit_reads,
        balance=balance,
        schuljahr=cfg.schuljahr,
        beginn=cfg.beginn,
        ende=cfg.ende,
        halbjahreswechsel=cfg.halbjahreswechsel,
        ferien=[FerienItem(name=f.name, von=f.von, bis=f.bis) for f in cfg.ferien],
        feiertage=[SondertagItem(name=t.name, datum=t.datum) for t in cfg.feiertage],
        unterrichtsfreie_tage=[
            SondertagItem(name=t.name, datum=t.datum) for t in cfg.unterrichtsfreie_tage
        ],
    )


# ── GET /planning/groups/{group_id}/jetzt ─────────────────────────────────────


@router.get("/groups/{group_id}/jetzt", response_model=JetztRead)
async def get_jetzt(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Wo die Gruppe gerade steht — für den ersten Block der Gruppenübersicht.

    Bewusst **nicht** `…/overview`: Der liefert dieselben Slots, dazu aber
    Wochenmuster, alle Einheiten, die Stundenbilanz und den kompletten
    Schuljahreskalender mit Ferien und Feiertagen — für fünf Zeilen.

    Die Slots des ganzen Schuljahres zu laden ist trotzdem richtig: Es sind je
    Gruppe rund hundert Zeilen, und die Stundenzahl einer Einheit („6 von 12")
    braucht sie ohnehin alle. Die Auswahl selbst steht in `app.planning.jetzt` —
    ohne Datenbank, damit ihre Grenzfälle prüfbar bleiben.
    """
    await require_group_teacher(group_id, user, db)

    result = await db.execute(
        sa.select(LessonSlot)
        .where(LessonSlot.group_id == group_id)
        .order_by(LessonSlot.date, LessonSlot.start_period)
    )
    slots = list(result.scalars().all())

    auswahl = jetzt_modul.waehle(slots, date.today())

    # Titel der beiden Einheiten in einer Abfrage, nicht in zweien.
    ue_ids = [
        e.node_id
        for e in (auswahl.laufende_einheit, auswahl.naechste_einheit)
        if e is not None
    ]
    titel: dict[UUID, str] = {}
    if ue_ids:
        res = await db.execute(
            sa.select(ContextNode.id, ContextNode.title).where(ContextNode.id.in_(ue_ids))
        )
        titel = {row[0]: row[1] for row in res.all()}

    def _einheit(e) -> JetztEinheit | None:
        if e is None:
            return None
        return JetztEinheit(
            node_id=e.node_id,
            # Eine Einheit ohne Knoten sollte es nicht geben (Fremdschlüssel mit
            # SET NULL); falls doch, ist ein Platzhalter besser als ein 500er.
            titel=titel.get(e.node_id, "Unbenannte Einheit"),
            stunden_gesamt=e.stunden_gesamt,
            stunden_gehalten=e.stunden_gehalten,
        )

    return JetztRead(
        hat_plan=bool(slots),
        laufende_einheit=_einheit(auswahl.laufende_einheit),
        naechste_einheit=_einheit(auswahl.naechste_einheit),
        zuletzt=JetztStunde(**vars(auswahl.zuletzt)) if auswahl.zuletzt else None,
        kommende=[JetztStunde(**vars(s)) for s in auswahl.kommende],
    )


# ── PUT /planning/groups/{group_id}/pattern ───────────────────────────────────


@router.put("/groups/{group_id}/pattern", response_model=list[WeekPatternRead])
async def set_week_pattern(
    group_id: int,
    payload: WeekPatternSet,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    await db.execute(
        sa.delete(GroupWeekPattern).where(
            GroupWeekPattern.group_id == group_id,
            GroupWeekPattern.halbjahr == payload.halbjahr,
        )
    )
    new_patterns = []
    for item in payload.patterns:
        p = GroupWeekPattern(
            group_id=group_id,
            halbjahr=payload.halbjahr,
            weekday=item.weekday,
            start_period=item.start_period,
            periods=item.periods,
            rhythmus=item.rhythmus,
        )
        db.add(p)
        new_patterns.append(p)

    await db.commit()
    for p in new_patterns:
        await db.refresh(p)
    return new_patterns


# ── GET /planning/ab-wochen ───────────────────────────────────────────────────


@router.get("/ab-wochen", response_model=AbWochenRead)
async def ab_wochen(
    halbjahr: int = Query(..., ge=1, le=2),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Welche Schultage im Halbjahr zur A- und welche zur B-Woche gehören.

    Damit kann der Wochenmuster-Editor neben „B-Woche" die konkreten Termine zeigen — und
    erst das macht den Buchstaben entbehrlich: Heißt die Woche in eurem Stundenplan anders
    als hier, prüft die Lehrkraft die Daten und muss die Bezeichnungen nicht vergleichen.
    Ohne das korrigiert früher oder später jemand das Auswahlfeld und verschiebt die Phase
    um eine Woche.

    Weder Gruppe noch Datenbank: Das ist reiner Schulkalender.
    """
    a_woche, b_woche = ab_schultage(halbjahr)
    return AbWochenRead(halbjahr=halbjahr, a_woche=a_woche, b_woche=b_woche)


# ── POST /planning/groups/{group_id}/slots/generate ───────────────────────────


@router.post("/groups/{group_id}/slots/generate", response_model=SlotGenStatsRead)
async def generate_group_slots(
    group_id: int,
    payload: SlotGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    stats = await generate_slots(
        db,
        group_id,
        payload.halbjahr,
        regenerate=payload.regenerate,
        vorlaeufig=payload.vorlaeufig,
        dry_run=payload.dry_run,
        created_by=user.sub,
    )
    return SlotGenStatsRead(
        created=stats.created,
        halbjahr=stats.halbjahr,
        used_hj1_fallback=stats.used_hj1_fallback,
        fallback_vierzehntaegig=stats.fallback_vierzehntaegig,
        vorlaeufig=stats.vorlaeufig,
        verschont=stats.verschont,
        umgehaengt=stats.umgehaengt,
        geparkt=stats.geparkt,
        meldungen=stats.meldungen,
    )


# ── PATCH /planning/slots/{slot_id} ──────────────────────────────────────────


@router.patch("/slots/{slot_id}", response_model=SlotRead)
async def update_slot(
    slot_id: UUID,
    payload: SlotUpdate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    slot = await db.get(LessonSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot nicht gefunden")

    await require_group_teacher(slot.group_id, user, db)

    vorbedingung.pruefe(slot.updated_at, payload.expected_updated_at, "Diese Stunde")

    update_data = payload.model_dump(exclude_unset=True)
    # Kein Datenfeld, sondern eine Bedingung — sie gehört nicht in die Schleife unten.
    # Ohne das Entfernen setzte `setattr` sie als **nicht abgebildetes** Attribut auf die
    # Instanz: folgenlos für die Datenbank (nachgemessen), aber ein Wert, der aussieht,
    # als gehörte er dorthin. Der nächste, der die Schleife erweitert, soll nicht darüber
    # stolpern.
    update_data.pop("expected_updated_at", None)

    changes_assignment = bool(_SNAPSHOT_ASSIGNMENT_FIELDS & update_data.keys())
    if changes_assignment:
        await create_snapshot(
            db, slot.group_id, reason="edit", created_by=user.sub
        )

    if "kategorie" in update_data:
        valid_kategorien = {"unterricht", "pruefung", "ausfall", "puffer", "vertretung"}
        if update_data["kategorie"] not in valid_kategorien:
            raise HTTPException(
                status_code=422,
                detail=f"Ungültige Kategorie. Erlaubt: {sorted(valid_kategorien)}",
            )

    for field, value in update_data.items():
        setattr(slot, field, value)

    slot.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(slot)
    return slot


# ── Parkplatz: Planungsinhalt ohne Termin ────────────────────────────────────


class ParkplatzItem(BaseModel):
    id: UUID
    halbjahr: int
    herkunft_datum: date
    thema: Optional[str] = None
    ue_node_id: Optional[UUID] = None
    ue_titel: Optional[str] = None
    stunde_node_id: Optional[UUID] = None
    stunde_titel: Optional[str] = None


class ParkplatzRead(BaseModel):
    items: list[ParkplatzItem]
    # Welche Unterrichtseinheit über ihrem Soll liegt. Ohne diese Angabe stünde auf dem
    # Parkplatz eine Liste ohne Begründung — und der Weg „kürzen" wäre nicht wählbar,
    # sondern geraten.
    ueberhang: list[OverhangFinding]


@router.get("/groups/{group_id}/parkplatz", response_model=ParkplatzRead)
async def get_parkplatz(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Was gerade keinen Termin hat — und warum.

    Entsteht beim Umhängen der Jahresplanung auf ein neues Stundenraster: Gibt es
    weniger Termine als Inhalte, bleibt der Rest hier liegen statt verloren zu gehen.
    Zurück kommt er durch Umplanen (`unpark_content`) oder durch Kürzen.
    """
    await require_group_teacher(group_id, user, db)

    eintraege = list(
        (
            await db.execute(
                sa.select(ParkedLessonContent)
                .where(ParkedLessonContent.group_id == group_id)
                .order_by(ParkedLessonContent.herkunft_datum)
            )
        )
        .scalars()
        .all()
    )

    knoten_ids = {
        i for e in eintraege for i in (e.ue_node_id, e.stunde_node_id) if i is not None
    }
    titel = {
        n.id: n.title
        for n in (
            await db.execute(
                sa.select(ContextNode).where(ContextNode.id.in_(knoten_ids or {None}))
            )
        )
        .scalars()
        .all()
    }

    return ParkplatzRead(
        items=[
            ParkplatzItem(
                id=e.id,
                halbjahr=e.halbjahr,
                herkunft_datum=e.herkunft_datum,
                thema=e.thema,
                ue_node_id=e.ue_node_id,
                ue_titel=titel.get(e.ue_node_id),
                stunde_node_id=e.stunde_node_id,
                stunde_titel=titel.get(e.stunde_node_id),
            )
            for e in eintraege
        ],
        ueberhang=await detect_overhang(db, group_id),
    )


class UnparkRequest(BaseModel):
    to_slot_id: UUID


@router.post("/parkplatz/{parkplatz_id}/unpark", response_model=dict)
async def unpark_eintrag(
    parkplatz_id: UUID,
    payload: UnparkRequest,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Holt einen geparkten Inhalt auf eine freie Stunde.

    **Warum ein eigener Endpunkt und nicht „Operationen anwenden".** Plan-Operationen
    laufen sonst über das Chat-Werkzeug `apply_plan_operations`; einen HTTP-Weg dorthin
    gibt es nicht. Statt einen allgemeinen aufzumachen — der jede Operation von außen
    erreichbar machte — bekommt der eine Vorgang, den die Oberfläche braucht, seinen
    eigenen Eingang. Die Prüfung dahinter ist dieselbe: `apply_operations` mit der
    Operation `unpark_content`, samt Snapshot und Undo.
    """
    eintrag = await db.get(ParkedLessonContent, parkplatz_id)
    if eintrag is None:
        raise HTTPException(status_code=404, detail="Parkplatz-Eintrag nicht gefunden")

    await require_group_teacher(eintrag.group_id, user, db)

    ergebnis = await apply_operations(
        db,
        eintrag.group_id,
        parse_operations([
            {
                "op": "unpark_content",
                "parkplatz_id": str(parkplatz_id),
                "to_slot_id": str(payload.to_slot_id),
            }
        ]),
        summary="Stunde vom Parkplatz eingeplant",
        created_by=user.sub,
    )
    if ergebnis.errors:
        # 409: Der Zielslot ist belegt oder gehört zu einer anderen Gruppe — beides ist
        # ein Konflikt mit dem Bestand, keine fehlerhafte Anfrage.
        raise HTTPException(status_code=409, detail=" · ".join(ergebnis.errors))
    return {"ok": True}


@router.delete("/parkplatz/{parkplatz_id}", response_model=dict)
async def delete_parkplatz_eintrag(
    parkplatz_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Verwirft einen Parkplatz-Eintrag.

    ⚠️ **Der Stundenentwurf bleibt.** Verworfen wird nur die Zusage, dass er in diesen
    Jahresplan gehört; der Knoten steht weiter im Wissensgraphen und ist dort auffindbar.
    Der übliche Weg hierher: Die Phasen wurden per `transfer_phases` in eine andere
    Stunde übernommen oder gekürzt — dann braucht der Eintrag keinen Termin mehr.
    """
    eintrag = await db.get(ParkedLessonContent, parkplatz_id)
    if eintrag is None:
        raise HTTPException(status_code=404, detail="Parkplatz-Eintrag nicht gefunden")

    await require_group_teacher(eintrag.group_id, user, db)

    await db.delete(eintrag)
    await db.commit()
    logger.info(
        "parkplatz_verworfen pseudonym=%s eintrag=%s gruppe=%s",
        user.sub, parkplatz_id, eintrag.group_id,
    )
    return {"ok": True}


# ── DELETE /planning/slots/{slot_id} ─────────────────────────────────────────


@router.delete("/slots/{slot_id}", response_model=dict)
async def delete_slot(
    slot_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Löscht einen einzelnen, leeren Termin.

    **Warum es diesen Endpunkt gibt.** Slots ließen sich bis zum 22.09.2026 überhaupt
    nicht einzeln löschen — es gab nur `regenerate`, und der nahm das ganze Halbjahr.
    Seit derselben Änderung verschont der Neuaufbau aber Slots mit `source='import'`
    oder `'manual'`: Ohne diesen Weg wäre ein versehentlich angelegter Termin
    **unlöschbar**.

    **Zwei Grenzen, beide mit 409:**

    *Inhalt daran* — eine Stunde mit Thema, Einheit oder Entwurf zu löschen hieße, die
    Planung wegzuwerfen, um einen Termin loszuwerden. Erst den Inhalt verschieben.

    *Aus dem Wochenmuster* (`source='pattern'`) — ein solcher Slot wäre beim nächsten
    Erzeugen wieder da. Die richtige Korrektur ist das Muster, nicht die Zeile.

    ⚠️ **Kein Weg für „an diesem Termin findet nichts statt".** Den Termin gibt es im
    Stundenplan, der Kalender zeigt ihn — das ist `kategorie='ausfall'` und keine
    gelöschte Zeile. Der Abgleich schreibt das ohnehin selbst.
    """
    slot = await db.get(LessonSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot nicht gefunden")

    await require_group_teacher(slot.group_id, user, db)

    if slot.ue_node_id or slot.stunde_node_id or (slot.thema or "").strip():
        raise HTTPException(
            status_code=409,
            detail=(
                "Diese Stunde trägt Inhalt. Verschieben Sie ihn zuerst auf einen "
                "anderen Termin."
            ),
        )
    if slot.source == "pattern":
        raise HTTPException(
            status_code=409,
            detail=(
                "Diese Stunde stammt aus dem Wochenmuster und entsteht beim nächsten "
                "Erzeugen wieder. Ändern Sie das Wochenmuster der Gruppe."
            ),
        )

    await create_snapshot(db, slot.group_id, reason="edit", created_by=user.sub)
    await db.delete(slot)
    await db.commit()
    logger.info(
        "slot_geloescht pseudonym=%s slot=%s gruppe=%s source=%s",
        user.sub, slot_id, slot.group_id, slot.source,
    )
    return {"ok": True}


# ── POST /planning/groups/{group_id}/slots/swap ───────────────────────────────


@router.post("/groups/{group_id}/slots/swap", response_model=list[SlotRead])
async def swap_slots(
    group_id: int,
    payload: SlotSwapRequest,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    slot_a = await db.get(LessonSlot, payload.slot_a_id)
    slot_b = await db.get(LessonSlot, payload.slot_b_id)

    if slot_a is None or slot_b is None:
        raise HTTPException(status_code=404, detail="Slot nicht gefunden")
    if slot_a.group_id != group_id or slot_b.group_id != group_id:
        raise HTTPException(status_code=403, detail="Slot gehört nicht zur Gruppe")

    await create_snapshot(db, group_id, reason="swap", created_by=user.sub)

    now = datetime.now(timezone.utc)
    slot_a.ue_node_id, slot_b.ue_node_id = slot_b.ue_node_id, slot_a.ue_node_id
    slot_a.stunde_node_id, slot_b.stunde_node_id = slot_b.stunde_node_id, slot_a.stunde_node_id
    slot_a.thema, slot_b.thema = slot_b.thema, slot_a.thema
    slot_a.updated_at = now
    slot_b.updated_at = now

    await db.commit()
    await db.refresh(slot_a)
    await db.refresh(slot_b)
    return [slot_a, slot_b]


# ── POST /planning/groups/{group_id}/units ────────────────────────────────────


@router.post("/groups/{group_id}/units", response_model=UnitRead, status_code=201)
async def create_unit(
    group_id: int,
    payload: UnitCreate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    group = await require_group_teacher(group_id, user, db)

    ue_node = await create_unit_node(
        db=db,
        group_id=group_id,
        group_subject_id=group.subject_id,
        user=user,
        titel=payload.titel,
        farbe=payload.farbe,
        kapitel_node_id=payload.kapitel_node_id,
    )

    kapitel_std = None
    if payload.kapitel_node_id:
        kapitel_std = await _kapitel_std(db, payload.kapitel_node_id)

    return UnitRead(
        id=ue_node.id,
        title=ue_node.title,
        metadata_=ue_node.metadata_ or {},
        kapitel_node_id=payload.kapitel_node_id,
        kapitel_std=kapitel_std,
        updated_at=ue_node.updated_at,
    )


# ── PATCH /planning/groups/{group_id}/units/{node_id} ─────────────────────────


@router.patch("/groups/{group_id}/units/{node_id}", response_model=UnitRead)
async def update_unit(
    group_id: int,
    node_id: UUID,
    payload: UnitUpdate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    ue_node = await update_unit_node(
        db=db,
        node_id=node_id,
        group_id=group_id,
        titel=payload.titel,
        farbe=payload.farbe,
        kapitel_node_id=payload.kapitel_node_id,
        update_kapitel="kapitel_node_id" in payload.model_fields_set,
    )

    kapitel_node_id, kapitel_std = await _kapitel_ref(db, ue_node.id)
    return UnitRead(
        id=ue_node.id,
        title=ue_node.title,
        metadata_=ue_node.metadata_ or {},
        kapitel_node_id=kapitel_node_id,
        kapitel_std=kapitel_std,
        updated_at=ue_node.updated_at,
    )


# ── DELETE /planning/groups/{group_id}/units/{node_id} ────────────────────────


@router.delete("/groups/{group_id}/units/{node_id}", status_code=204)
async def delete_unit(
    group_id: int,
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)
    await delete_unit_node(db=db, node_id=node_id, group_id=group_id)


# ── GET /planning/groups/{group_id}/units ────────────────────────────────────


@router.get("/groups/{group_id}/units", response_model=list[UnitRead])
async def list_units(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    units = await _load_units(db, group_id)
    result = []
    for ue in units:
        kapitel_node_id, kapitel_std = await _kapitel_ref(db, ue.id)
        result.append(
            UnitRead(
                id=ue.id,
                title=ue.title,
                metadata_=ue.metadata_ or {},
                kapitel_node_id=kapitel_node_id,
                kapitel_std=kapitel_std,
                updated_at=ue.updated_at,
            )
        )
    return result


# ── GET /planning/groups/{group_id}/curriculum-chapters ───────────────────────


@router.get(
    "/groups/{group_id}/curriculum-chapters",
    response_model=GroupCurriculaRead,
)
async def get_group_curriculum_chapters(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Zur Gruppe passende Curricula mit Kapiteln (Quelle für den UE-Picker)."""
    await require_group_teacher(group_id, user, db)

    resolved = await resolve_group_curricula(db, group_id)
    return GroupCurriculaRead(
        curricula=[
            CurriculumOption(
                curriculum_id=cur.curriculum_id,
                titel=cur.titel,
                jahrgangsstufe=cur.jahrgangsstufe,
                kapitel=[
                    CurriculumKapitelOption(
                        id=k.id,
                        titel=k.titel,
                        std=k.std,
                        reihenfolge=k.reihenfolge,
                        ues=k.ues,
                    )
                    for k in cur.kapitel
                ],
            )
            for cur in resolved.curricula
        ],
        grade=resolved.grade,
        grade_unbekannt=resolved.grade_unbekannt,
    )


# ── POST /planning/units/{node_id}/lessons ────────────────────────────────────


@router.post("/units/{node_id}/lessons", response_model=dict, status_code=201)
async def create_lesson(
    node_id: UUID,
    payload: LessonCreate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    ue_node = await db.get(ContextNode, node_id)
    if ue_node is None or ue_node.status != "active":
        raise HTTPException(status_code=404, detail="Unterrichtseinheit nicht gefunden")
    if ue_node.content_type != "unterrichtseinheit":
        raise HTTPException(status_code=422, detail="Knoten ist keine Unterrichtseinheit")

    group_id = ue_node.write_scope_group_id
    if group_id is None:
        raise HTTPException(status_code=422, detail="UE hat keine Gruppe")

    await require_group_teacher(group_id, user, db)

    if payload.slot_id:
        slot = await db.get(LessonSlot, payload.slot_id)
        if slot is None:
            raise HTTPException(status_code=404, detail="Slot nicht gefunden")
        if slot.group_id != group_id:
            raise HTTPException(status_code=403, detail="Slot gehört nicht zur Gruppe")

    # Vorgängerstunde für follows-Kante ermitteln
    last_lesson = await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(
            ContextEdge.to_node_id == node_id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "unterrichtsstunde",
            ContextNode.status == "active",
        )
        .order_by(ContextNode.created_at.desc())
        .limit(1)
    )
    predecessor = last_lesson.scalar_one_or_none()

    stunde = ContextNode(
        category="artifact",
        content_type="unterrichtsstunde",
        title=payload.titel,
        read_scope="group",
        write_scope="group",
        read_scope_group_id=group_id,
        write_scope_group_id=group_id,
        owner_pseudonym=user.sub,
        subject_id=ue_node.subject_id,
        metadata_={"phasen": []},
        status="active",
    )
    db.add(stunde)
    await db.flush()

    db.add(ContextEdge(
        from_node_id=stunde.id,
        to_node_id=node_id,
        relation="part_of",
        metadata_={},
    ))

    if predecessor:
        db.add(ContextEdge(
            from_node_id=stunde.id,
            to_node_id=predecessor.id,
            relation="follows",
            metadata_={},
        ))

    if payload.slot_id:
        slot = await db.get(LessonSlot, payload.slot_id)
        if slot:
            await create_snapshot(db, group_id, reason="edit", created_by=user.sub)
            slot.stunde_node_id = stunde.id
            slot.ue_node_id = ue_node.id
            slot.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(stunde)
    return {"id": str(stunde.id), "title": stunde.title}


# ── POST /planning/slots/{slot_id}/lesson ─────────────────────────────────────


@router.post("/slots/{slot_id}/lesson", response_model=dict, status_code=201)
async def create_lesson_for_slot(
    slot_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Entwurf **vom Termin aus** anlegen — auch ohne Unterrichtseinheit.

    Die ältere Route `POST /units/{node_id}/lessons` hängt am Einheitenknoten, weil sie
    Gruppe und Fach von dort nimmt. Ein Termin ohne Einheit kann darüber keinen Entwurf
    bekommen — und das ist der Normalfall am Anfang eines Schuljahres: Der Stundenplan
    steht, die Jahresplanung noch nicht.

    Beides steht aber genauso am Slot. Die **Leseseite trägt das längst**: `get_lesson`
    lässt `ue_edge` fehlen, `_lesson_nav` fängt `unit_id is None` ab, und die
    Jahresplanung liest `stunde_node_id` vom Slot statt über die Einheit. Gesperrt war
    nur das Anlegen.

    Eine so entstandene Stunde zählt in **keiner** Einheitenbilanz mit — sie gehört zu
    keiner. Das ist kein Mangel, sondern die Aussage: Die Zuordnung steht noch aus. Wird
    die Einheit später am Slot gesetzt, zieht `PATCH /planning/slots/{id}` die Kante nach.
    """
    slot = await db.get(LessonSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")

    await require_group_teacher(slot.group_id, user, db)

    # ⚠️ **Idempotent.** Der Aufruf hängt an einem Klick auf den Stundentitel; ein
    # Doppelklick oder ein zweiter Tab darf keinen zweiten Entwurf erzeugen. Der Slot
    # führt nur *einen* — der Überzählige wäre unauffindbar und bliebe für immer liegen.
    if slot.stunde_node_id:
        vorhanden = await db.get(ContextNode, slot.stunde_node_id)
        if vorhanden is not None and vorhanden.status == "active":
            return {"id": str(vorhanden.id), "title": vorhanden.title, "neu": False}

    ue_node = None
    if slot.ue_node_id:
        kandidat = await db.get(ContextNode, slot.ue_node_id)
        if kandidat is not None and kandidat.status == "active":
            ue_node = kandidat

    if ue_node is not None:
        subject_id = ue_node.subject_id
    else:
        group = await db.get(Group, slot.group_id)
        subject_id = group.subject_id if group else None

    stunde = ContextNode(
        category="artifact",
        content_type="unterrichtsstunde",
        title=(slot.thema or "").strip() or "Neue Stunde",
        read_scope="group",
        write_scope="group",
        read_scope_group_id=slot.group_id,
        write_scope_group_id=slot.group_id,
        owner_pseudonym=user.sub,
        subject_id=subject_id,
        metadata_={"phasen": []},
        status="active",
    )
    db.add(stunde)
    await db.flush()

    # Einordnung nur, wenn es eine Einheit gibt — sonst hängt die Stunde am Slot allein.
    if ue_node is not None:
        db.add(ContextEdge(
            from_node_id=stunde.id,
            to_node_id=ue_node.id,
            relation="part_of",
            metadata_={},
        ))
        vorgaenger = await db.execute(
            sa.select(ContextNode)
            .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
            .where(
                ContextEdge.to_node_id == ue_node.id,
                ContextEdge.relation == "part_of",
                ContextNode.content_type == "unterrichtsstunde",
                ContextNode.status == "active",
                ContextNode.id != stunde.id,
            )
            .order_by(ContextNode.created_at.desc())
            .limit(1)
        )
        letzte = vorgaenger.scalar_one_or_none()
        if letzte is not None:
            db.add(ContextEdge(
                from_node_id=stunde.id,
                to_node_id=letzte.id,
                relation="follows",
                metadata_={},
            ))

    await create_snapshot(db, slot.group_id, reason="edit", created_by=user.sub)
    slot.stunde_node_id = stunde.id
    slot.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(stunde)
    return {"id": str(stunde.id), "title": stunde.title, "neu": True}

# ── GET /planning/groups/{group_id}/balance ───────────────────────────────────


@router.get("/groups/{group_id}/balance", response_model=BalanceRead)
async def get_balance(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    slots_result = await db.execute(
        sa.select(LessonSlot).where(LessonSlot.group_id == group_id)
    )
    slots = slots_result.scalars().all()

    units = await _load_units(db, group_id)
    return await _build_balance(db, group_id, units, slots)


# ── GET /planning/groups/{group_id}/overhang ──────────────────────────────────


@router.get("/groups/{group_id}/overhang", response_model=list[OverhangFinding])
async def get_overhang(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Überhang-Befunde pro UE für die Assistenten-Hinweisleiste (UP-6 Schritt 8)."""
    await require_group_teacher(group_id, user, db)
    return await detect_overhang(db, group_id)


# ── POST /planning/groups/{group_id}/snapshots ────────────────────────────────


@router.post(
    "/groups/{group_id}/snapshots", response_model=SnapshotRead, status_code=201
)
async def create_manual_snapshot(
    group_id: int,
    payload: SnapshotCreate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    snapshot = await create_snapshot(
        db,
        group_id,
        reason="manual",
        label=payload.label,
        created_by=user.sub,
    )
    return snapshot


# ── GET /planning/groups/{group_id}/snapshots ─────────────────────────────────


@router.get("/groups/{group_id}/snapshots", response_model=list[SnapshotRead])
async def list_snapshots(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    await require_group_teacher(group_id, user, db)

    result = await db.execute(
        sa.select(SlotPlanSnapshot)
        .where(SlotPlanSnapshot.group_id == group_id)
        .order_by(SlotPlanSnapshot.created_at.desc())
    )
    return result.scalars().all()


# ── POST /planning/snapshots/{snapshot_id}/restore ───────────────────────────


@router.post("/snapshots/{snapshot_id}/restore", response_model=dict)
async def restore_snapshot_endpoint(
    snapshot_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    snapshot = await db.get(SlotPlanSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot nicht gefunden")

    await require_group_teacher(snapshot.group_id, user, db)

    return await restore_snapshot(db, snapshot_id, user)


# ── Hilfsfunktion: Navigations-Reihenfolge innerhalb einer UE ─────────────────


async def _build_lesson_nav(
    db: AsyncSession,
    node_id: UUID,
    unit_id: UUID | None,
) -> LessonNav:
    if unit_id is None:
        return LessonNav(prev_node_id=None, next_node_id=None, position=1, total=1)

    lessons_result = await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(
            ContextEdge.to_node_id == unit_id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "unterrichtsstunde",
            ContextNode.status == "active",
        )
    )
    all_lessons = {n.id: n for n in lessons_result.scalars().all()}

    if not all_lessons:
        return LessonNav(prev_node_id=None, next_node_id=None, position=1, total=1)

    follows_result = await db.execute(
        sa.select(ContextEdge).where(
            ContextEdge.from_node_id.in_(list(all_lessons.keys())),
            ContextEdge.relation == "follows",
        )
    )
    # follows[a] = b: lesson a follows lesson b (b is predecessor of a)
    follows = {e.from_node_id: e.to_node_id for e in follows_result.scalars().all()}

    # Build ordered list: first lesson has no outgoing follows edge
    first_candidates = set(all_lessons.keys()) - set(follows.keys())
    if not first_candidates:
        ordered = [n.id for n in sorted(all_lessons.values(), key=lambda n: n.created_at)]
    else:
        current = next(iter(first_candidates))
        ordered = [current]
        reverse_follows = {v: k for k, v in follows.items()}
        visited = {current}
        while current in reverse_follows and reverse_follows[current] not in visited:
            current = reverse_follows[current]
            ordered.append(current)
            visited.add(current)

    total = len(ordered)
    try:
        pos = ordered.index(node_id) + 1
    except ValueError:
        pos = total

    return LessonNav(
        prev_node_id=ordered[pos - 2] if pos > 1 else None,
        next_node_id=ordered[pos] if pos < total else None,
        position=pos,
        total=total,
    )


# ── GET /planning/lessons/{node_id} ──────────────────────────────────────────


@router.get("/lessons/{node_id}", response_model=LessonRead)
async def get_lesson(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    lesson = await db.get(ContextNode, node_id)
    if lesson is None or lesson.status != "active" or lesson.content_type != "unterrichtsstunde":
        raise HTTPException(status_code=404, detail="Stunde nicht gefunden")

    group_id = lesson.write_scope_group_id
    if group_id is None:
        raise HTTPException(status_code=422, detail="Stunde hat keine Gruppe")
    # Mitgliedschaft **oder** Eigentum; Letzteres nur lesend (Archiv-Fall).
    darf_bearbeiten = await zugang_zur_stunde(lesson, user, db)

    # Übergeordnete UE
    ue_edge_result = await db.execute(
        sa.select(ContextEdge).where(
            ContextEdge.from_node_id == node_id,
            ContextEdge.relation == "part_of",
        )
    )
    ue_edge = ue_edge_result.scalar_one_or_none()
    ue_ctx: LessonUeContext | None = None
    unit_id: UUID | None = None
    if ue_edge:
        unit_id = ue_edge.to_node_id
        ue_node = await db.get(ContextNode, unit_id)
        if ue_node:
            ue_ctx = LessonUeContext(
                id=ue_node.id,
                titel=ue_node.title,
                farbe=(ue_node.metadata_ or {}).get("farbe", 0),
            )

    # Slot-Kontext
    slot_result = await db.execute(
        sa.select(LessonSlot).where(LessonSlot.stunde_node_id == node_id)
    )
    slot = slot_result.scalar_one_or_none()
    slot_ctx: LessonSlotContext | None = None
    if slot:
        slot_ctx = LessonSlotContext(
            id=slot.id,
            date=slot.date,
            start_period=slot.start_period,
            periods=slot.periods,
            verfuegbare_min=slot.periods * 45,
        )

    nav = await _build_lesson_nav(db, node_id, unit_id)
    meta = lesson.metadata_ or {}

    # Jahrgang der Gruppe (gleiche Quelle wie die Curriculum-Anzeige) — für die
    # editionsbewusste IK/PK-Auswahl in der Stundenplanung. Kursstufe → None.
    resolved_curricula = await resolve_group_curricula(db, group_id)

    return LessonRead(
        id=lesson.id,
        titel=lesson.title,
        stundenziel=meta.get("stundenziel"),
        phasen=meta.get("phasen", []),
        refs=meta.get("refs", []),
        refs_dismissed=[str(x) for x in meta.get("refs_dismissed", [])],
        ue=ue_ctx,
        slot=slot_ctx,
        nav=nav,
        group_id=group_id,
        subject_id=lesson.subject_id,
        grade=resolved_curricula.grade,
        darf_bearbeiten=darf_bearbeiten,
        updated_at=lesson.updated_at,
    )


# ── PATCH /planning/lessons/{node_id} ────────────────────────────────────────


@router.patch("/lessons/{node_id}", response_model=dict)
async def patch_lesson(
    node_id: UUID,
    payload: LessonUpdate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    lesson = await db.get(ContextNode, node_id)
    if lesson is None or lesson.status != "active" or lesson.content_type != "unterrichtsstunde":
        raise HTTPException(status_code=404, detail="Stunde nicht gefunden")

    group_id = lesson.write_scope_group_id
    if group_id is None:
        raise HTTPException(status_code=422, detail="Stunde hat keine Gruppe")
    await require_group_teacher(group_id, user, db)

    # Vor dem Snapshot: Ein abgelehnter Schreibversuch soll keinen Wiederherstellungspunkt
    # erzeugen — sonst füllt ein Client mit veraltetem Stand den Verlauf mit Einträgen,
    # hinter denen keine Änderung steht.
    vorbedingung.pruefe(lesson.updated_at, payload.expected_updated_at, "Diese Stunde")

    if payload.phasen is not None:
        for phase in payload.phasen:
            try:
                phase.validate_prio()
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))

    await create_snapshot(db, group_id, reason="edit", created_by=user.sub)

    now = datetime.now(timezone.utc)
    if payload.titel is not None:
        lesson.title = payload.titel

    meta = dict(lesson.metadata_ or {})
    if payload.stundenziel is not None:
        meta["stundenziel"] = payload.stundenziel
    if payload.phasen is not None:
        # `exclude_none=False` schreibt eine fehlende Kennung als `"id": null` in
        # die Metadaten — deshalb wird sie hier vergeben und nicht erst dort
        # bemerkt, wo etwas auf sie zeigt.
        meta["phasen"] = sichere_phasen_kennungen(
            [p.model_dump(exclude_none=False, mode="json") for p in payload.phasen]
        )
    if payload.refs is not None:
        meta["refs"] = [r.model_dump(mode="json") for r in payload.refs]
    if payload.refs_dismissed is not None:
        meta["refs_dismissed"] = [str(rid) for rid in payload.refs_dismissed]

    lesson.metadata_ = meta
    lesson.updated_at = now
    await synchronisiere_materialkanten(db, lesson.id, meta)
    await db.commit()

    # Der neue Stand gehört in die Antwort: Ein Client mit Vorbedingung braucht ihn für
    # den nächsten Schreibversuch. Ohne ihn müsste er nach jedem Schreiben neu lesen —
    # und in der Lücke dazwischen wäre er wieder veraltet.
    return {"ok": True, "updated_at": now}


# ── POST /planning/slots/{slot_id}/review ────────────────────────────────────


@router.post("/slots/{slot_id}/review", response_model=ReviewResultRead, status_code=200)
async def create_review(
    slot_id: UUID,
    payload: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    slot = await db.get(LessonSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot nicht gefunden")
    await require_group_teacher(slot.group_id, user, db)
    if slot.stunde_node_id is None:
        raise HTTPException(status_code=409, detail="Slot hat keine Stunde")
    if slot.nachbereitet_at is not None:
        raise HTTPException(status_code=409, detail="Slot bereits nachbereitet")

    from app.planning.review_service import complete_review

    try:
        result = await complete_review(
            db,
            slot_id,
            group_id=slot.group_id,
            phasen_status=payload.phasen_status,
            reflexion=payload.reflexion,
            refs_offen=payload.refs_offen,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return ReviewResultRead(
        engagements_written=result.engagements_written,
        engagements_skipped=result.engagements_skipped,
        refs_offen=result.refs_offen,
        open_phases=result.open_phases,
    )


# ── DELETE /planning/slots/{slot_id}/review ───────────────────────────────────


@router.delete("/slots/{slot_id}/review", response_model=dict)
async def undo_review_endpoint(
    slot_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    slot = await db.get(LessonSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot nicht gefunden")
    await require_group_teacher(slot.group_id, user, db)
    if slot.nachbereitet_at is None:
        raise HTTPException(status_code=409, detail="Slot ist nicht nachbereitet")

    from app.planning.review_service import undo_review

    deleted = await undo_review(db, slot_id, group_id=slot.group_id)
    return {"ok": True, "deleted_engagements": deleted}


# ── GET /planning/groups/{group_id}/review-status ────────────────────────────


@router.get("/groups/{group_id}/review-status", response_model=list[ReviewStatusItem])
async def get_review_status(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Vergangene Slots mit Stunde, die noch nicht nachbereitet wurden."""
    await require_group_teacher(group_id, user, db)

    from datetime import date as date_type
    today = date_type.today()

    result = await db.execute(
        sa.select(LessonSlot).where(
            LessonSlot.group_id == group_id,
            LessonSlot.stunde_node_id.is_not(None),
            LessonSlot.kategorie.in_(["unterricht", "vertretung"]),
            LessonSlot.date < today,
        ).order_by(LessonSlot.date.desc())
    )
    slots = result.scalars().all()

    items: list[ReviewStatusItem] = []
    for slot in slots:
        stunde = await db.get(ContextNode, slot.stunde_node_id)
        items.append(
            ReviewStatusItem(
                slot_id=slot.id,
                date=slot.date,
                stunde_node_id=slot.stunde_node_id,
                titel=stunde.title if stunde else None,
                nachbereitet_auto=slot.nachbereitet_auto,
            )
        )
    return items


# ── GET /planning/lessons/{node_id}/export ────────────────────────────────────


@router.get("/lessons/{node_id}/export")
async def export_lesson(
    node_id: UUID,
    format: str = "md",  # md | pdf | docx
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    from fastapi.responses import Response

    lesson = await db.get(ContextNode, node_id)
    if lesson is None or lesson.status != "active" or lesson.content_type != "unterrichtsstunde":
        raise HTTPException(status_code=404, detail="Stunde nicht gefunden")

    group_id = lesson.write_scope_group_id
    if group_id is None:
        raise HTTPException(status_code=422, detail="Stunde hat keine Gruppe")
    await require_group_teacher(group_id, user, db)

    from app.planning.lesson_export import build_lesson_export, export_docx, export_markdown, export_pdf

    data = await build_lesson_export(db, node_id)

    if format == "md":
        content = export_markdown(data)
        filename = f"{data.datum}-{data.gruppe_slug}-{data.titel_slug}.md"
        return Response(
            content=content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    elif format == "pdf":
        content = await export_pdf(data)
        filename = f"{data.datum}-{data.gruppe_slug}-{data.titel_slug}.pdf"
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    elif format == "docx":
        content = export_docx(data)
        filename = f"{data.datum}-{data.gruppe_slug}-{data.titel_slug}.docx"
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    else:
        raise HTTPException(status_code=422, detail=f"Unbekanntes Format: {format}")


# ── GET /planning/mein-tag ────────────────────────────────────────────────────


class StundeAmTagRead(BaseModel):
    slot_id: UUID
    group_id: int
    gruppe: str
    # Für den Absprung in die Planung: die Route lautet
    # `/subjects/{slug}/groups/{id}/planner`. Ohne den Slug baut die Oberfläche einen
    # toten Link — oder muss das Fach in einer zweiten Runde nachschlagen.
    subject_slug: str | None
    # Icon und Farbe des Fachs — die Zeile trägt sie am Anfang, damit sich der Tag
    # überfliegen lässt, ohne jeden Gruppennamen zu lesen.
    subject_icon: str | None
    subject_color: str | None
    start_period: int | None
    periods: int
    stunde: str
    kategorie: str
    thema: str | None
    hat_entwurf: bool
    # Ohne die Id lässt sich der Weg in den Stundenentwurf nicht bauen.
    stunde_node_id: UUID | None
    ue_node_id: UUID | None
    ue_titel: str | None
    anpassung_noetig: bool


class TagRead(BaseModel):
    datum: date
    ist_heute: bool
    stunden: list[StundeAmTagRead]
    # Nur bei leerem Tag: warum. `wochenende` | `ferien` | `feiertag` |
    # `unterrichtsfrei` | `kein_unterricht` | `ausserhalb_schuljahr`.
    grund: str | None = None


class MeinTagRead(BaseModel):
    heute: TagRead
    naechster: TagRead | None
    # Ob die Lehrkraft überhaupt Unterrichtsgruppen hat, und ob darin geplant ist.
    # ⚠️ **Die dritte Lage.** „Heute kein Unterricht" und „noch nichts geplant" sind
    # verschiedene Auskünfte: Die erste ist eine Feststellung, die zweite eine
    # Aufforderung. Ohne diese beiden Angaben könnte die Oberfläche sie nicht trennen.
    hat_gruppen: bool
    hat_planung: bool


@router.get("/mein-tag", response_model=MeinTagRead)
async def get_mein_tag(
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_TEACHER_OR_ADMIN),
):
    """Die eigenen Stunden für heute und den nächsten Schultag — für die Startseite.

    **Eine Abfrage, nicht eine je Gruppe.** Eine Lehrkraft hat schnell zehn Gruppen;
    zehn Rundreisen für eine Seite, die beim Anmelden sofort dastehen soll, wären die
    falsche Bauform. Gefiltert wird über die Lehrkraft-Mitgliedschaften — **nicht**
    über `require_group_teacher` je Gruppe, das gäbe es hier gar nicht zu prüfen.

    ⚠️ **Der Filter ist die Zugriffsregel.** Fällt er weg, stehen die Stunden fremder
    Kolleg:innen auf der eigenen Startseite. Ein Wächtertest hält das fest.

    Geholt werden nur die Slots **zweier Tage**, nicht das Schuljahr: Anders als beim
    „Jetzt"-Block braucht die Startseite keinen Fortschritt einer Einheit, nur den Tag.
    """
    cfg = load_school_year()
    heute = date.today()
    naechster = mein_tag_modul.naechster_schultag(heute, cfg)
    tage = [d for d in (heute, naechster) if d is not None]

    eigene = sa.select(GroupMembership.group_id).where(
        GroupMembership.pseudonym == user.sub,
        GroupMembership.role_in_group == "teacher",
    )
    zeilen = await db.execute(
        sa.select(
            LessonSlot, Group.name, Group.display_name,
            Subject.slug, Subject.icon, Subject.color,
        )
        .join(Group, Group.id == LessonSlot.group_id)
        .outerjoin(Subject, Subject.id == Group.subject_id)
        .where(LessonSlot.group_id.in_(eigene), LessonSlot.date.in_(tage))
    )
    slots: list[LessonSlot] = []
    namen: dict[int, str] = {}
    faecher: dict[int, tuple[str | None, str | None, str | None]] = {}
    for slot, name, anzeige, fach_slug, fach_icon, fach_farbe in zeilen.all():
        slots.append(slot)
        namen[slot.group_id] = anzeige or name
        faecher[slot.group_id] = (fach_slug, fach_icon, fach_farbe)

    auswahl = mein_tag_modul.waehle(slots, heute, cfg)

    # Einheitstitel in einer Abfrage — sonst eine je Stunde.
    ue_ids = {
        s.ue_node_id
        for tag in (auswahl.heute, auswahl.naechster)
        if tag is not None
        for s in tag.stunden
        if s.ue_node_id is not None
    }
    titel: dict[UUID, str] = {}
    if ue_ids:
        res = await db.execute(
            sa.select(ContextNode.id, ContextNode.title).where(ContextNode.id.in_(ue_ids))
        )
        titel = {nid: t for nid, t in res.all()}

    def als_tag(tag) -> TagRead:
        return TagRead(
            datum=tag.datum,
            ist_heute=tag.ist_heute,
            grund=tag.grund,
            stunden=[
                StundeAmTagRead(
                    slot_id=s.slot_id,
                    group_id=s.group_id,
                    gruppe=namen.get(s.group_id, ""),
                    subject_slug=faecher.get(s.group_id, (None, None, None))[0],
                    subject_icon=faecher.get(s.group_id, (None, None, None))[1],
                    subject_color=faecher.get(s.group_id, (None, None, None))[2],
                    start_period=s.start_period,
                    periods=s.periods,
                    stunde=s.stundenbezeichnung,
                    kategorie=s.kategorie,
                    thema=s.thema,
                    hat_entwurf=s.hat_entwurf,
                    stunde_node_id=s.stunde_node_id,
                    ue_node_id=s.ue_node_id,
                    ue_titel=titel.get(s.ue_node_id) if s.ue_node_id else None,
                    anpassung_noetig=s.anpassung_noetig,
                )
                for s in tag.stunden
            ],
        )

    # Zwei billige Zahlen statt einer Vermutung in der Oberfläche.
    gruppen_anzahl = await db.scalar(
        sa.select(sa.func.count()).select_from(eigene.subquery())
    )
    planung_vorhanden = await db.scalar(
        sa.select(sa.literal(True))
        .where(sa.exists(sa.select(LessonSlot.id).where(LessonSlot.group_id.in_(eigene))))
    )

    return MeinTagRead(
        heute=als_tag(auswahl.heute),
        naechster=als_tag(auswahl.naechster) if auswahl.naechster else None,
        hat_gruppen=bool(gruppen_anzahl),
        hat_planung=bool(planung_vorhanden),
    )


# ── GET /planning/mein-tag/schueler ───────────────────────────────────────────


class FachAmTagRead(BaseModel):
    """Eine Stunde, wie Schüler:innen sie sehen.

    ⚠️ **Ein eigenes Modell, kein gefiltertes.** Thema, Unterrichtseinheit und
    Stundenentwurf sind Material der Lehrkraft (`docs/user/datenschutz.md`, „Was
    Schüler:innen mitbekommen"). Sie hier wegzulassen wäre eine Zusage, die jeder
    spätere Umbau von `StundeAmTagRead` unbemerkt brechen könnte — ein Feld ergänzt,
    und es steht in beiden Antworten. Zwei getrennte Modelle können das nicht: Was
    hier nicht steht, lässt sich nicht durchreichen.
    """

    group_id: int
    # Aus Schülersicht **ist** die Unterrichtsgruppe das Fach (CLAUDE.md,
    # Fachbegriff-Tabelle). Angezeigt wird deshalb ihr Anzeigename.
    fach: str
    subject_slug: str | None
    subject_icon: str | None
    subject_color: str | None
    start_period: int | None
    periods: int
    stunde: str
    # Ein Wort oder nichts — siehe `mein_tag.SCHUELER_HINWEISE`. **Nicht** die rohe
    # Kategorie: `puffer` ist Planungsvokabular und ginge niemanden sonst etwas an.
    hinweis: str | None


class SchuelerTagRead(BaseModel):
    datum: date
    ist_heute: bool
    faecher: list[FachAmTagRead]
    grund: str | None = None


class MeinTagSchuelerRead(BaseModel):
    heute: SchuelerTagRead
    naechster: SchuelerTagRead | None
    hat_gruppen: bool


@router.get("/mein-tag/schueler", response_model=MeinTagSchuelerRead)
async def get_mein_tag_schueler(
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(get_current_user),
):
    """Die heutigen Fächer — die Startseite aus Schülersicht.

    Gleiche Auswahlregel wie bei der Lehrkraft (`mein_tag.waehle`), **anderer
    Ausschnitt**: Fach, Stunde und im Ausnahmefall ein Wort dazu. Kein Thema, kein
    Entwurf, keine Unterrichtseinheit.

    ⚠️ **Die Freigabe wird hier serverseitig gelesen, nicht in der Oberfläche.** Für die
    Fachübersicht filtert das Frontend (`myGroups.freigegebeneGruppen`) — das genügt
    dort, weil die Liste ohnehin nur Namen trägt. Hier ginge es um den **Stundenplan**
    einer nicht freigegebenen Gruppe; der hat in der Antwort nichts verloren, auch nicht
    ungenutzt im JSON. Gelesen wird `student_visible` nur im Erprobungsbetrieb
    (`STUDENT_SUBJECTS_OPT_IN`) — dieselbe Bedingung wie überall sonst.
    """
    cfg = load_school_year()
    heute = date.today()
    naechster = mein_tag_modul.naechster_schultag(heute, cfg)
    tage = [d for d in (heute, naechster) if d is not None]

    eigene = sa.select(GroupMembership.group_id).where(
        GroupMembership.pseudonym == user.sub,
        GroupMembership.role_in_group == "student",
    )

    bedingungen = [LessonSlot.group_id.in_(eigene), LessonSlot.date.in_(tage)]
    if settings.student_subjects_opt_in:
        bedingungen.append(Group.student_visible.is_(True))

    zeilen = await db.execute(
        sa.select(
            LessonSlot, Group.name, Group.display_name,
            Subject.slug, Subject.icon, Subject.color,
        )
        .join(Group, Group.id == LessonSlot.group_id)
        .outerjoin(Subject, Subject.id == Group.subject_id)
        .where(*bedingungen)
    )
    slots: list[LessonSlot] = []
    namen: dict[int, str] = {}
    faecher: dict[int, tuple[str | None, str | None, str | None]] = {}
    for slot, name, anzeige, fach_slug, fach_icon, fach_farbe in zeilen.all():
        slots.append(slot)
        namen[slot.group_id] = anzeige or name
        faecher[slot.group_id] = (fach_slug, fach_icon, fach_farbe)

    auswahl = mein_tag_modul.waehle(slots, heute, cfg)

    def als_tag(tag) -> SchuelerTagRead:
        return SchuelerTagRead(
            datum=tag.datum,
            ist_heute=tag.ist_heute,
            grund=tag.grund,
            faecher=[
                FachAmTagRead(
                    group_id=s.group_id,
                    fach=namen.get(s.group_id, ""),
                    subject_slug=faecher.get(s.group_id, (None, None, None))[0],
                    subject_icon=faecher.get(s.group_id, (None, None, None))[1],
                    subject_color=faecher.get(s.group_id, (None, None, None))[2],
                    start_period=s.start_period,
                    periods=s.periods,
                    stunde=s.stundenbezeichnung,
                    hinweis=s.schueler_hinweis,
                )
                for s in tag.stunden
            ],
        )

    gruppen_anzahl = await db.scalar(
        sa.select(sa.func.count()).select_from(eigene.subquery())
    )

    return MeinTagSchuelerRead(
        heute=als_tag(auswahl.heute),
        naechster=als_tag(auswahl.naechster) if auswahl.naechster else None,
        hat_gruppen=bool(gruppen_anzahl),
    )
