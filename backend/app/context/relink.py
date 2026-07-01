"""Curriculum-Aktualisierung auf die aktuelle Bildungsplan-Edition (Re-Linking).

Analysiert, welche IK/PK-Referenzen eines Curriculums auf durch Re-Import/Editions-
Rollover **überholte** Knoten zeigen, und entscheidet je Referenz:

- ``current``  — zeigt bereits auf den Knoten der Ziel-Edition → nichts tun
- ``relink``   — Nr-Zwilling in Ziel-Edition **und** Text weitgehend identisch → umlinken
- ``outdated`` — kein Nr-Zwilling **oder** Text inhaltlich geändert → als veraltet markieren

Die Ziel-Edition wird **frontier-korrekt pro Stufe des Jahrgangsbandes** bestimmt
(``aktive_bp_version``). Ist das Band uneinheitlich (Übergangsjahr: neue Edition erst
in einzelnen Stufen), lautet der Modus ``duplicate`` (Original behalten, Kopie migrieren);
sonst ``in_place``. Dieses Modul liefert nur den **Plan**; Anwenden erfolgt separat.
"""

from __future__ import annotations

import difflib
import re
from copy import deepcopy
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.context.editions import aktive_bp_version
from app.context.grades import parse_grade_band
from app.context.service import load_curriculum_tree
from app.db.models import ContextNode, ContextEdge

# Ab dieser normalisierten Textähnlichkeit gilt eine Kompetenz als „weitgehend
# identisch" und wird umgelinkt; darunter → veraltet. An realen V1→V2-Texten
# kalibrierbar.
SIMILARITY_THRESHOLD = 0.90

_WS = re.compile(r"\s+")


def _normalize_competence_text(title: str | None, nr: str | None) -> str:
    """Kompetenztext für den Ähnlichkeitsvergleich normalisieren.

    Entfernt Soft-Hyphens, ein führendes Nummern-Präfix (die Nr ist bereits über
    die Identität gematcht und würde die Ähnlichkeit sonst künstlich anheben),
    normalisiert Whitespace und casef’t.
    """
    text = (title or "").replace("­", "")
    if nr:
        stripped = text.lstrip()
        if stripped.startswith(nr):
            text = stripped[len(nr):]
    return _WS.sub(" ", text).strip().casefold()


def _similarity(a: str, b: str) -> float:
    """Normalisierte Ähnlichkeit zweier bereits normalisierter Texte (0..1)."""
    if not a and not b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


async def _available_bp_versions(db: AsyncSession, subject_id: int) -> set[str]:
    """Tatsächlich importierte (aktive) Editionen eines Fachs."""
    _bp = ContextNode.metadata_["bp_version"].astext
    rows = await db.execute(
        sa.select(_bp).where(
            ContextNode.subject_id == subject_id,
            ContextNode.status == "active",
            _bp.isnot(None),
            _bp != "",
        ).distinct()
    )
    return {r[0] for r in rows.all() if r[0]}


async def _same_subject_refs(
    db: AsyncSession, ls_id, subject_id: int
) -> dict[str, list[dict]]:
    """Fach-eigene IK/PK-Referenzen einer Lernsequenz (Kanten → Knoten des Curriculum-Fachs).

    Bewusst **fach-gescopt**: Cross-Fach-IK (aus Hinweisen, anderes Fach) und
    Leitperspektiven werden **nicht** migriert (eigenes Thema). Status **nicht**
    gefiltert (archivierte Alt-Referenzen sind gerade die zu migrierenden). Nr aus
    der `kompetenz_nr` des Knotens (nicht aus dem verkürzten `eintrag.nr`).
    """
    async def q(relation: str, content_type: str) -> list[dict]:
        rows = await db.execute(
            sa.text("""
                SELECT n.id AS node_id, n.metadata->>'kompetenz_nr' AS nr, n.title AS title
                FROM context_edges e
                JOIN context_nodes n ON n.id = e.to_node_id
                WHERE e.from_node_id = :ls
                  AND e.relation = :rel
                  AND n.content_type = :ct
                  AND n.subject_id = :sid
            """),
            {"ls": str(ls_id), "rel": relation, "ct": content_type, "sid": subject_id},
        )
        return [
            {"node_id": str(r.node_id), "nr": r.nr or "", "title": r.title}
            for r in rows.mappings().all()
        ]

    return {
        "ik": await q("references", "ik_kompetenz"),
        "pk": await q("develops", "pk_kompetenz"),
    }


async def _twin_map(
    db: AsyncSession, subject_id: int, content_type: str, nr_field: str, bp_version: str
) -> dict[str, ContextNode]:
    """Aktive Ziel-Edition-Knoten eines Fachs, indiziert über ihre Nr (kompetenz_nr/pk_id)."""
    rows = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.subject_id == subject_id,
            ContextNode.content_type == content_type,
            ContextNode.status == "active",
            ContextNode.metadata_["bp_version"].astext == bp_version,
        )
    )
    out: dict[str, ContextNode] = {}
    for node in rows.scalars().all():
        key = (node.metadata_ or {}).get(nr_field)
        if key:
            out.setdefault(str(key), node)
    return out


def _decide(ref: dict, twin: ContextNode | None, nr: str) -> dict:
    """Entscheidung für eine einzelne Referenz gegen ihren Ziel-Edition-Zwilling."""
    old_id = ref.get("node_id")
    base = {
        "old_node_id": str(old_id) if old_id else None,
        "nr": nr,
        "old_title": ref.get("title"),
    }
    if twin is None:
        return {**base, "decision": "outdated", "new_node_id": None,
                "new_title": None, "similarity": None,
                "reason": "kein Knoten mit dieser Nr in der Ziel-Edition"}
    if old_id and str(old_id) == str(twin.id):
        return {**base, "decision": "current", "new_node_id": str(twin.id),
                "new_title": twin.title, "similarity": 1.0,
                "reason": "bereits auf Ziel-Edition"}
    sim = _similarity(
        _normalize_competence_text(ref.get("title"), nr),
        _normalize_competence_text(twin.title, (twin.metadata_ or {}).get("kompetenz_nr")
                                   or (twin.metadata_ or {}).get("pk_id")),
    )
    if sim >= SIMILARITY_THRESHOLD:
        return {**base, "decision": "relink", "new_node_id": str(twin.id),
                "new_title": twin.title, "similarity": round(sim, 3),
                "reason": "Nr gleich, Text weitgehend identisch"}
    return {**base, "decision": "outdated", "new_node_id": str(twin.id),
            "new_title": twin.title, "similarity": round(sim, 3),
            "reason": "Text inhaltlich geändert"}


async def plan_relink(db: AsyncSession, curriculum_id: UUID) -> dict | None:
    """Erstellt den Aktualisierungsplan für ein Curriculum. ``None`` wenn nicht gefunden."""
    tree = await load_curriculum_tree(db, curriculum_id)
    if tree is None:
        return None

    subject_id = tree["subject_id"]
    meta = tree.get("metadata") or {}
    current_bp = meta.get("bp_version") or ""
    min_g, max_g = parse_grade_band(meta.get("jahrgangsstufe"))

    available = await _available_bp_versions(db, subject_id)

    # Frontier pro Stufe des Bandes → Ziel-Edition + Modus
    per_grade: dict[int, str | None] = {}
    if min_g is not None and max_g is not None:
        for g in range(min_g, max_g + 1):
            per_grade[g] = aktive_bp_version(g, available)
    distinct = {v for v in per_grade.values() if v}
    target_bp = max(distinct) if distinct else (max(available) if available else current_bp)
    if len(distinct) > 1:
        mode = "duplicate"
    else:
        mode = "in_place"

    ik_twins = await _twin_map(db, subject_id, "ik_kompetenz", "kompetenz_nr", target_bp)
    pk_twins = await _twin_map(db, subject_id, "pk_kompetenz", "kompetenz_nr", target_bp)

    items: list[dict] = []
    for kap in tree.get("kapitel", []):
        for ls in kap.get("lernsequenzen", []):
            ls_id = ls["id"]
            refs = await _same_subject_refs(db, ls_id, subject_id)
            for ref in refs["ik"]:
                d = _decide(ref, ik_twins.get(ref["nr"]), ref["nr"])
                items.append({"kind": "ik", "ls_id": str(ls_id), **d})
            for ref in refs["pk"]:
                d = _decide(ref, pk_twins.get(ref["nr"]), ref["nr"])
                items.append({"kind": "pk", "ls_id": str(ls_id), **d})

    summary = {
        "relink": sum(1 for i in items if i["decision"] == "relink"),
        "outdated": sum(1 for i in items if i["decision"] == "outdated"),
        "current": sum(1 for i in items if i["decision"] == "current"),
    }
    # Nichts zu tun, wenn keine Änderung ansteht (alles current, in_place auf Ist-Edition).
    if mode == "in_place" and summary["relink"] == 0 and summary["outdated"] == 0:
        mode = "none"

    return {
        "curriculum_id": str(curriculum_id),
        "subject_id": subject_id,
        "jahrgangsstufe": meta.get("jahrgangsstufe"),
        "current_bp_version": current_bp,
        "target_bp_version": target_bp,
        "per_grade": {str(g): v for g, v in per_grade.items()},
        "mode": mode,
        "items": items,
        "summary": summary,
    }


# ── Anwenden ──────────────────────────────────────────────────────────────────

async def _repoint_edge(db: AsyncSession, ls_id: str, old_id: str, new_id: str, relation: str) -> None:
    """Kante (ls --relation--> old) auf new umbiegen; Duplikat vermeiden (kein Unique-Constraint)."""
    exists = (await db.execute(sa.text(
        "SELECT 1 FROM context_edges WHERE from_node_id=CAST(:ls AS uuid) "
        "AND to_node_id=CAST(:new AS uuid) AND relation=:rel LIMIT 1"),
        {"ls": ls_id, "new": new_id, "rel": relation})).first()
    if exists:
        await db.execute(sa.text(
            "DELETE FROM context_edges WHERE from_node_id=CAST(:ls AS uuid) "
            "AND to_node_id=CAST(:old AS uuid) AND relation=:rel"),
            {"ls": ls_id, "old": old_id, "rel": relation})
    else:
        await db.execute(sa.text(
            "UPDATE context_edges SET to_node_id=CAST(:new AS uuid) WHERE from_node_id=CAST(:ls AS uuid) "
            "AND to_node_id=CAST(:old AS uuid) AND relation=:rel"),
            {"ls": ls_id, "new": new_id, "old": old_id, "rel": relation})


async def apply_relink(db: AsyncSession, curriculum_id: UUID, plan: dict) -> dict:
    """Wendet einen Plan **in-place** an: Kanten repointen, ``eintraege`` (node_id/veraltet),
    Curriculum-``bp_version``. Committet. Gibt die Summary zurück.
    """
    relink_map = {i["old_node_id"]: i["new_node_id"] for i in plan["items"] if i["decision"] == "relink"}
    outdated_set = {i["old_node_id"] for i in plan["items"] if i["decision"] == "outdated"}

    for i in plan["items"]:
        if i["decision"] != "relink":
            continue
        relation = "references" if i["kind"] == "ik" else "develops"
        await _repoint_edge(db, i["ls_id"], i["old_node_id"], i["new_node_id"], relation)

    affected_ls = {i["ls_id"] for i in plan["items"] if i["decision"] in ("relink", "outdated")}
    for ls_id in affected_ls:
        node = await db.get(ContextNode, UUID(ls_id))
        if node is None or not node.metadata_:
            continue
        meta = deepcopy(node.metadata_)
        changed = False
        for eintrag in meta.get("eintraege", []) or []:
            for key in ("ik", "pk"):
                for ref in eintrag.get(key, []) or []:
                    nid = ref.get("node_id")
                    if nid in relink_map:
                        ref["node_id"] = relink_map[nid]
                        ref.pop("veraltet", None)
                        changed = True
                    elif nid in outdated_set:
                        ref["veraltet"] = True
                        changed = True
        if changed:
            node.metadata_ = meta
            flag_modified(node, "metadata_")

    cur = await db.get(ContextNode, curriculum_id if isinstance(curriculum_id, UUID) else UUID(str(curriculum_id)))
    if cur is not None:
        cmeta = deepcopy(cur.metadata_ or {})
        cmeta["bp_version"] = plan["target_bp_version"]
        cur.metadata_ = cmeta
        flag_modified(cur, "metadata_")

    await db.commit()
    return plan["summary"]


# ── Deep-Copy (für den Band-Split-/Duplicate-Modus) ──────────────────────────

_CLONE_FIELDS = (
    "category", "content_type", "title", "content", "owner_pseudonym",
    "read_scope", "write_scope", "read_scope_group_id", "write_scope_group_id",
    "assistant_id", "subject_id", "min_grade", "max_grade", "niveau",
    "bp_version", "valid_until", "schuljahr",
)


def _clone_node(src: ContextNode, **overrides) -> ContextNode:
    data = {f: getattr(src, f) for f in _CLONE_FIELDS}
    data["status"] = "active"
    data["metadata_"] = deepcopy(src.metadata_ or {})
    data.update(overrides)
    return ContextNode(**data)


async def _children(db: AsyncSession, parent_id, content_type: str) -> list[ContextNode]:
    rows = await db.execute(sa.text("""
        SELECT n.id FROM context_nodes n
        JOIN context_edges e ON e.from_node_id = n.id
        WHERE e.to_node_id = CAST(:pid AS uuid) AND e.relation = 'part_of'
          AND n.content_type = :ct
        ORDER BY (n.metadata->>'reihenfolge')::int NULLS LAST
    """), {"pid": str(parent_id), "ct": content_type})
    ids = [r[0] for r in rows.all()]
    return [await db.get(ContextNode, nid) for nid in ids]


async def duplicate_curriculum(db: AsyncSession, curriculum_id: UUID) -> tuple[UUID, dict[str, str]]:
    """Tiefe Kopie des Curriculum-Baums (Curriculum + Kapitel + Lernsequenzen + Kanten).

    Kompetenz-/LP-Knoten werden **nicht** kopiert (geteilt) — nur die Kanten auf sie.
    Gibt ``(neue_curriculum_id, {alte_ls_id: neue_ls_id})`` zurück. Kein Commit.
    """
    cur = await db.get(ContextNode, curriculum_id)
    new_cur = _clone_node(cur, title=f"{cur.title or ''} (Kopie)")
    db.add(new_cur)
    await db.flush()

    ls_map: dict[str, str] = {}
    for kap in await _children(db, curriculum_id, "kapitel"):
        new_kap = _clone_node(kap)
        db.add(new_kap)
        await db.flush()
        db.add(ContextEdge(from_node_id=new_kap.id, to_node_id=new_cur.id, relation="part_of", metadata_={}))
        for ls in await _children(db, kap.id, "lernsequenz"):
            new_ls = _clone_node(ls)
            db.add(new_ls)
            await db.flush()
            ls_map[str(ls.id)] = str(new_ls.id)
            db.add(ContextEdge(from_node_id=new_ls.id, to_node_id=new_kap.id, relation="part_of", metadata_={}))
            edges = await db.execute(sa.text("""
                SELECT to_node_id, relation, metadata FROM context_edges
                WHERE from_node_id = CAST(:ls AS uuid)
                  AND relation IN ('references', 'develops', 'used_with')
            """), {"ls": str(ls.id)})
            for er in edges.mappings().all():
                db.add(ContextEdge(from_node_id=new_ls.id, to_node_id=er["to_node_id"],
                                   relation=er["relation"], metadata_=er["metadata"] or {}))
    await db.flush()
    return new_cur.id, ls_map


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def relink_curriculum(db: AsyncSession, curriculum_id: UUID, apply: bool) -> dict | None:
    """Vorschau (``apply=False``) oder Anwenden. Bei ``mode='duplicate'`` wird eine
    migrierte Kopie erzeugt (Original bleibt); sonst In-Place-Migration."""
    plan = await plan_relink(db, curriculum_id)
    if plan is None:
        return None
    if not apply or plan["mode"] == "none":
        return {**plan, "applied": False}

    if plan["mode"] == "in_place":
        await apply_relink(db, curriculum_id, plan)
        return {**plan, "applied": True, "result_curriculum_id": str(curriculum_id)}

    # duplicate: Kopie migrieren, Original unverändert
    new_id, ls_map = await duplicate_curriculum(db, curriculum_id)
    copy_plan = deepcopy(plan)
    copy_plan["curriculum_id"] = str(new_id)
    for it in copy_plan["items"]:
        it["ls_id"] = ls_map.get(it["ls_id"], it["ls_id"])
    await apply_relink(db, new_id, copy_plan)
    return {**plan, "applied": True, "result_curriculum_id": str(new_id),
            "duplicated_from": str(curriculum_id)}
