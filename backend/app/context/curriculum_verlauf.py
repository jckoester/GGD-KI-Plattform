"""Rückgängig für Curricula (0.46, Päckchen AP Teil B, Schritt 3).

**Sichern** (`sichern`): Vor jedem Speichern im Editor und vor jedem Schreibstapel des
Assistenten wird der ganze Baum festgehalten — Curriculum, Kapitel, Lernsequenzen mit allen
Feldern und Metadaten (Einträge mit IK, PK, Begriffen, Fachmethoden) und jede Kante, die einen
dieser Knoten berührt. Je Curriculum höchstens `VERLAUF_LIMIT` Stände, die ältesten fallen weg.

**Zurücknehmen** (`zuruecknehmen`): Der jüngste Stand wird wiederhergestellt und aus dem Verlauf
genommen; mehrfaches Zurücknehmen geht Stand für Stand zurück.
- Seitdem angelegte Kapitel und Lernsequenzen werden gelöscht, seitdem gelöschte kommen mit
  derselben Kennung zurück (der Editor löscht hart, `delete_node`).
- Kanten **aus** dem Baum (Gliederung, Kompetenzen, Material) werden durch die gesicherten ersetzt.
  Kanten **in** den Baum (eine Unterrichtseinheit am Kapitel) bleiben, wie sie sind; was beim
  Löschen eines Kapitels mit verschwand, kommt zurück, soweit die andere Seite noch existiert.
- ⚠️ **Der Status bleibt der heutige.** Wurde der Entwurf seitdem veröffentlicht, nimmt
  „Rückgängig“ Inhalte zurück, nicht die Veröffentlichung — Status ändert nur „Veröffentlichen“.
- Geänderte Knoten verlieren ihren Vektor; die Embedding-Nachholung holt ihn (nur `active`).

Rechte prüft der Aufrufer (`_require_curriculum_write`, für den Assistenten die Regel aus Teil A).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextEdge, ContextNode, CurriculumSnapshot

VERLAUF_LIMIT = 30

#: Felder eines Knotens, die ein Stand festhält. Nicht dabei: `status` (siehe oben), Zeitstempel,
#: Vektor.
FELDER = ("category", "content_type", "title", "title_locked", "content", "metadata_",
          "owner_pseudonym", "read_scope", "write_scope", "read_scope_group_id",
          "write_scope_group_id", "assistant_id", "subject_id", "min_grade", "max_grade", "niveau",
          "bp_version", "valid_until", "schuljahr")
_VEKTOR_FELDER = ("title", "content", "metadata_")


async def baum_ids(db: AsyncSession, curriculum_id: UUID) -> list[UUID]:
    """Curriculum, Kapitel und Lernsequenzen — jeder Status außer `deleted`."""
    kapitel = (await db.execute(
        sa.select(ContextNode.id).join(ContextEdge, ContextEdge.from_node_id == ContextNode.id).where(
            ContextEdge.to_node_id == curriculum_id, ContextEdge.relation == "part_of",
            ContextNode.content_type == "kapitel", ContextNode.status != "deleted"))).scalars().all()
    ls = []
    if kapitel:
        ls = (await db.execute(
            sa.select(ContextNode.id).join(ContextEdge, ContextEdge.from_node_id == ContextNode.id).where(
                ContextEdge.to_node_id.in_(kapitel), ContextEdge.relation == "part_of",
                ContextNode.content_type == "lernsequenz", ContextNode.status != "deleted"))).scalars().all()
    return [curriculum_id, *kapitel, *ls]


def _wert(v):
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


async def sichern(db: AsyncSession, curriculum_id: UUID, *, grund: str,
                  von: str | None) -> CurriculumSnapshot:
    """Hält den Baum fest und kürzt den Verlauf. Kein Commit."""
    ids = await baum_ids(db, curriculum_id)
    knoten = (await db.execute(sa.select(ContextNode).where(ContextNode.id.in_(ids)))).scalars().all()
    kanten = (await db.execute(sa.select(ContextEdge).where(
        sa.or_(ContextEdge.from_node_id.in_(ids), ContextEdge.to_node_id.in_(ids))))).scalars().all()
    payload = {
        "knoten": [{"id": str(n.id), **{f: _wert(getattr(n, f)) for f in FELDER}} for n in knoten],
        "kanten": [{"from": str(k.from_node_id), "to": str(k.to_node_id), "relation": k.relation,
                    "metadata": k.metadata_ or {}} for k in kanten],
    }
    # Zeit aus Python, nicht `now()`: Das ist die Zeit der Transaktion — zwei Stände in einer
    # (Assistent: sichern, schreiben, sichern) hätten sonst keine Reihenfolge.
    stand = CurriculumSnapshot(curriculum_id=curriculum_id, reason=grund, created_by=von, payload=payload,
                               created_at=datetime.now(timezone.utc))
    db.add(stand)
    await db.flush()

    ueberzaehlig = (await db.execute(
        sa.select(CurriculumSnapshot.id).where(CurriculumSnapshot.curriculum_id == curriculum_id)
        .order_by(CurriculumSnapshot.created_at.desc(), CurriculumSnapshot.id.desc())
        .offset(VERLAUF_LIMIT))).scalars().all()
    if ueberzaehlig:
        await db.execute(sa.delete(CurriculumSnapshot).where(CurriculumSnapshot.id.in_(ueberzaehlig)))
    return stand


async def _juengster(db: AsyncSession, curriculum_id: UUID) -> CurriculumSnapshot | None:
    return (await db.execute(
        sa.select(CurriculumSnapshot).where(CurriculumSnapshot.curriculum_id == curriculum_id)
        .order_by(CurriculumSnapshot.created_at.desc(), CurriculumSnapshot.id.desc()).limit(1)
    )).scalar_one_or_none()


async def verlauf(db: AsyncSession, curriculum_id: UUID, user_sub: str) -> dict:
    """Für den Knopf: wie viele Stände, und von wann der jüngste ist (ohne Pseudonyme)."""
    anzahl = await db.scalar(sa.select(sa.func.count()).where(
        CurriculumSnapshot.curriculum_id == curriculum_id))
    j = await _juengster(db, curriculum_id)
    return {"anzahl": anzahl or 0, "letzter": None if j is None else {
        "zeit": j.created_at, "grund": j.reason, "von_mir": j.created_by == user_sub}}


def _feld(f: str, v):
    return date.fromisoformat(v) if f == "valid_until" and v else v


async def zuruecknehmen(db: AsyncSession, curriculum: ContextNode) -> dict:
    """Stellt den jüngsten Stand wieder her und nimmt ihn aus dem Verlauf. Kein Commit."""
    stand = await _juengster(db, curriculum.id)
    if stand is None:
        raise HTTPException(status_code=404, detail="Es gibt nichts zurückzunehmen.")
    status = curriculum.status
    gesichert = {UUID(k["id"]): k for k in stand.payload.get("knoten", [])}
    jetzt = set(await baum_ids(db, curriculum.id))

    # 1. Seitdem dazugekommene Teile weg (Kanten folgen per CASCADE).
    neu = jetzt - set(gesichert) - {curriculum.id}
    if neu:
        await db.execute(sa.delete(ContextNode).where(ContextNode.id.in_(neu)))

    # 2. Gesicherte Knoten zurückschreiben, gelöschte mit derselben Kennung neu anlegen.
    for nid, daten in gesichert.items():
        node = await db.get(ContextNode, nid)
        if node is None:
            node = ContextNode(id=nid)
            db.add(node)
        alt = {f: getattr(node, f, None) for f in _VEKTOR_FELDER}
        for f in FELDER:
            setattr(node, f, _feld(f, daten.get(f)))
        if nid != curriculum.id:
            node.status = status
        if any(alt[f] != getattr(node, f) for f in _VEKTOR_FELDER):
            node.embedding = None
    await db.flush()

    # 3. Kanten: aus dem Baum ersetzen, in den Baum ergänzen.
    alle = jetzt | set(gesichert)
    await db.execute(sa.delete(ContextEdge).where(ContextEdge.from_node_id.in_(alle)))
    kanten = stand.payload.get("kanten", [])
    enden = {UUID(k[s]) for k in kanten for s in ("from", "to")}
    vorhanden = set((await db.execute(sa.select(ContextNode.id).where(
        ContextNode.id.in_(enden or {curriculum.id}), ContextNode.status != "deleted"))).scalars().all())
    for k in kanten:
        von, zu = UUID(k["from"]), UUID(k["to"])
        if von not in vorhanden or zu not in vorhanden:
            continue  # die andere Seite gibt es nicht mehr
        await db.execute(pg_insert(ContextEdge).values(
            from_node_id=von, to_node_id=zu, relation=k["relation"], metadata_=k.get("metadata") or {},
        ).on_conflict_do_nothing())
    await db.delete(stand)
    await db.flush()
    return {"zeit": stand.created_at, "grund": stand.reason}
