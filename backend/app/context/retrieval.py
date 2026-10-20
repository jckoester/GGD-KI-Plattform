"""Retrieval-Funktionen fuer den Kontextspeicher (KS-Phase-3)."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.visibility import read_scope_clause
from app.db.models import ContextNode

# Nur strukturell sinnvolle Einstiegspunkte als retrieval_scope zulässig. Weiterhin von
# hier importierbar (`router.py`), die Liste selbst kommt aber aus der Taxonomie.
#
# Bis 02.09.2026 stand sie hier als Literal — und wich von `scope_anchor: true` in
# `taxonomy.yaml` ab: dort `kapitel`, hier stattdessen `unterrichtseinheit`, und
# der Assistenten-Editor hielt eine dritte Kopie. Sichtbar war davon nur ein falsches
# Badge in der Knotenliste. Jetzt gibt es eine Quelle, und die Startprüfung
# (`taxonomy_check.py`) hält sie fest.
from app.context.taxonomy import VALID_SCOPE_ANCHOR_TYPES  # noqa: F401 — Re-Export


@dataclass
class EngagementEntry:
    node: ContextNode
    relations: list[str]   # z.B. ['knows', 'introduced']
    strength: float | None
    origins: list[str]     # z.B. ['user', 'group']


_SCOPE_CTE = """
WITH RECURSIVE descendants AS (
    SELECT id FROM context_nodes
    WHERE id = ANY(:anchor_ids) AND status = 'active'
    UNION ALL
    SELECT e.from_node_id
    FROM context_edges e
    JOIN descendants d ON e.to_node_id = d.id
    WHERE e.relation = 'part_of'
),
referenced AS (
    SELECT e.to_node_id AS id
    FROM context_edges e
    WHERE e.from_node_id = ANY(:anchor_ids)
      AND e.relation IN ('references', 'develops')
),
scope AS (
    SELECT id FROM descendants
    UNION
    SELECT id FROM referenced
)
"""


# Die Editionslogik (Jahrgangs-Frontier, Fassungs-Zusammenfassung) und die semantische
# Suche im Anker-Teilgraphen liegen seit 09/2026 in :mod:`app.context.search` — dort
# gelten sie für **alle** Aufruferprofile, nicht nur für Anker-Assistenten (ADR-017,
# AP5). Hier bleibt allein der Lernstand: Er ist Traversierung, keine Suche.


async def get_engagement_context(
    anchor_ids: list[UUID],
    pseudonym: str,
    db: AsyncSession,
    *,
    rollen: Sequence[str] = (),
    group_id: int | None = None,
) -> list[EngagementEntry]:
    """Kombinierter Lernstand (eigene + Gruppen-Engagements), scoped auf Anker-Subgraphen.

    Folgt dem UNION-Pattern aus ADR-013 Paragraph Lernzustands-Tabelle.
    Gibt leere Liste zurueck wenn keine Anker oder keine Engagements.

    **Gruppen-Engagements nur der Gruppe der Konversation** (``group_id``; 0.20, Päckchen AC,
    F6). Bis dahin kamen die *aller* Gruppen der Person — im Chemie-Chat stand dann auch, was
    ihre Deutschgruppe eingeführt hatte. Ohne Gruppenbezug gibt es keine.

    **Nur lesbare Knoten** (``read_scope_clause`` für diese Person). Bis 0.20 prüfte der
    Lernstand keine Leserechte — ein privater Knoten der Lehrkraft, als Material einer Phase
    nachbereitet, ging als „eingeführt" in den Prompt der Schüler:in (Nebenbefund 09.10.2026).
    """
    if not anchor_ids:
        return []

    anchor_id_strs = [str(aid) for aid in anchor_ids]

    sql = sa.text(
        _SCOPE_CTE
        + """
        , student_engagement AS (
            -- Ebene 1: direkte Nutzer-Engagements
            SELECT
                ne.node_id,
                ne.relation,
                ne.strength,
                'user' AS origin
            FROM node_engagement ne
            WHERE ne.pseudonym = :pseudonym

            UNION ALL

            -- Ebene 2: Gruppen-Engagements aller Gruppen des Schuelers
            SELECT
                ne.node_id,
                ne.relation,
                ne.strength,
                'group' AS origin
            FROM node_engagement ne
            JOIN group_memberships gm ON gm.group_id = ne.group_id
            WHERE gm.pseudonym = :pseudonym
              AND ne.group_id = CAST(:group_id AS integer)
        ),
        aggregated AS (
            SELECT
                se.node_id,
                MAX(se.strength)                  AS strength,
                array_agg(DISTINCT se.relation)   AS relations,
                array_agg(DISTINCT se.origin)     AS origins
            FROM student_engagement se
            JOIN scope s ON s.id = se.node_id
            GROUP BY se.node_id
        )
        SELECT
            n.id, n.category, n.content_type, n.title, n.content,
            n.metadata, n.embedding, n.owner_pseudonym,
            n.read_scope, n.write_scope,
            n.read_scope_group_id, n.write_scope_group_id,
            n.assistant_id, n.status, n.valid_until,
            n.archived_at, n.schuljahr, n.created_at, n.updated_at,
            a.strength, a.relations, a.origins
        FROM aggregated a
        JOIN context_nodes n ON n.id = a.node_id
        WHERE n.status = 'active'
        ORDER BY n.content_type, n.title
        """
    )

    result = await db.execute(
        sql,
        {
            "anchor_ids": anchor_id_strs,
            "pseudonym": pseudonym,
            "group_id": group_id,
        },
    )
    rows = result.mappings().all()
    if rows:
        lesbar = set((await db.execute(
            sa.select(ContextNode.id).where(
                ContextNode.id.in_([r["id"] for r in rows]),
                read_scope_clause(pseudonym, rollen),
            )
        )).scalars())
        rows = [r for r in rows if r["id"] in lesbar]

    entries: list[EngagementEntry] = []
    for row in rows:
        node_data = {k: v for k, v in row.items()
                     if k not in ("strength", "relations", "origins")}
        if "metadata" in node_data:
            node_data["metadata_"] = node_data.pop("metadata")
        node = ContextNode(**node_data)
        entries.append(EngagementEntry(
            node=node,
            relations=list(row["relations"] or []),
            strength=row["strength"],
            origins=list(row["origins"] or []),
        ))
    return entries
