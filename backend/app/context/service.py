"""Context-Service – öffentliche Schnittstelle des Kontextspeichers.

get_context_for_query() ist die einzige Funktion, die vom Chat-Router aufgerufen wird.
"""

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.embedding import enqueue_embedding_job
from app.context.retrieval import EngagementEntry, get_engagement_context, get_semantic_context
from app.context.schemas import CurriculumDraftConfirmed
from app.db.models import (
    AssistantContextAnchor,
    ChatContextNode,
    ContextEdge,
    ContextNode,
    Group,
)

logger = logging.getLogger(__name__)


_RELATION_LABELS: dict[str, str] = {
    "introduced": "eingeführt",
    "knows": "bekannt",
    "mastered": "beherrscht",
    "struggles_with": "Schwierigkeiten",
}


def _assemble_context(
    semantic_nodes: list[ContextNode],
    engagement_entries: list[EngagementEntry],
    pinned_nodes: list[ContextNode],
) -> str:
    sections: list[str] = []

    if semantic_nodes:
        lines = ["## Relevante Lerninhalte\n"]
        for node in semantic_nodes:
            breadcrumb = ""
            if node.metadata_ and "breadcrumb" in node.metadata_:
                breadcrumb = " | ".join(node.metadata_["breadcrumb"]) + "\n"
            content = node.content or ""
            lines.append(f"### {node.title}\n{breadcrumb}{content}\n")
        sections.append("\n".join(lines))

    if engagement_entries:
        lines = ["## Vorwissen dieses Lernenden\n"]
        for entry in engagement_entries:
            label = " / ".join(
                _RELATION_LABELS.get(r, r) for r in entry.relations
            )
            lines.append(f"- **{entry.node.title}** ({label})")
        sections.append("\n".join(lines))

    if pinned_nodes:
        lines = ["## Explizit hinzugefügter Kontext\n"]
        for node in pinned_nodes:
            content = node.content or ""
            lines.append(f"### {node.title}\n{content}\n")
        sections.append("\n".join(lines))

    if not sections:
        return ""

    return "\n\n---\n\n".join(sections)


async def get_context_for_query(
    assistant_id: int | None,
    pseudonym: str,
    query_text: str,
    chat_id: UUID | None,
    db: AsyncSession,
) -> str:
    """Assembliert den Kontext-String für einen Chat-Prompt.

    Kombiniert semantische Suche, Engagement-Retrieval und explizit gepinnte Knoten.
    Pinned nodes werden unabhängig von einem Assistenten oder retrieval_scope geladen.
    """
    # Retrieval-Scope-Anker nur laden wenn ein Assistent aktiv ist
    anchor_ids: list[UUID] = []
    if assistant_id is not None:
        result = await db.execute(
            sa.select(AssistantContextAnchor.node_id)
            .where(
                AssistantContextAnchor.assistant_id == assistant_id,
                AssistantContextAnchor.role == "retrieval_scope",
            )
        )
        anchor_ids = [row[0] for row in result.all()]

    # Gepinnte Knoten immer laden (unabhängig von retrieval_scope)
    pinned_nodes: list[ContextNode] = []
    if chat_id is not None:
        pinned_result = await db.execute(
            sa.select(ContextNode)
            .join(ChatContextNode, ChatContextNode.node_id == ContextNode.id)
            .where(
                ChatContextNode.chat_id == chat_id,
                ContextNode.status == "active",
            )
        )
        pinned_nodes = list(pinned_result.scalars().all())

    # Semantische Suche nur wenn retrieval_scope-Anker vorhanden
    semantic_nodes: list[ContextNode] = []
    engagement_entries: list[EngagementEntry] = []
    if anchor_ids:
        semantic_nodes, engagement_entries = await asyncio.gather(
            get_semantic_context(anchor_ids, query_text, pseudonym, db),
            get_engagement_context(anchor_ids, pseudonym, db),
        )

    return _assemble_context(semantic_nodes, engagement_entries, pinned_nodes)


# -- KS-Phase-6 Curriculum Import Logic -----------------------------------------


@dataclass
class ImportStats:
    """Statistiken für den Curriculum-Import."""
    curriculum_count: int = 0
    kapitel_count: int = 0
    lernsequenz_count: int = 0
    edge_count: int = 0
    archived_count: int = 0
    warnings: list[str] = field(default_factory=list)


async def get_subject_id_by_code(db: AsyncSession, fach_code: str) -> int | None:
    """Lädt subject_id aus DB für den gegebenen fach_code.

    Match über die Spalte subjects.fach_code (Bildungsplan-Kürzel, z. B. 'M', 'CH'),
    normalisiert auf Großschreibung — nicht über den Slug.
    """
    from app.db.models import Subject
    if not fach_code:
        return None
    result = await db.execute(
        sa.select(Subject.id).where(
            Subject.fach_code == fach_code.strip().upper(),
        )
    )
    row = result.fetchone()
    return row[0] if row else None


async def get_fachplan_node(db: AsyncSession, fachplan_id: str) -> ContextNode | None:
    """Lädt den fachplan-Knoten für die gegebene fachplan_id."""
    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "fachplan",
            ContextNode.metadata_["fachplan_id"].astext == fachplan_id,
            ContextNode.status == "active",
        )
    )
    return result.scalars().first()


async def get_subject_department_group_id(db: AsyncSession, subject_id: int) -> int | None:
    """Lädt die Fachschafts-Gruppen-ID für ein Fach."""
    result = await db.execute(
        sa.select(Group.id).where(
            Group.subject_id == subject_id,
            Group.type == "subject_department",
        ).limit(1)
    )
    row = result.fetchone()
    return row[0] if row else None


def _normalize_ref(ref: str) -> str:
    """Normalisiert eine Referenz für toleranten Vergleich.
    
    Entfernt Leerzeichen, vereinheitlicht Klammern und Punkte.
    Wird für resolve_ik_node und resolve_pk_node verwendet.
    """
    if not ref:
        return ""
    # Leerzeichen entfernen
    ref = ref.replace(" ", "")
    # Klammern vereinheitlichen
    ref = ref.replace("[", "(").replace("]", ")")
    # Doppelte Punkte entfernen
    ref = ref.replace(".(", "(").replace(")", ".")
    return ref


async def resolve_ik_node(db: AsyncSession, subject_id: int, nr: str) -> UUID | None:
    """Löst IK-Nummer zu node_id auf (mit toleranter Normalisierung)."""
    # Normalisierte Suche
    normalized_nr = _normalize_ref(nr)
    
    # Erst: exakter Vergleich
    result = await db.execute(
        sa.select(ContextNode.id).where(
            ContextNode.content_type == "ik_kompetenz",
            ContextNode.subject_id == subject_id,
            ContextNode.metadata_["nr"].astext == nr,
            ContextNode.status == "active",
        )
    )
    row = result.fetchone()
    if row:
        return row[0]
    
    # Fallback: normalisierter Vergleich
    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "ik_kompetenz",
            ContextNode.subject_id == subject_id,
            ContextNode.status == "active",
        )
    )
    for (node,) in result.fetchall():
        node_nr = (node.metadata_ or {}).get("nr", "")
        if _normalize_ref(node_nr) == normalized_nr:
            return node.id

    return None


async def resolve_pk_node(db: AsyncSession, pk_id: str) -> UUID | None:
    """Löst PK-ID zu node_id auf (mit toleranter Normalisierung)."""
    # Normalisierte Suche
    normalized_pk = _normalize_ref(pk_id)
    
    # Erst: exakter Vergleich
    result = await db.execute(
        sa.select(ContextNode.id).where(
            ContextNode.content_type == "pk_kompetenz",
            ContextNode.metadata_["pk_id"].astext == pk_id,
            ContextNode.status == "active",
        )
    )
    row = result.fetchone()
    if row:
        return row[0]
    
    # Fallback: normalisierter Vergleich
    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "pk_kompetenz",
            ContextNode.status == "active",
        )
    )
    for (node,) in result.fetchall():
        node_pk = (node.metadata_ or {}).get("pk_id", "")
        if _normalize_ref(node_pk) == normalized_pk:
            return node.id

    return None


async def resolve_leitperspektive_node(db: AsyncSession, lp_code: str) -> UUID | None:
    """Löst Leitperspektive-Code zu node_id auf."""
    result = await db.execute(
        sa.select(ContextNode.id).where(
            ContextNode.content_type == "leitperspektive",
            ContextNode.metadata_["code"].astext == lp_code,
            ContextNode.status == "active",
        )
    )
    row = result.fetchone()
    return row[0] if row else None


async def get_or_create_node(
    db: AsyncSession,
    category: str,
    content_type: str,
    import_key: str,
    data: dict[str, Any],
) -> tuple[UUID, bool]:
    """Holt existierenden Knoten via import_key oder erstellt neuen.
    
    Rückgabe: (node_id, was_created)
    """
    # Existing node via import_key suchen
    result = await db.execute(
        sa.select(ContextNode.id).where(
            ContextNode.metadata_["import_key"].astext == import_key
        )
    )
    row = result.fetchone()
    
    if row:
        node_id = row[0]
        # Update existing node
        update_data = {}
        if "category" in data:
            update_data["category"] = data["category"]
        if "content_type" in data:
            update_data["content_type"] = data["content_type"]
        if "title" in data:
            update_data["title"] = data["title"]
        if "content" in data:
            update_data["content"] = data["content"]
            update_data["embedding"] = None  # Reset embedding wenn content sich ändert
        if "read_scope" in data:
            update_data["read_scope"] = data["read_scope"]
        if "write_scope" in data:
            update_data["write_scope"] = data["write_scope"]
        if "write_scope_group_id" in data:
            update_data["write_scope_group_id"] = data["write_scope_group_id"]
        if "subject_id" in data:
            update_data["subject_id"] = data["subject_id"]
        if "metadata_" in data:
            update_data["metadata_"] = data["metadata_"]
        
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        await db.execute(
            sa.update(ContextNode).where(ContextNode.id == node_id).values(**update_data)
        )
        return node_id, False
    
    # Create new node
    node_id = UUID(str(uuid.uuid4()))
    node_data = {
        "id": node_id,
        "category": data.get("category", category),
        "content_type": data.get("content_type", content_type),
        "title": data.get("title", ""),
        "content": data.get("content"),
        "read_scope": data.get("read_scope", "school"),
        "write_scope": data.get("write_scope", "private"),
        "write_scope_group_id": data.get("write_scope_group_id"),
        "subject_id": data.get("subject_id"),
        "metadata_": data.get("metadata_", {}),
        "status": "active",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    # Setze import_key in metadata
    if "metadata_" not in node_data or not node_data["metadata_"]:
        node_data["metadata_"] = {}
    node_data["metadata_"]["import_key"] = import_key
    
    db.add(ContextNode(**node_data))
    await db.flush()  # FK-Constraint bei nachfolgenden Edge-Inserts sichern
    return node_id, True


async def create_edge(
    db: AsyncSession,
    from_node_id: UUID,
    to_node_id: UUID,
    relation: str,
    metadata: dict | None = None,
) -> None:
    """Erstellt eine Kante zwischen zwei Knoten (idempotent)."""
    existing = await db.execute(
        sa.select(ContextEdge.id).where(
            ContextEdge.from_node_id == from_node_id,
            ContextEdge.to_node_id == to_node_id,
            ContextEdge.relation == relation,
        )
    )
    if existing.fetchone():
        return
    edge = ContextEdge(
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        relation=relation,
        metadata_=metadata or {},
    )
    db.add(edge)
    await db.flush()


async def archive_orphaned_curriculum_nodes(
    db: AsyncSession,
    import_keys: set[str],
) -> int:
    """Archiviert Knoten mit content_type in ('curriculum', 'kapitel', 'lernsequenz') 
    deren import_key NICHT in der gegebenen Menge ist."""
    result = await db.execute(
        sa.select(ContextNode.id, ContextNode.metadata_["import_key"].label("import_key")).where(
            ContextNode.content_type.in_(["curriculum", "kapitel", "lernsequenz"]),
            ContextNode.status == "active",
            ContextNode.metadata_["import_key"].isnot(None),
            sa.not_(ContextNode.metadata_["import_key"].astext.in_(import_keys)),
        )
    )
    rows = result.all()
    archived = 0
    
    for row in rows:
        logger.info(f"Archiviere Knoten mit import_key: {row.import_key}")
        await db.execute(
            sa.update(ContextNode)
            .where(ContextNode.id == row.id)
            .values(status="archived", archived_at=datetime.now(timezone.utc))
        )
        archived += 1
    
    return archived


async def import_curriculum_from_draft(
    db: AsyncSession,
    payload: CurriculumDraftConfirmed,
    user_pseudonym: str,
) -> tuple[UUID, ImportStats]:
    """Importiert ein Curriculum aus dem bestätigten Zwischenformat.
    
    Dies ist die Kernlogik für Stufe 2 (Persistenz).
    Wird sowohl vom API-Endpunkt als auch vom CLI-Skript aufgerufen.
    
    Rückgabe: (curriculum_id, stats)
    """
    stats = ImportStats()
    
    # Validieren
    if not payload.kapitel:
        raise ValueError("Keine Kapitel in den Import-Daten gefunden")
    
    # Subject laden
    subject_id = await get_subject_id_by_code(db, payload.fach_code)
    if subject_id is None:
        raise ValueError(f"Fach mit fach_code '{payload.fach_code}' nicht gefunden")
    
    # Fachplan laden
    fachplan = await get_fachplan_node(db, payload.fachplan_id)
    if not fachplan:
        raise ValueError(
            f"Fachplan mit fachplan_id '{payload.fachplan_id}' nicht gefunden. "
            f"Bildungsplan-Import fehlt?"
        )
    fachplan_id = fachplan.id
    
    # Fachschafts-Gruppen-ID
    department_group_id = await get_subject_department_group_id(db, subject_id)
    
    # Import-Key Basis
    import_key_base = f"{payload.fachplan_id}_{payload.jahrgangsstufe}"
    curriculum_import_key = import_key_base
    
    # Alle import_keys sammeln für späteres Archivieren
    all_import_keys: set[str] = set()
    
    # 1. Curriculum-Knoten
    curriculum_data = {
        "category": "knowledge",
        "content_type": "curriculum",
        "title": f"{payload.fach or payload.fach_code} {payload.schulart} Kl. {payload.jahrgangsstufe}",
        "content": payload.vorwort or "",
        "read_scope": "school",
        "write_scope": "subject" if department_group_id else "school",
        "write_scope_group_id": department_group_id,
        "subject_id": subject_id,
        "owner_pseudonym": user_pseudonym,
        "metadata_": {
            "fachplan_id": payload.fachplan_id,
            "bp_version": payload.bp_version,
            "schule": payload.schule,
            "fach_code": payload.fach_code,
            "fach": payload.fach or payload.fach_code,
            "schulart": payload.schulart,
            "jahrgangsstufe": payload.jahrgangsstufe,
            "import_key": curriculum_import_key,
        }
    }
    curriculum_id, created = await get_or_create_node(
        db, "knowledge", "curriculum", curriculum_import_key, curriculum_data
    )
    all_import_keys.add(curriculum_import_key)
    if created:
        stats.curriculum_count += 1
    
    # Kante: curriculum -> fachplan
    await create_edge(db, curriculum_id, UUID(str(fachplan_id)), "part_of")
    stats.edge_count += 1
    
    # Fach-Name für Breadcrumb
    fach_name = payload.fach or payload.fach_code
    schulart = payload.schulart
    jahrgangsstufe = payload.jahrgangsstufe
    
    # 2. Kapitel und Lernsequenzen
    for kap in payload.kapitel:
        kapitel_import_key = f"{import_key_base}_kapitel_{kap.reihenfolge}"
        
        # Kapitel-Knoten
        konkretisierung_text = " ".join(kap.konkretisierung) if kap.konkretisierung else None
        kapitel_data = {
            "category": "knowledge",
            "content_type": "kapitel",
            "title": kap.titel,
            "content": konkretisierung_text,
            "read_scope": "school",
            "write_scope": "subject" if department_group_id else "school",
            "write_scope_group_id": department_group_id,
            "subject_id": subject_id,
            "owner_pseudonym": user_pseudonym,
            "metadata_": {
                "std": kap.std,
                "reihenfolge": kap.reihenfolge,
                "einleitung": kap.hinweis or "",
                "breadcrumb": f"{schulart} | {fach_name} | Kl. {jahrgangsstufe}: {kap.titel}",
                "import_key": kapitel_import_key,
            }
        }
        kapitel_id, created = await get_or_create_node(
            db, "knowledge", "kapitel", kapitel_import_key, kapitel_data
        )
        all_import_keys.add(kapitel_import_key)
        if created:
            stats.kapitel_count += 1
        
        # Kante: kapitel -> curriculum
        await create_edge(db, kapitel_id, curriculum_id, "part_of")
        stats.edge_count += 1
        
        # Embedding-Job für Kapitel
        if created:
            await enqueue_embedding_job(kapitel_id, db)
        
        # 3. Lernsequenzen
        for ls in kap.lernsequenzen:
            ls_reihenfolge = ls.reihenfolge if ls.reihenfolge is not None else 0
            ls_import_key = f"{kapitel_import_key}_ls_{ls_reihenfolge}"
            
            # Lernsequenz-Knoten
            ls_data = {
                "category": "knowledge",
                "content_type": "lernsequenz",
                "title": ls.bp_titel or "",
                "content": None,
                "read_scope": "school",
                "write_scope": "subject" if department_group_id else "school",
                "write_scope_group_id": department_group_id,
                "subject_id": subject_id,
                "owner_pseudonym": user_pseudonym,
                "metadata_": {
                    "bp_leitidee": ls.bp_leitidee,
                    "reihenfolge": ls_reihenfolge,
                    "eintraege": [
                        {
                            "ik": e.ik,
                            "ik_partiell": e.ik_partiell,
                            "pk": e.pk,
                            "konkretisierung": e.konkretisierung,
                            "hinweise": e.hinweise,
                            "lp": e.lp,
                        }
                        for e in ls.eintraege
                    ],
                    "import_key": ls_import_key,
                }
            }
            lernsequenz_id, created = await get_or_create_node(
                db, "knowledge", "lernsequenz", ls_import_key, ls_data
            )
            all_import_keys.add(ls_import_key)
            if created:
                stats.lernsequenz_count += 1
            
            # Kante: lernsequenz -> kapitel
            await create_edge(db, lernsequenz_id, kapitel_id, "part_of")
            stats.edge_count += 1
            
            # 4. IK- und PK-Referenzen auflösen
            for entry in ls.eintraege:
                # IK-Referenzen
                if entry.ik:
                    ik_ids = entry.ik.split(",") if isinstance(entry.ik, str) else [str(entry.ik)]
                    for ik_nr_single in ik_ids:
                        ik_nr_single = ik_nr_single.strip()
                        ik_node_id = await resolve_ik_node(db, subject_id, ik_nr_single)
                        if ik_node_id:
                            # Prüfe ob partiell
                            partiell = entry.ik_partiell
                            metadata = {"partiell": str(partiell).lower()}
                            await create_edge(db, lernsequenz_id, ik_node_id, "references", metadata)
                            stats.edge_count += 1
                        else:
                            warning = f"IK {ik_nr_single} nicht gefunden für LS {ls.bp_titel or '?'}"
                            if warning not in stats.warnings:
                                stats.warnings.append(warning)
                            logger.warning(warning)
                
                # PK-Referenzen
                if entry.pk:
                    pk_list = entry.pk if isinstance(entry.pk, list) else [entry.pk]
                    for pk_ref in pk_list:
                        if isinstance(pk_ref, dict):
                            pk_id = pk_ref.get("id")
                        else:
                            pk_id = str(pk_ref)
                        if pk_id:
                            pk_node_id = await resolve_pk_node(db, pk_id)
                            if pk_node_id:
                                await create_edge(db, lernsequenz_id, pk_node_id, "develops")
                                stats.edge_count += 1
                            else:
                                warning = f"PK {pk_id} nicht gefunden für LS {ls.bp_titel or '?'}"
                                if warning not in stats.warnings:
                                    stats.warnings.append(warning)
                                logger.warning(warning)
                
                # Leitperspektiven-Referenzen
                if entry.lp:
                    lp_list = entry.lp if isinstance(entry.lp, list) else [entry.lp]
                    for lp_code in lp_list:
                        lp_node_id = await resolve_leitperspektive_node(db, str(lp_code))
                        if lp_node_id:
                            await create_edge(db, lernsequenz_id, lp_node_id, "references")
                            stats.edge_count += 1
                        else:
                            warning = f"LP {lp_code} nicht gefunden für LS {ls.bp_titel or '?'}"
                            if warning not in stats.warnings:
                                stats.warnings.append(warning)
                            logger.warning(warning)
    
    return curriculum_id, stats
