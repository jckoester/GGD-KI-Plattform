"""LFDB-Assembler: neutrale Struktur → JSONL-Knoten (KS-Plan C4, Schritt 3).

Deterministisch (keine LLM-Nichtdeterminismus in den bp_ids). 3 Ebenen:
`lfdb_baustein` → `lfdb_themenblock` → `lfdb_kompetenz`, verankert am LFDB-Übersichtsknoten
(`BP2016BW_ALLG_LP_LFDB`, vom HTML-Scraper erzeugt). Erzeugt zusätzlich einen Review-Report.
"""
from __future__ import annotations

from scripts.pdf_import.nodes import build_node

# Übersichtsknoten (vom Scraper erzeugt) — Parent der Bausteine.
LFDB_BP_ID = "BP2016BW_ALLG_LP_LFDB"


def _kompetenz_content(k: dict) -> str:
    parts = [(k.get("kompetenz") or "").strip()]
    impulse = (k.get("impulse_inhalte") or "").strip()
    if impulse:
        parts.append(f"**Impulse und Inhalte:** {impulse}")
    return "\n\n".join(p for p in parts if p)


def build_lfdb_nodes(structure: dict, *, source_url: str | None = None) -> list[dict]:
    """Baut die LFDB-Unterknoten (Baustein/Themenblock/Kompetenz) aus der neutralen Struktur."""
    nodes: list[dict] = []
    for bi, b in enumerate(structure["bausteine"], start=1):
        nr = b.get("nummer") or bi
        b_bpid = f"{LFDB_BP_ID}_B{nr}"
        b_title = f"Baustein {nr}: {b['titel']}"
        nodes.append(build_node(
            bp_id=b_bpid,
            content_type="lfdb_baustein",
            title=b_title,
            content=b["titel"],
            parent_bp_id=LFDB_BP_ID,
            source_url=source_url,
            extra_metadata={"nummer": nr},
        ))
        for ti, t in enumerate(b.get("themenbloecke", []), start=1):
            t_bpid = f"{b_bpid}_T{ti}"
            lps = t.get("leitperspektiven") or []
            nodes.append(build_node(
                bp_id=t_bpid,
                content_type="lfdb_themenblock",
                title=t["titel"],
                content=t["titel"],
                parent_bp_id=b_bpid,
                source_url=source_url,
                extra_metadata={"leitperspektiven": lps},
            ))
            for ki, k in enumerate(t.get("kompetenzen", []), start=1):
                k_bpid = f"{t_bpid}_K{ki}"
                title = (k.get("leitfrage") or k.get("kompetenz") or "").strip()
                nodes.append(build_node(
                    bp_id=k_bpid,
                    content_type="lfdb_kompetenz",
                    title=title,
                    content=_kompetenz_content(k),
                    parent_bp_id=t_bpid,
                    source_url=source_url,
                    extra_metadata={
                        "leitfrage": (k.get("leitfrage") or "").strip(),
                        "leitperspektiven": lps,
                    },
                ))
    return nodes


#: Reihenfolge der Ebenen in der JSONL — Eltern vor Kindern, wie `build_lfdb_nodes`.
_EBENEN = ("lfdb_baustein", "lfdb_themenblock", "lfdb_kompetenz")


def _natuerlich(bp_id: str) -> list:
    """`…_B2_T10` nach `…_B2_T9`."""
    import re

    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", bp_id)]


def lfdb_nodes_aus_db(zeilen: list[dict]) -> list[dict]:
    """Die LFDB-Knoten aus der Datenbank zurück als JSONL (0.53.1, Rückweg ohne LLM).

    Die JSONL des PDF-Imports ging verloren (sie lag bis 24.08.2026 in einem eigenen
    Verzeichnis); ohne sie archiviert jeder Voll-Import den LFDB. Die Knoten stehen aber
    vollständig in der Datenbank. Daraus entsteht dieselbe Datei — mit dem **gespeicherten**
    `content_hash`, damit der Import die Knoten als unverändert erkennt (kein neues
    Embedding) und sie nur wieder aktiv setzt.

    `zeilen`: je Knoten `bp_id`, `content_type`, `title`, `content`, `metadata`,
    `parent_bp_id` (über die Kante `part_of`), `min_grade`, `max_grade`, `niveau`,
    `bp_version`. Archivierte Knoten gehören dazu — gerade die sollen zurück.
    """
    aus = []
    for z in sorted(zeilen, key=lambda z: (_EBENEN.index(z["content_type"]), _natuerlich(z["bp_id"]))):
        meta = dict(z.get("metadata") or {})
        hash_ = meta.pop("content_hash", None)
        meta.pop("bp_version", None)  # setzt der Import aus dem Knoten
        if not hash_:
            raise ValueError(f"{z['bp_id']}: kein content_hash in der Datenbank")
        aus.append({
            "bp_id": z["bp_id"],
            "type": "knowledge",
            "content_type": z["content_type"],
            "title": z["title"],
            "content": z["content"] or "",
            "content_hash": hash_,
            "parent_bp_id": z["parent_bp_id"],
            "relations": [],
            "min_grade": z.get("min_grade"),
            "max_grade": z.get("max_grade"),
            "niveau": z.get("niveau") or "regulär",
            "bp_version": z.get("bp_version") or "",
            "metadata": meta,
            "visibility": "global",
        })
    return aus


def render_lfdb_report(structure: dict) -> str:
    """Menschenlesbarer Markdown-Baum zur Review (Vollständigkeit/Zuordnung prüfen)."""
    lines = ["# LFDB — Extraktions-Review", ""]
    n_b = len(structure["bausteine"])
    n_t = sum(len(b.get("themenbloecke", [])) for b in structure["bausteine"])
    n_k = sum(len(t.get("kompetenzen", []))
              for b in structure["bausteine"] for t in b.get("themenbloecke", []))
    lines.append(f"**{n_b} Bausteine · {n_t} Themenblöcke · {n_k} Kompetenzen**")
    lines.append("")
    for bi, b in enumerate(structure["bausteine"], start=1):
        nr = b.get("nummer") or bi
        lines.append(f"## Baustein {nr}: {b['titel']}")
        for t in b.get("themenbloecke", []):
            lp = ", ".join(t.get("leitperspektiven") or []) or "—"
            lines.append(f"### {t['titel']}  · Leitperspektiven: {lp}")
            for k in t.get("kompetenzen", []):
                lines.append(f"- **{(k.get('leitfrage') or '').strip()}**")
                lines.append(f"  - {(k.get('kompetenz') or '').strip()}")
                impulse = (k.get("impulse_inhalte") or "").strip()
                if impulse:
                    lines.append(f"  - _Impulse/Inhalte:_ {impulse}")
        lines.append("")
    return "\n".join(lines)
