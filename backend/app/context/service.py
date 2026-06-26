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
from app.context.grades import parse_grade_band
from app.context.retrieval import EngagementEntry, get_engagement_context, get_semantic_context
from app.context.schemas import CurriculumDraftConfirmed
from app.db.models import (
    AssistantContextAnchor,
    ChatContextNode,
    ContextEdge,
    ContextNode,
    Conversation,
    Group,
    Subject,
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

    base = _assemble_context(semantic_nodes, engagement_entries, pinned_nodes)

    # UP-7: Planungs-Block „Aktueller Unterricht" für Conversations mit Gruppenbezug.
    planning_block = await _planning_block(db, chat_id)
    if planning_block:
        return f"{planning_block}\n\n{base}" if base else planning_block
    return base


async def _group_label(db: AsyncSession, group_id: int) -> str:
    group = await db.get(Group, group_id)
    if group is None:
        return "Unterricht"
    subj = await db.get(Subject, group.subject_id) if group.subject_id else None
    if subj and subj.name.lower() not in (group.name or "").lower():
        return f"{subj.name}, {group.name}"
    return group.name


async def _planning_block(db: AsyncSession, chat_id: UUID | None) -> str | None:
    """Markdown-Block aus den Planungsdaten der Conversation-Gruppe (UP-7)."""
    if chat_id is None:
        return None
    conv = await db.get(Conversation, chat_id)
    if conv is None or not isinstance(conv.group_id, int):
        return None

    # Lokaler Import vermeidet eine Modul-Zyklus-Abhängigkeit context ↔ planning.
    from datetime import date as _date

    from app.planning.student_context import (
        get_current_topic,
        get_exam_scope,
        render_topic_block,
    )

    today = _date.today()
    topic = await get_current_topic(db, conv.group_id, today)
    exam = await get_exam_scope(db, conv.group_id, today=today)
    if topic is None and exam is None:
        return None
    return render_topic_block(topic, await _group_label(db, conv.group_id), exam)


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

    Match über subjects.fach_code ODER subjects.fach_codes (Bildungsplan-Kürzel,
    z. B. 'M', 'CH', oder bei Multi-Code-Fächern 'NWT'/'NWTBFO'), normalisiert auf
    Großschreibung — nicht über den Slug.
    """
    from app.db.models import Subject
    if not fach_code:
        return None
    code = fach_code.strip().upper()
    result = await db.execute(
        sa.select(Subject.id).where(
            sa.or_(
                Subject.fach_code == code,
                Subject.fach_codes.any(code),
            )
        ).limit(1)
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


async def resolve_leitperspektive_aspekt_node(db: AsyncSession, bp_id: str) -> UUID | None:
    """Löst Leitperspektive-Aspekt-bp_id (z. B. 'BNE_01') zu node_id auf."""
    result = await db.execute(
        sa.select(ContextNode.id).where(
            ContextNode.content_type == "leitperspektive_aspekt",
            ContextNode.metadata_["bp_id"].astext == bp_id,
            ContextNode.status == "active",
        )
    )
    row = result.fetchone()
    return row[0] if row else None


async def resolve_ik_node_by_fach_code(
    db: AsyncSession, fach_code: str, nr: str
) -> UUID | None:
    """Löst Cross-Fach-IK via (fach_code, nr) auf."""
    # subject_id aus fach_code ODER fach_codes (Multi-Code-Fächer); Großschreibung
    if not fach_code:
        return None
    result = await db.execute(
        sa.text(
            "SELECT id FROM subjects "
            "WHERE fach_code = :code OR :code = ANY(fach_codes) LIMIT 1"
        ),
        {"code": fach_code.strip().upper()},
    )
    row = result.fetchone()
    if not row:
        return None
    return await resolve_ik_node(db, row[0], nr)


# ── Code-Token → UUID-Token Übersetzer (für Re-Import) ───────────────────────

_LP_CODE_TOKEN  = re.compile(r'@\[([^\]]*)\]\(lp:([^)]+)\)')
_LPA_CODE_TOKEN = re.compile(r'@\[([^\]]*)\]\(lpa:([^)]+)\)')
_IK_CODE_TOKEN  = re.compile(r'#\[([^\]]*)\]\(ik:([^/:)]+):([^)]+)\)')
_NODE_UUID_TOKEN = re.compile(r'@\[([^\]]*)\]\(node:[0-9a-f-]{36}\)')


async def hinweise_code_to_uuid(
    text: str,
    db: AsyncSession,
    warnings: list[str],
    context_label: str = "",
) -> str:
    """Übersetzt Code-Token im Hinweise-Feld zurück in UUID-Token.

    Verarbeitet: lp:<code>, lpa:<bp_id>, ik:<fach>:<nr>.
    node:<uuid> (Material) bleibt unverändert.
    Unbekannte Tokens werden als Freitext belassen + Warnung.
    """
    if not text:
        return text

    all_matches: list[tuple[re.Match, str]] = []
    for pattern, kind in [
        (_LP_CODE_TOKEN, "lp"),
        (_LPA_CODE_TOKEN, "lpa"),
        (_IK_CODE_TOKEN, "ik"),
    ]:
        for m in pattern.finditer(text):
            all_matches.append((m, kind))
    if not all_matches:
        return text
    all_matches.sort(key=lambda x: x[0].start())

    parts = []
    last = 0
    for m, kind in all_matches:
        parts.append(text[last:m.start()])
        label = m.group(1)
        if kind == "lp":
            code = m.group(2)
            uid = await resolve_leitperspektive_node(db, code)
            if uid:
                parts.append(f"@[{label}](lp:{uid})")
            else:
                warnings.append(f"LP '{code}' nicht gefunden{' in ' + context_label if context_label else ''}")
                parts.append(m.group(0))
        elif kind == "lpa":
            bp_id = m.group(2)
            uid = await resolve_leitperspektive_aspekt_node(db, bp_id)
            if uid:
                parts.append(f"@[{label}](lpa:{uid})")
            else:
                warnings.append(f"LP-Aspekt '{bp_id}' nicht gefunden{' in ' + context_label if context_label else ''}")
                parts.append(m.group(0))
        elif kind == "ik":
            fach_code = m.group(2)
            nr = m.group(3)
            uid = await resolve_ik_node_by_fach_code(db, fach_code, nr)
            if uid:
                parts.append(f"#[{label}](ik:{uid})")
            else:
                warnings.append(f"Cross-IK '{fach_code}:{nr}' nicht gefunden{' in ' + context_label if context_label else ''}")
                parts.append(m.group(0))
        last = m.end()
    parts.append(text[last:])
    return "".join(parts)


async def material_resolve_nodes(
    text: str,
    db: AsyncSession,
    warnings: list[str],
    context_label: str = "",
) -> list[UUID]:
    """Extrahiert UUIDs aus Material-node-Token und prüft Existenz.

    Gibt Liste gültiger node_ids zurück; fehlende → Warnung.
    """
    node_token = re.compile(r'@\[[^\]]*\]\(node:([0-9a-f-]{36})\)')
    valid_ids = []
    for m in node_token.finditer(text or ""):
        uid_str = m.group(1)
        try:
            uid = UUID(uid_str)
        except ValueError:
            continue
        result = await db.execute(
            sa.select(ContextNode.id).where(
                ContextNode.id == uid, ContextNode.status == "active"
            )
        )
        if result.fetchone():
            valid_ids.append(uid)
        else:
            warnings.append(
                f"Material-Knoten '{uid_str}' nicht gefunden"
                f"{' in ' + context_label if context_label else ''} – Token bleibt erhalten"
            )
    return valid_ids


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
        if "min_grade" in data:
            update_data["min_grade"] = data["min_grade"]
        if "max_grade" in data:
            update_data["max_grade"] = data["max_grade"]
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
        "min_grade": data.get("min_grade"),
        "max_grade": data.get("max_grade"),
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


async def load_curriculum_tree(db: AsyncSession, curriculum_id: UUID) -> dict | None:
    """Lädt das vollständige Curriculum als verschachtelten Dict (ohne Berechtigungsprüfung).

    Gibt None zurück wenn das Curriculum nicht existiert oder inaktiv ist.
    Der zurückgegebene Dict enthält `read_scope` und `owner_pseudonym` für die
    Berechtigungsprüfung im Router.
    """
    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.id == curriculum_id,
            ContextNode.status == "active",
            ContextNode.content_type == "curriculum",
        )
    )
    curriculum = result.scalar_one_or_none()
    if not curriculum:
        return None

    # Kapitel laden
    result = await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(
            ContextEdge.to_node_id == curriculum_id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "kapitel",
            ContextNode.status == "active",
        )
        .order_by(ContextNode.metadata_["reihenfolge"].as_integer())
    )
    kapitel_nodes = result.scalars().all()

    kapitel_list = []
    for kap_node in kapitel_nodes:
        result = await db.execute(
            sa.select(ContextNode)
            .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
            .where(
                ContextEdge.to_node_id == kap_node.id,
                ContextEdge.relation == "part_of",
                ContextNode.content_type == "lernsequenz",
                ContextNode.status == "active",
            )
            .order_by(ContextNode.metadata_["reihenfolge"].as_integer())
        )
        lernsequenz_nodes = result.scalars().all()

        lernsequenzen_list = []
        for ls_node in lernsequenz_nodes:
            result = await db.execute(
                sa.text("""
                    SELECT n.id, n.title,
                           n.metadata->>'nr' AS nr,
                           e.metadata->>'partiell' AS partiell
                    FROM context_nodes n
                    JOIN context_edges e ON e.to_node_id = n.id
                    WHERE e.from_node_id = :ls_id
                      AND e.relation = 'references'
                      AND n.content_type = 'ik_kompetenz'
                      AND n.status = 'active'
                """),
                {"ls_id": str(ls_node.id)},
            )
            ik_refs = [
                {
                    "node_id": str(row.id),
                    "title": row.title,
                    "nr": row.nr,
                    "partiell": row.partiell == "true",
                }
                for row in result.mappings().all()
            ]

            result = await db.execute(
                sa.text("""
                    SELECT n.id, n.title, n.metadata->>'pk_id' AS pk_id
                    FROM context_nodes n
                    JOIN context_edges e ON e.to_node_id = n.id
                    WHERE e.from_node_id = :ls_id
                      AND e.relation = 'develops'
                      AND n.content_type = 'pk_kompetenz'
                      AND n.status = 'active'
                """),
                {"ls_id": str(ls_node.id)},
            )
            pk_refs = [
                {"node_id": str(row.id), "title": row.title, "pk_id": row.pk_id}
                for row in result.mappings().all()
            ]

            result = await db.execute(
                sa.text("""
                    SELECT n.id, n.title, n.metadata->>'code' AS lp_code
                    FROM context_nodes n
                    JOIN context_edges e ON e.to_node_id = n.id
                    WHERE e.from_node_id = :ls_id
                      AND e.relation = 'references'
                      AND n.content_type = 'leitperspektive'
                      AND n.status = 'active'
                """),
                {"ls_id": str(ls_node.id)},
            )
            leitperspektive_refs = [
                {"node_id": str(row.id), "title": row.title, "lp_code": row.lp_code}
                for row in result.mappings().all()
            ]

            lernsequenzen_list.append({
                "id": ls_node.id,
                "title": ls_node.title,
                "metadata": ls_node.metadata_ or {},
                "ik_refs": ik_refs,
                "pk_refs": pk_refs,
                "leitperspektive_refs": leitperspektive_refs,
            })

        kapitel_list.append({
            "id": kap_node.id,
            "title": kap_node.title,
            "metadata": kap_node.metadata_ or {},
            "content": kap_node.content,
            "lernsequenzen": lernsequenzen_list,
        })

    return {
        "id": curriculum.id,
        "title": curriculum.title,
        "metadata": curriculum.metadata_ or {},
        "content": curriculum.content,
        "subject_id": curriculum.subject_id,
        "write_scope_group_id": curriculum.write_scope_group_id,
        "read_scope": curriculum.read_scope,
        "owner_pseudonym": curriculum.owner_pseudonym,
        "kapitel": kapitel_list,
    }


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
    min_grade, max_grade = parse_grade_band(payload.jahrgangsstufe)
    curriculum_data = {
        "category": "knowledge",
        "content_type": "curriculum",
        "title": f"{payload.fach or payload.fach_code} {payload.schulart} Kl. {payload.jahrgangsstufe}",
        "content": payload.vorwort or "",
        "read_scope": "school",
        "write_scope": "subject" if department_group_id else "school",
        "write_scope_group_id": department_group_id,
        "subject_id": subject_id,
        "min_grade": min_grade,
        "max_grade": max_grade,
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
            ls_label = ls.bp_titel or "?"

            # Einträge vorverarbeiten: IK/PK auflösen, Hinweise rewriten, Material prüfen
            eintraege_for_meta = []
            resolved_edges: list[tuple[UUID, UUID, str, dict]] = []  # (from, to, relation, meta)

            for entry in ls.eintraege:
                # ── IK normalisieren ────────────────────────────────────────
                ik_pairs = _normalize_ik_input(entry.ik, entry.ik_partiell)
                editor_ik = []
                for ik_nr, partiell in ik_pairs:
                    ik_node_id = await resolve_ik_node(db, subject_id, ik_nr)
                    if ik_node_id:
                        editor_ik.append({"node_id": str(ik_node_id), "nr": ik_nr, "partiell": partiell})
                        resolved_edges.append((None, ik_node_id, "references", {"partiell": str(partiell).lower()}))
                    else:
                        w = f"IK {ik_nr} nicht gefunden für LS {ls_label}"
                        if w not in stats.warnings:
                            stats.warnings.append(w)
                        logger.warning(w)

                # ── PK normalisieren ─────────────────────────────────────────
                pk_raw = entry.pk if isinstance(entry.pk, list) else ([entry.pk] if entry.pk else [])
                editor_pk = []
                for pk_ref in pk_raw:
                    pk_id_str = pk_ref.get("id") if isinstance(pk_ref, dict) else str(pk_ref)
                    if pk_id_str:
                        pk_node_id = await resolve_pk_node(db, pk_id_str)
                        if pk_node_id:
                            editor_pk.append({"node_id": str(pk_node_id), "pk_id": pk_id_str})
                            resolved_edges.append((None, pk_node_id, "develops", {}))
                        else:
                            w = f"PK {pk_id_str} nicht gefunden für LS {ls_label}"
                            if w not in stats.warnings:
                                stats.warnings.append(w)
                            logger.warning(w)

                # ── Hinweise: Code-Token → UUID-Token rewrite + Kanten ───────
                hinweise_raw = entry.hinweise or ""
                hinweise_uuid = await hinweise_code_to_uuid(hinweise_raw, db, stats.warnings, ls_label)

                # LP-Kanten aus UUID-Token
                for uid_str in re.findall(r'@\[[^\]]*\]\(lp:([0-9a-f-]{36})\)', hinweise_uuid):
                    resolved_edges.append((None, UUID(uid_str), "references", {}))
                # LPA-Kanten
                for uid_str in re.findall(r'@\[[^\]]*\]\(lpa:([0-9a-f-]{36})\)', hinweise_uuid):
                    resolved_edges.append((None, UUID(uid_str), "references", {}))
                # Cross-IK-Kanten
                for uid_str in re.findall(r'#\[[^\]]*\]\(ik:([0-9a-f-]{36})\)', hinweise_uuid):
                    resolved_edges.append((None, UUID(uid_str), "references", {}))

                # Legacy lp-Liste (dedupliziert mit Token-Kanten)
                for lp_code in (entry.lp or []):
                    lp_node_id = await resolve_leitperspektive_node(db, str(lp_code))
                    if lp_node_id:
                        resolved_edges.append((None, lp_node_id, "references", {}))
                    else:
                        w = f"LP {lp_code} nicht gefunden für LS {ls_label}"
                        if w not in stats.warnings:
                            stats.warnings.append(w)
                        logger.warning(w)

                # ── Material: node-Token → used_with Kanten ──────────────────
                material_text = entry.material or ""
                material_uuids = await material_resolve_nodes(
                    material_text, db, stats.warnings, ls_label
                )
                for mat_uid in material_uuids:
                    resolved_edges.append((None, mat_uid, "used_with", {"via": "material"}))

                eintraege_for_meta.append({
                    "ik": editor_ik,
                    "pk": editor_pk,
                    "konkretisierung": entry.konkretisierung or "",
                    "hinweise": hinweise_uuid,
                    "material": material_text,
                })

            # Lernsequenz-Knoten (metadata mit editor-kompatiblen eintraege)
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
                    "std": getattr(ls, "std", None),
                    "eintraege": eintraege_for_meta,
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

            # 4. Vorberechnete Kanten anlegen (dedupliziert nach to_node_id + relation)
            seen_edges: set[tuple[str, str]] = set()
            for (_from, to_id, relation, meta) in resolved_edges:
                edge_key = (str(to_id), relation)
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)
                await create_edge(db, lernsequenz_id, to_id, relation, meta or None)
                stats.edge_count += 1

    return curriculum_id, stats


def _normalize_ik_input(ik_raw: str | list | None, ik_partiell_default: bool) -> list[tuple[str, bool]]:
    """Normalisiert den ik-Eingabewert auf eine Liste von (nr, partiell)-Paaren."""
    if not ik_raw:
        return []
    if isinstance(ik_raw, str):
        return [(nr.strip(), ik_partiell_default) for nr in ik_raw.split(",") if nr.strip()]
    if isinstance(ik_raw, list):
        result = []
        for item in ik_raw:
            if isinstance(item, dict):
                nr = item.get("nr")
                partiell = bool(item.get("partiell", False))
                if nr:
                    result.append((str(nr), partiell))
            elif isinstance(item, str) and item.strip():
                result.append((item.strip(), ik_partiell_default))
        return result
    return []
