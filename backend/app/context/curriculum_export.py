"""Curriculum-Export: YAML und PDF."""

import re
import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode

logger = logging.getLogger(__name__)

# ── Token-Regex (spiegelt Frontend hinweise.js / material.js) ─────────────────

_LP_TOKEN   = re.compile(r'@\[([^\]]*)\]\(lp:([0-9a-f-]{36})\)')
_LPA_TOKEN  = re.compile(r'@\[([^\]]*)\]\(lpa:([0-9a-f-]{36})\)')
_IK_TOKEN   = re.compile(r'#\[([^\]]*)\]\(ik:([0-9a-f-]{36})\)')
_NODE_TOKEN = re.compile(r'@\[([^\]]*)\]\(node:([0-9a-f-]{36})\)')


async def _resolve_node_meta(db: AsyncSession, node_id: str, *fields: str) -> dict | None:
    """Lädt ausgewählte metadata_-Felder eines Knotens per UUID."""
    try:
        uid = UUID(node_id)
    except ValueError:
        return None
    result = await db.execute(
        sa.select(ContextNode).where(ContextNode.id == uid, ContextNode.status == "active")
    )
    node = result.scalar_one_or_none()
    if not node:
        return None
    meta = node.metadata_ or {}
    return {f: meta.get(f) for f in fields}


async def hinweise_uuid_to_code(text: str, db: AsyncSession) -> str:
    """Übersetzt UUID-Token im Hinweise-Feld in Code-Token (für portables YAML).

    lp:<uuid>  → lp:<code>
    lpa:<uuid> → lpa:<bp_id>
    ik:<uuid>  → ik:<fach_code>:<nr>
    node:<uuid> bleibt unverändert (Material, nicht portabel).
    """
    if not text:
        return text

    async def replace_lp(m: re.Match) -> str:
        label, uid = m.group(1), m.group(2)
        meta = await _resolve_node_meta(db, uid, "code")
        if meta and meta.get("code"):
            return f"@[{label}](lp:{meta['code']})"
        logger.warning("LP-Knoten %s hat kein 'code'-Feld – Token bleibt als UUID", uid)
        return m.group(0)

    async def replace_lpa(m: re.Match) -> str:
        label, uid = m.group(1), m.group(2)
        meta = await _resolve_node_meta(db, uid, "bp_id")
        if meta and meta.get("bp_id"):
            return f"@[{label}](lpa:{meta['bp_id']})"
        logger.warning("LPA-Knoten %s hat kein 'bp_id'-Feld – Token bleibt als UUID", uid)
        return m.group(0)

    async def replace_ik(m: re.Match) -> str:
        label, uid = m.group(1), m.group(2)
        result = await db.execute(
            sa.select(ContextNode).where(
                ContextNode.id == UUID(uid), ContextNode.status == "active"
            )
        )
        node = result.scalar_one_or_none()
        if node:
            meta = node.metadata_ or {}
            nr = meta.get("nr")
            # fach_code aus subject_id ableiten
            if nr and node.subject_id:
                subj_result = await db.execute(
                    sa.text("SELECT fach_code FROM subjects WHERE id = :sid"),
                    {"sid": node.subject_id},
                )
                row = subj_result.fetchone()
                fach_code = row[0] if row else None
                if fach_code:
                    return f"#[{label}](ik:{fach_code}:{nr})"
        logger.warning("IK-Knoten %s nicht auflösbar – Token bleibt als UUID", uid)
        return m.group(0)

    # Sequenziell ersetzen (kein paralleler async replace in Python)
    result_parts = []
    last = 0
    # Alle Matches aller Patterns sammeln und nach Position sortieren
    all_matches = []
    for pattern in (_LP_TOKEN, _LPA_TOKEN, _IK_TOKEN):
        for m in pattern.finditer(text):
            all_matches.append(m)
    all_matches.sort(key=lambda m: m.start())

    for m in all_matches:
        result_parts.append(text[last:m.start()])
        if m.re is _LP_TOKEN:
            result_parts.append(await replace_lp(m))
        elif m.re is _LPA_TOKEN:
            result_parts.append(await replace_lpa(m))
        elif m.re is _IK_TOKEN:
            result_parts.append(await replace_ik(m))
        last = m.end()
    result_parts.append(text[last:])
    return "".join(result_parts)


async def build_curriculum_export_dict(db: AsyncSession, tree: dict) -> dict:
    """Baut das code-basierte Export-Dict für YAML-Serialisierung.

    Verwendet den vorberechneten `tree`-Dict aus `load_curriculum_tree`.
    """
    from app.config import settings

    meta = tree.get("metadata", {})
    # Schulname: EXPORT_SCHOOL_NAME hat Vorrang, sonst Curriculum-Metadaten
    schule = settings.export_school_name or meta.get("schule", "")

    kapitel_out = []
    for kap in tree.get("kapitel", []):
        kap_meta = kap.get("metadata", {})
        lernsequenzen_out = []

        for ls in kap.get("lernsequenzen", []):
            ls_meta = ls.get("metadata", {})
            eintraege_raw = ls_meta.get("eintraege", [])

            ik_refs_by_id = {r["node_id"]: r for r in ls.get("ik_refs", [])}
            pk_refs_by_id = {r["node_id"]: r for r in ls.get("pk_refs", [])}

            eintraege_out = []
            for e in eintraege_raw:
                # IK — intern Liste von {node_id, nr, partiell} oder Legacy-String
                ik_raw = e.get("ik") or []
                ik_list_out = []
                if isinstance(ik_raw, list):
                    for ik_item in ik_raw:
                        if isinstance(ik_item, dict):
                            node_id = ik_item.get("node_id")
                            ref = ik_refs_by_id.get(node_id, {})
                            nr = ref.get("nr") or ik_item.get("nr")
                            partiell = ik_item.get("partiell", False)
                            if nr:
                                ik_list_out.append({"nr": nr, "partiell": bool(partiell)})
                        elif isinstance(ik_item, str) and ik_item:
                            ik_list_out.append({"nr": ik_item, "partiell": False})
                elif isinstance(ik_raw, str) and ik_raw:
                    ik_list_out.append({"nr": ik_raw, "partiell": e.get("ik_partiell", False)})

                # PK
                pk_raw = e.get("pk") or []
                pk_list_out = []
                if isinstance(pk_raw, list):
                    for pk_item in pk_raw:
                        if isinstance(pk_item, dict):
                            node_id = pk_item.get("node_id")
                            ref = pk_refs_by_id.get(node_id, {})
                            pk_id = ref.get("pk_id") or pk_item.get("pk_id")
                            if pk_id:
                                pk_list_out.append({"id": pk_id})
                        elif isinstance(pk_item, str) and pk_item:
                            pk_list_out.append({"id": pk_item})

                hinweise_text = e.get("hinweise") or ""
                hinweise_coded = await hinweise_uuid_to_code(hinweise_text, db)

                eintrag_out = {
                    "ik": ik_list_out,
                    "pk": pk_list_out,
                    "konkretisierung": e.get("konkretisierung") or "",
                    "hinweise": hinweise_coded,
                    "material": e.get("material") or "",
                }
                eintraege_out.append(eintrag_out)

            lernsequenzen_out.append({
                "bp_titel": ls.get("title") or "",
                "bp_leitidee": ls_meta.get("bp_leitidee") or "",
                "reihenfolge": ls_meta.get("reihenfolge", 0),
                "std": ls_meta.get("std"),
                "eintraege": eintraege_out,
            })

        # Kapitel-Konkretisierung steht (joined) im content; als Liste re-serialisieren,
        # damit der Re-Import sie wieder zusammenfügt (Listengranularität geht verloren).
        kap_konkretisierung = [kap["content"]] if kap.get("content") else []

        kapitel_out.append({
            "titel": kap.get("title") or "",
            "reihenfolge": kap_meta.get("reihenfolge", 0),
            "std": kap_meta.get("std"),
            "hinweis": kap_meta.get("einleitung") or "",
            "konkretisierung": kap_konkretisierung,
            "lernsequenzen": lernsequenzen_out,
        })

    return {
        "schule": schule,
        "fach_code": meta.get("fach_code", ""),
        "fach": meta.get("fach", ""),
        "schulart": meta.get("schulart", ""),
        "jahrgangsstufe": meta.get("jahrgangsstufe", ""),
        "fachplan_id": meta.get("fachplan_id", ""),
        "bp_version": meta.get("bp_version", ""),
        "vorwort": tree.get("content") or "",
        "kapitel": kapitel_out,
    }


# ── PDF-Export ────────────────────────────────────────────────────────────────

def _parse_hinweise_for_pdf(text: str) -> list[dict]:
    """Zerlegt Hinweise-Text in Segmente für PDF-Rendering."""
    if not text:
        return []
    parts = []
    last = 0
    all_matches = []
    for pattern, kind in [(_LP_TOKEN, "lp"), (_LPA_TOKEN, "lpa"), (_IK_TOKEN, "ik")]:
        for m in pattern.finditer(text):
            all_matches.append((m, kind))
    all_matches.sort(key=lambda x: x[0].start())
    for m, kind in all_matches:
        if m.start() > last:
            parts.append({"kind": "text", "text": text[last:m.start()]})
        parts.append({"kind": kind, "label": m.group(1)})
        last = m.end()
    if last < len(text):
        parts.append({"kind": "text", "text": text[last:]})
    return parts


def _parse_material_for_pdf(text: str) -> list[dict]:
    """Zerlegt Material-Text in Segmente für PDF-Rendering."""
    if not text:
        return []
    parts = []
    last = 0
    for m in _NODE_TOKEN.finditer(text):
        if m.start() > last:
            parts.append({"kind": "text", "text": text[last:m.start()]})
        parts.append({"kind": "node", "label": m.group(1)})
        last = m.end()
    if last < len(text):
        parts.append({"kind": "text", "text": text[last:]})
    return parts


_md_parser = None


def _render_markdown(text: str) -> str:
    """Rendert Konkretisierungs-Markdown zu HTML (Listen, Betonung etc.).

    Roh-HTML in der Quelle wird escaped (html=False) – sicher fürs PDF-Template.
    """
    if not text:
        return ""
    global _md_parser
    if _md_parser is None:
        from markdown_it import MarkdownIt
        _md_parser = MarkdownIt("commonmark", {"html": False})
    return _md_parser.render(text)


def _build_pdf_kapitel(tree: dict) -> list[dict]:
    """Reichert die Curriculum-Struktur fürs PDF-Template an.

    - IK/PK als Volltext (Knoten-Titel aus ik_refs/pk_refs), Fallback nr/pk_id
    - Konkretisierung als gerendertes Markdown
    - Hinweise/Material als vorgeparste Segment-Listen
    """
    kapitel_out = []
    for kap in tree.get("kapitel", []):
        kap_meta = kap.get("metadata", {})
        ls_out = []
        for ls in kap.get("lernsequenzen", []):
            ls_meta = ls.get("metadata", {})
            ik_title_by_id = {r["node_id"]: r.get("title") for r in ls.get("ik_refs", [])}
            pk_title_by_id = {r["node_id"]: r.get("title") for r in ls.get("pk_refs", [])}

            eintraege_out = []
            for e in ls_meta.get("eintraege", []):
                ik_items = []
                for ik in (e.get("ik") or []):
                    if isinstance(ik, dict):
                        text = ik_title_by_id.get(ik.get("node_id")) or ik.get("nr") or ""
                        if text:
                            ik_items.append({"text": text, "partiell": bool(ik.get("partiell"))})
                    elif isinstance(ik, str) and ik:
                        ik_items.append({"text": ik, "partiell": False})

                pk_items = []
                for pk in (e.get("pk") or []):
                    if isinstance(pk, dict):
                        text = pk_title_by_id.get(pk.get("node_id")) or pk.get("pk_id") or ""
                        if text:
                            pk_items.append({"text": text})
                    elif isinstance(pk, str) and pk:
                        pk_items.append({"text": pk})

                eintraege_out.append({
                    "ik_items": ik_items,
                    "pk_items": pk_items,
                    "konkretisierung_html": _render_markdown(e.get("konkretisierung") or ""),
                    "hinweise_parts": _parse_hinweise_for_pdf(e.get("hinweise") or ""),
                    "material_parts": _parse_material_for_pdf(e.get("material") or ""),
                })

            ls_out.append({
                "title": ls.get("title"),
                "std": ls_meta.get("std"),
                "eintraege": eintraege_out,
            })
        kapitel_out.append({
            "titel": kap.get("title"),
            "std": kap_meta.get("std"),
            "lernsequenzen": ls_out,
        })
    return kapitel_out


async def render_curriculum_pdf(db: AsyncSession, tree: dict) -> bytes:
    """Rendert das Curriculum als PDF via weasyprint + Jinja2."""
    try:
        import weasyprint
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError as e:
        raise RuntimeError(
            f"PDF-Export benötigt 'weasyprint' und 'jinja2' ({e}). "
            "Bitte in requirements.txt ergänzen und installieren."
        ) from e

    import os
    from app.config import settings

    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html"]),
    )

    template = env.get_template("curriculum_pdf.html")
    meta = tree.get("metadata", {})
    school_name = settings.export_school_name or meta.get("schule", "")
    html_str = template.render(
        title=tree.get("title", ""),
        school_name=school_name,
        meta=meta,
        kapitel=_build_pdf_kapitel(tree),
    )
    pdf_bytes = weasyprint.HTML(string=html_str, base_url=templates_dir).write_pdf()
    return pdf_bytes
