"""Deterministische Node-Assemblierung für den PDF→JSONL-Import.

Baut Knoten-Dicts im GLEICHEN Format wie der HTML-Scraper (`scripts/scraper/parsers.py`) —
inkl. identischem `content_hash` und `bp_version`, damit der bestehende Import sie
unverändert frisst. Die fragile bp_id-/Nummern-Logik bleibt hier (deterministisch),
nicht im LLM (KS-Plan, Zweiteilung).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.scraper.parsers import _content_hash, _now_iso, extract_bp_version


def build_node(
    *,
    bp_id: str,
    content_type: str,
    title: str,
    content: str,
    parent_bp_id: str | None = None,
    min_grade: int | None = None,
    max_grade: int | None = None,
    niveau: str = "regulär",
    relations: list | None = None,
    source_url: str | None = None,
    extra_metadata: dict | None = None,
    visibility: str = "global",
    node_type: str = "knowledge",
) -> dict[str, Any]:
    """Ein Knoten im Scraper-JSONL-Format. `content_hash` = sha256 des `content`
    (identisch zum Scraper → Idempotenz); `bp_version` aus der bp_id abgeleitet."""
    metadata: dict[str, Any] = {
        "bp_id": bp_id,
        "source_url": source_url,
        "scraped_at": _now_iso(),
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    return {
        "bp_id": bp_id,
        "type": node_type,
        "content_type": content_type,
        "title": title,
        "content": content,
        "content_hash": _content_hash(content),
        "parent_bp_id": parent_bp_id,
        "relations": relations or [],
        "min_grade": min_grade,
        "max_grade": max_grade,
        "niveau": niveau,
        "bp_version": extract_bp_version(bp_id),
        "metadata": metadata,
        "visibility": visibility,
    }


def write_jsonl(nodes: list[dict], path: Path) -> None:
    """Schreibt die Knoten als JSONL (eine Zeile je Knoten, UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for node in nodes:
            f.write(json.dumps(node, ensure_ascii=False) + "\n")
