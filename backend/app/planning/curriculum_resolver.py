"""Auflösung: Gruppe → passende(s) Curriculum/Curricula mit Kapiteln.

Single Source of Truth für den UE↔Kapitel-Picker (Planner-UI) **und** das Assistent-Tool
`get_curriculum_chapters`. Match läuft strukturell über die Spalten min_grade/max_grade
(per `parse_grade_band` beim Schreiben befüllt), nicht über das freie jahrgangsstufe-Label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.grades import parse_class_grade
from app.db.models import ContextEdge, ContextNode, Group


@dataclass
class KapitelInfo:
    id: UUID
    titel: str
    std: int | None
    reihenfolge: int | None
    ues: list[str]  # Titel bereits verknüpfter Unterrichtseinheiten


@dataclass
class CurriculumChapters:
    curriculum_id: UUID
    titel: str
    jahrgangsstufe: str | None
    kapitel: list[KapitelInfo] = field(default_factory=list)


@dataclass
class GroupCurriculaResult:
    curricula: list[CurriculumChapters]
    grade: int | None
    grade_unbekannt: bool


async def _group_grade(db: AsyncSession, group: Group) -> int | None:
    """Jahrgang der teaching_group aus der verknüpften Klassengruppe ableiten."""
    if group.source_class_group_id is None:
        return None
    cls = await db.get(Group, group.source_class_group_id)
    return parse_class_grade(cls.name) if cls else None


async def _ue_titles_by_kapitel(db: AsyncSession, group_id: int) -> dict[UUID, list[str]]:
    """{kapitel_node_id: [ue_titel]} für alle UEs der Gruppe (references-Kanten)."""
    ues = (
        await db.execute(
            sa.select(ContextNode).where(
                ContextNode.content_type == "unterrichtseinheit",
                ContextNode.write_scope_group_id == group_id,
                ContextNode.status == "active",
            )
        )
    ).scalars().all()
    if not ues:
        return {}

    ue_by_id = {u.id: u.title for u in ues}
    edges = (
        await db.execute(
            sa.select(ContextEdge).where(
                ContextEdge.from_node_id.in_(list(ue_by_id.keys())),
                ContextEdge.relation == "references",
            )
        )
    ).scalars().all()

    result: dict[UUID, list[str]] = {}
    for edge in edges:
        result.setdefault(edge.to_node_id, []).append(ue_by_id[edge.from_node_id])
    return result


async def resolve_group_curricula(db: AsyncSession, group_id: int) -> GroupCurriculaResult:
    """Liefert die zur Gruppe passenden Curricula samt Kapiteln.

    Match: gleiches Fach (subject_id) und Jahrgang im Stufenband (min_grade/max_grade;
    NULL = gilt für alle Stufen). Lässt sich der Jahrgang nicht ableiten (Oberstufe,
    Gruppe ohne Klassenbezug), entfällt der Jahrgangsfilter und `grade_unbekannt=True`.
    """
    group = await db.get(Group, group_id)
    if group is None or group.subject_id is None:
        return GroupCurriculaResult(curricula=[], grade=None, grade_unbekannt=True)

    grade = await _group_grade(db, group)

    stmt = sa.select(ContextNode).where(
        ContextNode.content_type == "curriculum",
        ContextNode.subject_id == group.subject_id,
        ContextNode.status == "active",
    )
    if grade is not None:
        stmt = stmt.where(
            sa.or_(
                ContextNode.min_grade.is_(None),
                ContextNode.max_grade.is_(None),
                sa.and_(
                    ContextNode.min_grade <= grade,
                    ContextNode.max_grade >= grade,
                ),
            )
        )
    stmt = stmt.order_by(
        ContextNode.min_grade.nullsfirst(), ContextNode.title
    )
    curricula = (await db.execute(stmt)).scalars().all()

    ue_map = await _ue_titles_by_kapitel(db, group_id)

    result: list[CurriculumChapters] = []
    for cur in curricula:
        kap_nodes = (
            await db.execute(
                sa.select(ContextNode)
                .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
                .where(
                    ContextEdge.to_node_id == cur.id,
                    ContextEdge.relation == "part_of",
                    ContextNode.content_type == "kapitel",
                    ContextNode.status == "active",
                )
                .order_by(
                    ContextNode.metadata_["reihenfolge"].as_integer().nullslast()
                )
            )
        ).scalars().all()

        kapitel = [
            KapitelInfo(
                id=k.id,
                titel=k.title,
                std=(k.metadata_ or {}).get("std"),
                reihenfolge=(k.metadata_ or {}).get("reihenfolge"),
                ues=ue_map.get(k.id, []),
            )
            for k in kap_nodes
        ]
        result.append(
            CurriculumChapters(
                curriculum_id=cur.id,
                titel=cur.title,
                jahrgangsstufe=(cur.metadata_ or {}).get("jahrgangsstufe"),
                kapitel=kapitel,
            )
        )

    return GroupCurriculaResult(
        curricula=result, grade=grade, grade_unbekannt=grade is None
    )
