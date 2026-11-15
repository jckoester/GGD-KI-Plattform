"""Kompetenzen aus einem fremden Fach in Curricula reparieren (0.45, nach Schritt 3).

Bis 25.08.2026 (`cc71eca7`) löste der Curriculum-Import PK-Nummern **ohne Fach** auf —
`2.1.1` gibt es in über zwanzig Fächern. Ein Mathematik-Curriculum, das vor diesem Tag
importiert wurde, hängt deshalb an den PK von Kunst, Geographie, Chemie … Sichtbar wurde
das erst mit der Abdeckung (`fremdes_fach`, `curriculum_abdeckung.py`).

**Was repariert wird.** Je Lernsequenz die Spalten IK und PK der Einträge
(`eintraege[].ik`, `eintraege[].pk`), deren Knoten zu einem anderen Fach gehört. Gesucht wird
dieselbe Nummer im Fach und in der Bildungsplan-Fassung des Curriculums (IK zusätzlich im
Band); bei mehreren Treffern zählt nur ein aktiver. Gibt es genau einen, wandern Eintrag und
Kante (`develops` bzw. `references`) dorthin. Sonst bleibt alles, wie es ist, und der Fund
wird gemeldet — geraten wird nicht.

**Was nicht angefasst wird.** Verweise in Hinweisen und Material: Dort sind Kompetenzen
anderer Fächer gewollt. Steht der alte Knoten zugleich in einem Hinweis derselben
Lernsequenz, bleibt seine Kante und die neue kommt dazu.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.service import _normalize_ref, load_curriculum_tree
from app.db.models import ContextEdge, ContextNode, Subject

_TYP = {"ik": ("ik_kompetenz", "references"), "pk": ("pk_kompetenz", "develops")}


@dataclass
class Fund:
    curriculum: str
    lernsequenz: str
    typ: str            # "ik" | "pk"
    nr: str
    alt_fach: str
    alt_id: UUID
    neu_id: UUID | None  # None: nicht repariert
    grund: str = ""      # warum nicht


def _nr(ref: dict, alt: ContextNode) -> str:
    return ref.get("nr") or ref.get("pk_id") or (alt.metadata_ or {}).get("kompetenz_nr") or ""


async def _ersatz(db: AsyncSession, cur: ContextNode, typ: str, nr: str) -> tuple[UUID | None, str]:
    bp = (cur.metadata_ or {}).get("bp_version") or cur.bp_version
    bedingungen = [ContextNode.content_type == _TYP[typ][0], ContextNode.subject_id == cur.subject_id,
                   ContextNode.bp_version == bp, ContextNode.status != "deleted"]
    if typ == "ik" and cur.min_grade is not None and cur.max_grade is not None:
        bedingungen += [sa.or_(ContextNode.min_grade.is_(None), ContextNode.min_grade <= cur.max_grade),
                        sa.or_(ContextNode.max_grade.is_(None), ContextNode.max_grade >= cur.min_grade)]
    soll = _normalize_ref(nr)
    treffer = [k for k in (await db.execute(sa.select(ContextNode).where(*bedingungen))).scalars()
               if _normalize_ref((k.metadata_ or {}).get("kompetenz_nr") or "") == soll]
    if len(treffer) > 1:
        treffer = [k for k in treffer if k.status == "active"] or treffer
    if len(treffer) == 1:
        return treffer[0].id, ""
    if not treffer:
        return None, f"keine {typ.upper()} {nr} im Fach (Fassung {bp})"
    return None, f"{len(treffer)} Treffer für {typ.upper()} {nr} — mehrdeutig"


async def kompetenzen_reparieren(
    db: AsyncSession, *, curriculum_id: UUID | None = None, anwenden: bool = False,
) -> list[Fund]:
    """Findet (und mit ``anwenden``: repariert) fachfremde IK/PK in den Einträgen. Kein Commit."""
    bedingung = [ContextNode.content_type == "curriculum", ContextNode.status.in_(("active", "draft"))]
    if curriculum_id is not None:
        bedingung.append(ContextNode.id == curriculum_id)
    curricula = (await db.execute(sa.select(ContextNode).where(*bedingung).order_by(ContextNode.title))).scalars().all()
    faecher = dict((await db.execute(sa.select(Subject.id, Subject.name))).all())
    funde: list[Fund] = []

    for cur in curricula:
        if cur.subject_id is None:
            continue
        tree = await load_curriculum_tree(db, cur.id)
        for kap in (tree or {}).get("kapitel", []):
            for ls_baum in kap.get("lernsequenzen", []):
                funde += await _lernsequenz(db, cur, ls_baum, faecher, anwenden)
    if anwenden:
        await db.flush()
    return funde


async def _lernsequenz(db, cur: ContextNode, ls_baum: dict, faecher: dict, anwenden: bool) -> list[Fund]:
    meta = deepcopy(ls_baum.get("metadata") or {})
    eintraege = meta.get("eintraege") or []
    refs = [(typ, ref) for e in eintraege for typ in ("ik", "pk") for ref in (e.get(typ) or [])
            if isinstance(ref, dict) and ref.get("node_id")]
    if not refs:
        return []
    knoten = {str(k.id): k for k in (await db.execute(sa.select(ContextNode).where(
        ContextNode.id.in_({UUID(str(r["node_id"])) for _, r in refs})))).scalars()}

    funde, ersetzt = [], {}  # alt_id → neu_id
    for typ, ref in refs:
        alt = knoten.get(str(ref["node_id"]))
        if alt is None or alt.subject_id == cur.subject_id:
            continue
        if alt.id not in ersetzt:
            nr = _nr(ref, alt)
            neu_id, grund = await _ersatz(db, cur, typ, nr)
            ersetzt[alt.id] = neu_id
            funde.append(Fund(cur.title, ls_baum.get("title") or "", typ, nr,
                              faecher.get(alt.subject_id, "ohne Fach"), alt.id, neu_id, grund))
        if ersetzt[alt.id] is not None:
            ref["node_id"] = str(ersetzt[alt.id])

    if not anwenden or not any(ersetzt.values()):
        return funde

    ls = await db.get(ContextNode, UUID(str(ls_baum["id"])))
    ls.metadata_ = meta
    in_hinweisen = " ".join(str(e.get(f) or "") for e in eintraege for f in ("hinweise", "material"))
    typ_je_alt = {f.alt_id: f.typ for f in funde}
    for alt_id, neu_id in ersetzt.items():
        if neu_id is None:
            continue
        relation = _TYP[typ_je_alt[alt_id]][1]
        kanten = (await db.execute(sa.select(ContextEdge).where(
            ContextEdge.from_node_id == ls.id, ContextEdge.relation == relation,
            ContextEdge.to_node_id.in_((alt_id, neu_id))))).scalars().all()
        alte = [k for k in kanten if k.to_node_id == alt_id]
        hat_neue = any(k.to_node_id == neu_id for k in kanten)
        for k in alte:
            if str(alt_id) in in_hinweisen:  # gewollter Verweis im Hinweis: Kante bleibt
                continue
            if hat_neue:
                await db.delete(k)
            else:
                k.to_node_id, hat_neue = neu_id, True
        if not hat_neue:
            vorlage = alte[0].metadata_ if alte else {}
            db.add(ContextEdge(from_node_id=ls.id, to_node_id=neu_id, relation=relation,
                               metadata_=dict(vorlage or {})))
    return funde
