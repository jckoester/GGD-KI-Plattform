"""Bildungsplan-Import: JSONL -> context_nodes + context_edges.

Aufruf:
  python scripts/import_bildungsplan.py \
    --subjects config/subjects.yaml \
    --input scripts/scraper/output \
    --db-url postgresql://user:pass@localhost/ggd_ki \
    [--dry-run]
    [--fach CH]    # nur ein Fach (fach_code)

Idempotenz: Knoten werden anhand metadata->>'bp_id' identifiziert.
- Neu:               INSERT
- Hash unveraendert:  ueberspringen
- Hash geaendert:     UPDATE content + metadata; embedding auf NULL zuruecksetzen
- bp_id weggefallen: status = 'archived' (kein DELETE)

Kanten werden nach allen Knoten aufeloest; unaufloesbare Targets -> import_warnings.log.
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg2
import psycopg2.extras
import yaml

logger = logging.getLogger("import_bildungsplan")

# content_types die im Bildungsplan-Import verwendet werden
BP_CONTENT_TYPES = {
    "fachplan",
    "leitidee",
    "ik_kompetenz",
    "pk_gruppe",
    "pk_kompetenz",
    "leitperspektive",
    "leitperspektive_aspekt",
}

# Reihenfolge fuer INSERT (FK-sichere Topologie)
IMPORT_ORDER = [
    "leitperspektive",
    "leitperspektive_aspekt",
    "fachplan",
    "leitidee",
    "pk_gruppe",
    "ik_kompetenz",
    "pk_kompetenz",
]

VALID_SCHULARTEN = {"GYM", "RS", "GMS", "GS", "BSO", "SBBZ"}
SCHULJAHR_RE = re.compile(r"^\d{4}/\d{2}$")


# -- Validierung ---------------------------------------------------------------


def validate_subjects_yaml(cfg: dict) -> list[str]:
    """Gibt Liste der Fehler zurueck (leer = OK)."""
    errors = []
    if cfg.get("schulart") not in VALID_SCHULARTEN:
        errors.append(f"schulart '{cfg.get('schulart')}' nicht in {VALID_SCHULARTEN}")
    if not SCHULJAHR_RE.match(str(cfg.get("schuljahr", ""))):
        errors.append(
            f"schuljahr '{cfg.get('schuljahr')}' hat falsches Format (erwartet: YYYY/YY)"
        )
    for fach in cfg.get("subjects", []):
        fach_code = fach.get("fach_code")
        overrides = fach.get("bildungsplan_overrides", {})
        if overrides and not fach_code:
            errors.append(
                f"Fach '{fach['slug']}' hat bildungsplan_overrides aber keinen fach_code"
            )
    return errors


def preflight_check_migration(conn) -> None:
    """Wirft RuntimeError wenn Migration 0019 (related_to) oder 0021 (subject_id, etc.) nicht eingespielt ist."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT conname, pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname = 'check_context_edges_relation'
        """)
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(
                "Constraint 'check_context_edges_relation' nicht gefunden. "
                "Ist Migration 0018 eingespielt?"
            )
        constraint_def = row[1]
        if "related_to" not in constraint_def:
            raise RuntimeError(
                "Constraint 'check_context_edges_relation' enthaelt nicht 'related_to'. "
                "Bitte Migration 0019 einspielen: alembic upgrade head"
            )
        
        # Check für neue Spalten aus Migration 0021
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'context_nodes'
              AND column_name IN ('subject_id', 'min_grade', 'max_grade')
        """)
        found = {row[0] for row in cur.fetchall()}
        missing = {'subject_id', 'min_grade', 'max_grade'} - found
        if missing:
            raise RuntimeError(
                f"Spalten fehlen in context_nodes: {missing}. "
                "Bitte Migration 0021 einspielen: alembic upgrade head"
            )


def build_subject_id_lookup(conn) -> dict[str, int]:
    """Gibt dict fach_slug -> subject_id aus der subjects-Tabelle zurück."""
    with conn.cursor() as cur:
        cur.execute("SELECT slug, id FROM subjects")
        return {row[0]: row[1] for row in cur.fetchall()}


# -- Laden und Sortieren ---------------------------------------------------------


def load_jsonl_files(
    input_dir: Path, fach_filter: str | None = None
) -> list[dict[str, Any]]:
    """Laedt alle JSONL-Dateien aus dem Input-Verzeichnis."""
    nodes = []
    for jsonl_file in sorted(input_dir.glob("*.jsonl")):
        if fach_filter:
            stem = jsonl_file.stem.upper()
            if not stem.startswith(fach_filter.upper()):
                # LP-Datei immer laden (wird fuer alle Faeccher gebraucht)
                if not stem.startswith("LEITPERSPEKTIVEN"):
                    continue
        with jsonl_file.open(encoding="utf-8") as f:
            for line_nr, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    nodes.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning(f"{jsonl_file.name}:{line_nr}: JSON-Fehler: {e}")
    return nodes


def sort_nodes_by_import_order(nodes: list[dict]) -> list[dict]:
    """Sortiert Knoten in topologisch sichere Import-Reihenfolge."""
    order_map = {ct: i for i, ct in enumerate(IMPORT_ORDER)}
    return sorted(nodes, key=lambda n: order_map.get(n.get("content_type", ""), 99))


# -- Import-Logik ---------------------------------------------------------------


def build_metadata(node: dict) -> dict:
    """Baut das metadata-Dict aus JSONL-Feldern zusammen."""
    meta = dict(node.get("metadata", {}))
    meta["bp_id"] = node["bp_id"]
    meta["content_hash"] = node.get("content_hash", "")
    return meta


def upsert_node(
    cur,
    node: dict,
    dry_run: bool,
    subject_id_lookup: dict[str, int],
) -> tuple[str, UUID | None]:
    """
    Fuehrt INSERT oder UPDATE durch je nach Idempotenz-Status.
    Gibt ('inserted'|'updated'|'skipped', node_uuid) zurueck.
    """
    bp_id = node["bp_id"]
    category = node.get("type", "knowledge")
    content_type = node.get("content_type")
    title = node.get("title", bp_id)
    content = node.get("content", "")
    new_hash = node.get("content_hash", "")
    visibility = node.get("visibility", "global")
    metadata = build_metadata(node)

    # Neue Felder aus JSONL
    min_grade = node.get("min_grade")
    max_grade = node.get("max_grade")

    # subject_id: aus fach_slug ableiten (nur für Bildungsplan-Knoten mit fach_slug)
    fach_slug = node.get("fach_slug")
    subject_id = subject_id_lookup.get(fach_slug) if fach_slug else None

    # Existenz pruefen
    cur.execute(
        "SELECT id, metadata->>'content_hash' FROM context_nodes WHERE metadata->>'bp_id' = %s",
        (bp_id,),
    )
    row = cur.fetchone()

    if row is None:
        # INSERT
        if not dry_run:
            cur.execute(
                """
                INSERT INTO context_nodes
                    (category, content_type, title, content, metadata,
                     read_scope, write_scope, status, owner_pseudonym, assistant_id,
                     subject_id, min_grade, max_grade)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, 'active', NULL, NULL,
                     %s, %s, %s)
                RETURNING id
            """,
                (
                    category,
                    content_type,
                    title,
                    content,
                    json.dumps(metadata, ensure_ascii=False),
                    visibility,
                    visibility,
                    subject_id,
                    min_grade,
                    max_grade,
                ),
            )
            node_id = cur.fetchone()[0]
        else:
            node_id = None
        return "inserted", node_id

    existing_id, existing_hash = row
    if existing_hash == new_hash:
        # Content unverändert — neue Metadaten-Spalten trotzdem setzen (initialer Roll-out)
        # COALESCE: bestehende Non-NULL-Werte werden nicht überschrieben
        if not dry_run and any(v is not None for v in (subject_id, min_grade, max_grade)):
            cur.execute(
                """
                UPDATE context_nodes
                SET subject_id = COALESCE(subject_id, %s),
                    min_grade  = COALESCE(min_grade,  %s),
                    max_grade  = COALESCE(max_grade,  %s)
                WHERE id = %s
                """,
                (subject_id, min_grade, max_grade, existing_id),
            )
        return "skipped", UUID(str(existing_id))

    # UPDATE (Hash geaendert -> embedding zuruecksetzen, auch neue Felder aktualisieren)
    if not dry_run:
        cur.execute(
            """
            UPDATE context_nodes
            SET content = %s,
                title = %s,
                metadata = %s,
                subject_id = %s,
                min_grade = %s,
                max_grade = %s,
                embedding = NULL,
                updated_at = now()
            WHERE id = %s
        """,
            (content, title, json.dumps(metadata, ensure_ascii=False),
             subject_id, min_grade, max_grade, existing_id),
        )
    return "updated", UUID(str(existing_id))


def resolve_edges(
    cur,
    node: dict,
    node_id: UUID,
    dry_run: bool,
    warnings: list[str],
) -> int:
    """
    Legt Kanten fuer einen Knoten an (parent_bp_id + relations[]).
    Gibt Anzahl angelegter Kanten zurueck.
    """
    edges_created = 0

    def insert_edge(from_id: UUID, to_id: UUID, relation: str) -> bool:
        if dry_run:
            return True
        try:
            cur.execute(
                """
                INSERT INTO context_edges (from_node_id, to_node_id, relation)
                VALUES (%s, %s, %s)
                ON CONFLICT (from_node_id, to_node_id, relation) DO NOTHING
            """,
                (str(from_id), str(to_id), relation),
            )
            return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Kanten-Insert-Fehler {from_id}->{to_id} ({relation}): {e}")
            return False

    def lookup_bp_id(bp_id: str) -> UUID | None:
        cur.execute(
            "SELECT id FROM context_nodes WHERE metadata->>'bp_id' = %s", (bp_id,)
        )
        row = cur.fetchone()
        return UUID(str(row[0])) if row else None

    # parent_bp_id -> part_of-Kante
    parent_bp_id = node.get("parent_bp_id")
    if parent_bp_id:
        parent_id = lookup_bp_id(parent_bp_id)
        if parent_id:
            if insert_edge(node_id, parent_id, "part_of"):
                edges_created += 1
        else:
            warnings.append(
                f"{datetime.now(timezone.utc).isoformat()} WARN "
                f"parent_bp_id nicht aufgeloest: {parent_bp_id} (Knoten: {node['bp_id']})"
            )

    # relations[]
    for rel in node.get("relations", []):
        target_bp_id = rel.get("target_bp_id")
        relation_type = rel.get("type")
        if not target_bp_id or not relation_type:
            continue
        target_id = lookup_bp_id(target_bp_id)
        if not target_id:
            # BNT-Sonderfall: _00-Suffix -> versuche ohne letztes Segment
            if target_bp_id.endswith("_00"):
                alt_bp_id = target_bp_id[:-3]
                target_id = lookup_bp_id(alt_bp_id)
            if not target_id:
                warnings.append(
                    f"{datetime.now(timezone.utc).isoformat()} WARN "
                    f"target_bp_id nicht aufresoelt: {target_bp_id} "
                    f"(Relation: {relation_type}, Knoten: {node['bp_id']})"
                )
                continue
        if insert_edge(node_id, target_id, relation_type):
            edges_created += 1

    return edges_created


def archive_removed_nodes(cur, known_bp_ids: set[str], dry_run: bool) -> int:
    """Setzt status='archived' fuer Knoten die nicht mehr im JSONL vorkommen."""
    if not known_bp_ids:
        return 0
    placeholders = ",".join(["%s"] * len(known_bp_ids))
    cur.execute(
        f"""
        SELECT id, metadata->>'bp_id'
        FROM context_nodes
        WHERE category = 'knowledge'
          AND content_type = ANY(%s)
          AND status = 'active'
          AND metadata->>'bp_id' NOT IN ({placeholders})
    """,
        ([ct for ct in BP_CONTENT_TYPES], *known_bp_ids),
    )
    rows = cur.fetchall()
    if not rows:
        return 0
    if not dry_run:
        ids = [row[0] for row in rows]
        cur.execute(
            "UPDATE context_nodes SET status = 'archived', archived_at = now() WHERE id = ANY(%s)",
            (ids,),
        )
    return len(rows)


# -- Hauptfunktion ---------------------------------------------------------------


def run_import(
    subjects_path: str,
    input_dir: str,
    db_url: str,
    dry_run: bool = False,
    fach_filter: str | None = None,
) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # subjects.yaml laden und validieren
    with open(subjects_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    errors = validate_subjects_yaml(cfg)
    if errors:
        for err in errors:
            logger.error(f"subjects.yaml: {err}")
        sys.exit(1)

    # JSONL laden
    nodes = load_jsonl_files(Path(input_dir), fach_filter)
    if not nodes:
        logger.warning(f"Keine JSONL-Dateien in {input_dir}")
        return

    nodes = sort_nodes_by_import_order(nodes)
    known_bp_ids = {n["bp_id"] for n in nodes}

    # psycopg2-URL normalisieren (asyncpg-URLs umwandeln)
    psycopg2_url = db_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg2://", "postgresql://"
    )

    conn = psycopg2.connect(psycopg2_url)
    psycopg2.extras.register_uuid()

    # Hilfsfunktion zum Extrahieren von fach_slug aus bp_id
    def _fach_slug_from_bp_id(bp_id: str) -> str | None:
        """Versucht den Fach-Slug aus der bp_id zu extrahieren.
        
        Bildungsplan-IDs enthalten den Fach-Code als Segment:
        'BP2016BW_ALLG_GYM_CH_IK_7-8_01' -> 'CH'
        'BNE_01' (Leitperspektive) -> None
        """
        # Suche nach bekannten Fach-Codes in bp_id
        # fach_code_to_slug wird unten aus cfg aufgebaut
        parts = bp_id.split('_')
        for part in parts:
            if part in fach_code_to_slug:
                return fach_code_to_slug[part]
        return None

    # fach_code -> slug Mapping aus subjects.yaml bauen
    fach_code_to_slug: dict[str, str] = {}
    for fach in cfg.get("subjects", []):
        fc = fach.get("fach_code")
        if fc:
            fach_code_to_slug[fc.upper()] = fach["slug"]

    try:
        # Pre-Flight
        preflight_check_migration(conn)

        # Lookup-Tabelle aus DB laden
        subject_id_lookup = build_subject_id_lookup(conn)

        with conn.cursor() as cur:
            warnings: list[str] = []
            stats = {
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "archived": 0,
                "edges": 0,
            }

            # Knoten upserten
            node_id_map: dict[str, UUID] = {}  # bp_id -> uuid
            for node in nodes:
                # fach_slug für subject_id-Lookup anhängen
                node["fach_slug"] = _fach_slug_from_bp_id(node["bp_id"])
                status, node_id = upsert_node(cur, node, dry_run, subject_id_lookup)
                stats[status] += 1
                if node_id:
                    node_id_map[node["bp_id"]] = node_id
                elif not dry_run:
                    # Existierenden Knoten nachschlagen (bei 'skipped')
                    cur.execute(
                        "SELECT id FROM context_nodes WHERE metadata->>'bp_id' = %s",
                        (node["bp_id"],),
                    )
                    row = cur.fetchone()
                    if row:
                        node_id_map[node["bp_id"]] = UUID(str(row[0]))

            # Kanten auflösen
            for node in nodes:
                node_id = node_id_map.get(node["bp_id"])
                if node_id:
                    stats["edges"] += resolve_edges(
                        cur, node, node_id, dry_run, warnings
                    )

            # Entfernte Knoten archivieren (nur beim Voll-Import, nicht bei --fach-Filter)
            if not fach_filter:
                stats["archived"] = archive_removed_nodes(cur, known_bp_ids, dry_run)

            if not dry_run:
                conn.commit()
            else:
                conn.rollback()
                logger.info("[DRY RUN] — keine Aenderungen geschrieben")

        # Zusammenfassung
        logger.info(
            f"{'[DRY RUN] ' if dry_run else ''}"
            f"{stats['inserted']} insertiert, {stats['updated']} aktualisiert, "
            f"{stats['skipped']} unveraendert, {stats['archived']} archiviert, "
            f"{stats['edges']} Kanten, {len(warnings)} Warnungen"
        )

        # Warnungs-Log schreiben
        if warnings:
            log_dir = Path("data/import_logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            log_file = log_dir / f"import_warnings_{date_str}.log"
            with log_file.open("a", encoding="utf-8") as f:
                f.write("\n".join(warnings) + "\n")
            logger.info(f"Warnungen geschrieben nach {log_file}")

    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bildungsplan-Import")
    parser.add_argument("--subjects", default="config/subjects.yaml")
    parser.add_argument("--input", default="scripts/scraper/output")
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--fach", default=None, help="Nur dieses Fach importieren (fach_code)"
    )
    args = parser.parse_args()

    if not args.db_url:
        logger.error("Kein --db-url und DATABASE_URL nicht gesetzt")
        sys.exit(1)

    run_import(args.subjects, args.input, args.db_url, args.dry_run, args.fach)


if __name__ == "__main__":
    main()
