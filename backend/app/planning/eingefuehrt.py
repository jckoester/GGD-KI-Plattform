"""Welche Begriffe eine Unterrichtsgruppe schon hatte (0.20, Päckchen AC, Schritt 3).

Die Quelle für den Schüler-Chat: Die Vorab-Suche nimmt einen Begriff aus dem Graubereich als
sicheren Treffer, wenn die Gruppe ihn hatte (F2), und der Block „Aktueller Unterricht" nennt
die Titel über die letzten zwei Stunden hinaus (F4).

**Zwei Herkünfte** (F3 b, Jan 20.10.2026):

* *nachbereitet* — ``node_engagement(group_id, relation='introduced')``, geschrieben von der
  Nachbereitung (`review_service`) ohne die als offen markierten `refs`.
* *laut Plan* — die `refs` vergangener, **nicht** nachbereiteter Stunden. Die Auto-Bestätigung
  bestätigt eine Stunde erst, wenn die nächste vorbei ist; ohne diese Herkunft fehlte genau die
  letzte Stunde — dieselbe Falle wie 0.15 Plan B (`student_context.get_current_topic`).

**Nur Begriffe** (`BEGRIFF_TYPEN`): Die Nachbereitung trägt auch Kompetenzen, Methoden und
Material als „eingeführt" ein — die gehören nicht hierher. **Nur, was jedes Mitglied der Gruppe
lesen darf** (`fuer_gruppe_lesbar`, F6): Das Ergebnis ist für alle Mitglieder dasselbe.

⚠️ **„Laut Plan" kann falsch sein**: Eine ausgefallene Stunde, die nicht als Entfall gebucht
ist, zählt mit. Bekannte Unschärfe aus Plan B; der Block kennzeichnet die Herkunft, die
Vorab-Suche nimmt sie hin.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.visibility import fuer_gruppe_lesbar_clause
from app.db.models import ContextNode, LessonSlot, NodeEngagement
from app.planning.schemas import BEGRIFF_TYPEN
from app.planning.student_context import BEHANDELT_KATEGORIEN

NACHBEREITET = "nachbereitet"
LAUT_PLAN = "laut_plan"

#: Deckel für das Ergebnis — ein Schuljahr Chemie bringt grob 100 Begriffe; was darüber
#: hinausgeht, ist älter als alles, worauf ein Chat sich noch beziehen sollte.
EINGEFUEHRT_MAX = 150


@dataclass(frozen=True)
class Eingefuehrt:
    node_id: UUID
    titel: str
    #: :data:`NACHBEREITET`, wenn eine Nachbereitung ihn eingetragen hat — sonst :data:`LAUT_PLAN`.
    herkunft: str
    #: Datum der jüngsten Stunde, in der er vorkam; ``None`` bei einem Eintrag ohne Termin.
    datum: date | None
    #: Einheit dieser Stunde — für die Block-Zeile „laufende Einheit" (F4).
    ue_node_id: UUID | None


async def eingefuehrte_begriffe(
    db: AsyncSession, group_id: int, *, heute: date, deckel: int = EINGEFUEHRT_MAX
) -> list[Eingefuehrt]:
    """Die eingeführten Begriffe der Gruppe, die jüngsten zuerst, höchstens ``deckel``.

    Kommt ein Begriff mehrfach vor, zählt die jüngste Stunde für Datum und Einheit; die
    Herkunft ist *nachbereitet*, sobald eine Nachbereitung ihn eingetragen hat.
    """
    gefunden: dict[UUID, tuple[str, date | None, UUID | None]] = {}

    def merken(node_id: UUID, herkunft: str, datum: date | None, ue: UUID | None) -> None:
        alt = gefunden.get(node_id)
        if alt is None:
            gefunden[node_id] = (herkunft, datum, ue)
            return
        herkunft = NACHBEREITET if NACHBEREITET in (herkunft, alt[0]) else LAUT_PLAN
        if datum is not None and (alt[1] is None or datum > alt[1]):
            gefunden[node_id] = (herkunft, datum, ue)
        else:
            gefunden[node_id] = (herkunft, alt[1], alt[2])

    # 1. Nachbereitet — der Termin steht in `metadata.slot_id` (review_service).
    slot_id = NodeEngagement.metadata_["slot_id"].astext
    zeilen = (await db.execute(
        sa.select(NodeEngagement.node_id, LessonSlot.date, LessonSlot.ue_node_id,
                  NodeEngagement.created_at)
        .outerjoin(LessonSlot, sa.cast(LessonSlot.id, sa.Text) == slot_id)
        .where(NodeEngagement.group_id == group_id, NodeEngagement.relation == "introduced")
    )).all()
    for node_id, datum, ue, angelegt in zeilen:
        merken(node_id, NACHBEREITET, datum or (angelegt.date() if angelegt else None), ue)

    # 2. Laut Plan — vergangene, nicht nachbereitete Stunden mit Entwurf.
    slots = (await db.execute(
        sa.select(LessonSlot.stunde_node_id, LessonSlot.date, LessonSlot.ue_node_id).where(
            LessonSlot.group_id == group_id,
            LessonSlot.date < heute,
            LessonSlot.kategorie.in_(BEHANDELT_KATEGORIEN),
            LessonSlot.stunde_node_id.isnot(None),
            LessonSlot.nachbereitet_at.is_(None),
        )
    )).all()
    if slots:
        entwuerfe = dict((await db.execute(
            sa.select(ContextNode.id, ContextNode.metadata_)
            .where(ContextNode.id.in_({s.stunde_node_id for s in slots}))
        )).all())
        for stunde_id, datum, ue in slots:
            meta = entwuerfe.get(stunde_id)
            refs = meta.get("refs") if isinstance(meta, dict) else None
            for ref in refs or []:
                roh = ref.get("node_id") if isinstance(ref, dict) else None
                try:
                    merken(UUID(str(roh)), LAUT_PLAN, datum, ue)
                except ValueError:
                    continue

    if not gefunden:
        return []
    # Nur Begriffe, nur aktive, nur für alle lesbare.
    titel = dict((await db.execute(
        sa.select(ContextNode.id, ContextNode.title).where(
            ContextNode.id.in_(gefunden),
            ContextNode.content_type.in_(BEGRIFF_TYPEN),
            ContextNode.status == "active",
            fuer_gruppe_lesbar_clause(group_id),
        )
    )).all())
    liste = [
        Eingefuehrt(node_id=k, titel=titel[k], herkunft=h, datum=d, ue_node_id=u)
        for k, (h, d, u) in gefunden.items() if k in titel
    ]
    liste.sort(key=lambda e: (e.datum is None, -(e.datum.toordinal() if e.datum else 0), e.titel))
    return liste[:deckel]
