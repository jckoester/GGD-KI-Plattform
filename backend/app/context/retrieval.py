"""Retrieval-Funktionen fuer den Kontextspeicher (KS-Phase-3)."""

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.editions import aktive_bp_version
from app.context.embedding import generate_embedding
from app.context.search import fasse_fassungen_zusammen, fassungs_schluessel
from app.db.models import ContextNode


@dataclass
class EngagementEntry:
    node: ContextNode
    relations: list[str]   # z.B. ['knows', 'introduced']
    strength: float | None
    origins: list[str]     # z.B. ['user', 'group']

# Nur strukturell sinnvolle Einstiegspunkte als retrieval_scope zulässig
VALID_SCOPE_ANCHOR_TYPES: frozenset[str] = frozenset({
    "fachplan", "leitidee", "pk_gruppe", "curriculum", "themengebiet",
    "unterrichtseinheit", "unterrichtsstunde",
})


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


# ── Editionsbewusstsein (zwei aktive BP-Fassungen gleichzeitig) ──────────────
#
# Solange eine neue Bildungsplan-Edition jahrgangsweise nach oben wächst, liegen
# dieselben Kompetenzen doppelt im Speicher — in der alten und der neuen Fassung,
# textlich oft nur in Nuancen verschieden. Ohne Gegenmaßnahme belegen beide je
# einen der top_k-Plätze und verdrängen anderes.
#
# Zwei Stufen, absichtlich in dieser Reihenfolge:
#   1. Filtern, wo ein Jahrgang bekannt ist — dann entscheidet der Fahrplan,
#      welche Fassung gilt (fachweise, inkl. Inhalts-Fallback).
#   2. Zusammenfassen, was danach noch doppelt ist — greift auch im freien Chat
#      ohne Gruppenbezug, wählt aber nur nach Ähnlichkeit.

# Nummernträger je Knotentyp: IK/PK führen 'kompetenz_nr', Leitidee/PK-Gruppe 'nr'.
_NR_KEYS = ("kompetenz_nr", "nr")

# Überhang beim Holen: Filter und Zusammenfassung entfernen Treffer, deshalb wird
# ein Vielfaches von top_k geladen und erst danach gekürzt.
_KANDIDATEN_FAKTOR = 3


def _fassungs_schluessel(node: ContextNode) -> tuple | None:
    """Der Fassungsschlüssel eines ORM-Knotens.

    Die Regel selbst steht in :func:`app.context.search.fassungs_schluessel` — dort
    gilt sie auch für die Aufzählung. Hier bleibt nur das Herauslesen der Felder aus
    dem ORM-Objekt; AP5 führt beide Wege ohnehin zusammen.
    """
    if not node.bp_version:
        return None
    meta = node.metadata_ or {}
    nr = next((meta[k] for k in _NR_KEYS if meta.get(k)), None)
    return fassungs_schluessel(node.subject_id, node.content_type, nr)


async def _frontier_je_fach(
    db: AsyncSession, subject_ids: set[int], grade: int
) -> dict[int, str]:
    """{subject_id: geltende bp_version} für diese Stufe im laufenden Schuljahr.

    Fächer ohne bestimmbare Fassung fehlen im Ergebnis — für sie wird nicht
    gefiltert. Der Editionsbestand kommt je Fach aus der DB, damit der
    Inhalts-Fallback greift (neue Edition laut Fahrplan in Kraft, aber für dieses
    Fach noch nicht importiert → vorige Edition gilt weiter).
    """
    if not subject_ids:
        return {}

    rows = await db.execute(
        sa.select(ContextNode.subject_id, ContextNode.bp_version)
        .where(
            ContextNode.subject_id.in_(subject_ids),
            ContextNode.status == "active",
            ContextNode.bp_version != "",
        )
        .distinct()
    )
    bestand: dict[int, set[str]] = {}
    for subject_id, bp_version in rows.all():
        bestand.setdefault(subject_id, set()).add(bp_version)

    frontier: dict[int, str] = {}
    for subject_id, verfuegbar in bestand.items():
        gilt = aktive_bp_version(grade, verfuegbar)
        if gilt:
            frontier[subject_id] = gilt
    return frontier


def _filtere_auf_frontier(
    nodes: list[ContextNode], frontier: dict[int, str]
) -> list[ContextNode]:
    """Nur die geltende Fassung behalten — unversionierte Knoten bleiben immer.

    Fächer ohne Eintrag in ``frontier`` werden nicht gefiltert; sonst bliebe von
    einem Fach, dessen Fassung sich nicht bestimmen lässt, gar nichts übrig.
    """
    return [
        n
        for n in nodes
        if not n.bp_version or frontier.get(n.subject_id) in (None, n.bp_version)
    ]


def _fasse_fassungen_zusammen(nodes: list[ContextNode]) -> list[ContextNode]:
    """Je Kompetenz nur den bestbewerteten Treffer behalten (Reihenfolge bleibt)."""
    return fasse_fassungen_zusammen(nodes, _fassungs_schluessel)


async def get_semantic_context(
    anchor_ids: list[UUID],
    query_text: str,
    pseudonym: str,
    db: AsyncSession,
    top_k: int = 10,
    grade: int | None = None,
) -> list[ContextNode]:
    """Semantische Suche im durch anchor_ids definierten Scope-Subgraphen.

    Gibt leere Liste zurueck wenn keine Anker oder kein Embedding vorhanden.

    ``grade`` = Jahrgangsstufe des Fragenden, falls ableitbar (Konversation mit
    Gruppenbezug). Ist sie bekannt, bleibt je Fach nur die für diese Stufe
    geltende BP-Fassung übrig; sonst werden Fassungs-Dubletten derselben
    Kompetenz auf den ähnlichsten Treffer reduziert.
    """
    if not anchor_ids:
        return []

    query_embedding: list[float] = await generate_embedding(query_text)

    # anchor_ids als Liste von Strings fuer asyncpg ARRAY-Binding
    anchor_id_strs = [str(aid) for aid in anchor_ids]

    # Embedding als pgvector-kompatibler String
    embedding_str = "[" + ",".join(f"{v:.10f}" for v in query_embedding) + "]"

    sql = sa.text(
        _SCOPE_CTE
        + """
        SELECT n.id, n.category, n.content_type, n.title, n.content,
               n.metadata AS metadata, n.embedding, n.owner_pseudonym,
               n.read_scope, n.write_scope,
               n.read_scope_group_id, n.write_scope_group_id,
               n.assistant_id, n.status, n.valid_until,
               n.archived_at, n.schuljahr,
               n.subject_id, n.min_grade, n.max_grade, n.niveau, n.bp_version,
               n.created_at, n.updated_at
        FROM context_nodes n
        WHERE n.id IN (SELECT id FROM scope)
          AND n.status = 'active'
          AND n.embedding IS NOT NULL
          AND (
              n.read_scope IN ('global', 'school')
              OR (n.read_scope = 'private' AND n.owner_pseudonym = :pseudonym)
          )
        ORDER BY n.embedding <=> CAST(:embedding AS vector)
        LIMIT :fetch_k
        """
    )

    result = await db.execute(
        sql,
        {
            "anchor_ids": anchor_id_strs,
            "pseudonym": pseudonym,
            "embedding": embedding_str,
            "fetch_k": top_k * _KANDIDATEN_FAKTOR,
        },
    )
    rows = result.mappings().all()
    nodes = []
    for row in rows:
        row_dict = dict(row)
        # metadata Spalte heisst in der DB 'metadata', im ORM aber 'metadata_'
        if 'metadata' in row_dict:
            row_dict['metadata_'] = row_dict.pop('metadata')
        nodes.append(ContextNode(**row_dict))

    if grade is not None:
        faecher = {n.subject_id for n in nodes if n.bp_version and n.subject_id}
        nodes = _filtere_auf_frontier(nodes, await _frontier_je_fach(db, faecher, grade))

    return _fasse_fassungen_zusammen(nodes)[:top_k]


async def get_engagement_context(
    anchor_ids: list[UUID],
    pseudonym: str,
    db: AsyncSession,
) -> list[EngagementEntry]:
    """Kombinierter Lernstand (eigene + Gruppen-Engagements), scoped auf Anker-Subgraphen.

    Folgt dem UNION-Pattern aus ADR-013 Paragraph Lernzustands-Tabelle.
    Gibt leere Liste zurueck wenn keine Anker oder keine Engagements.
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
        },
    )
    rows = result.mappings().all()

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
