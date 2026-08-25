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

# Projektwurzel (scripts/ liegt direkt darunter) — für Pfade, die nicht vom
# Arbeitsverzeichnis des Aufrufers abhängen dürfen.
PROJEKT_WURZEL = Path(__file__).resolve().parent.parent

# Wo das `app`-Paket liegt, hängt vom Layout ab — es gibt zwei, und sie sind
# unvereinbar:
#
#   Entwicklung  Repo-Klon, `scripts/` und `backend/` nebeneinander
#                → das Paket liegt unter `<wurzel>/backend/app`
#   Produktion   `scripts/` ist nach `/app/import-scripts` gemountet, das Image hat
#                WORKDIR /app und das Paket direkt darunter (`/app/app`). Ein
#                `backend/`-Verzeichnis existiert dort **nicht**.
#
# In beiden Fällen ist `PROJEKT_WURZEL` das Elternverzeichnis von `scripts/` — aber
# einmal muss `backend/` angehängt werden und einmal nicht. Darum nicht raten,
# sondern nachsehen, wo `app/context/editions.py` tatsächlich liegt.
BACKEND_KANDIDATEN = (PROJEKT_WURZEL / "backend", PROJEKT_WURZEL)
BACKEND_WURZEL = next(
    (p for p in BACKEND_KANDIDATEN if (p / "app" / "context" / "editions.py").is_file()),
    None,
)
if BACKEND_WURZEL is not None and str(BACKEND_WURZEL) not in sys.path:
    sys.path.insert(0, str(BACKEND_WURZEL))

# content_types die im Bildungsplan-Import verwendet werden
BP_CONTENT_TYPES = {
    "fachplan",
    "leitidee",
    "ik_kompetenz",
    "pk_gruppe",
    "pk_kompetenz",
    "leitperspektive",
    "leitperspektive_aspekt",
    "operator",
    # Leitfaden Demokratiebildung (LFDB, aus PDF): Baustein → Themenblock → Kompetenz.
    "lfdb_baustein",
    "lfdb_themenblock",
    "lfdb_kompetenz",
}

# Reihenfolge fuer INSERT (FK-sichere Topologie)
IMPORT_ORDER = [
    "leitperspektive",
    "leitperspektive_aspekt",
    # LFDB-Hierarchie hängt am leitperspektive-Übersichtsknoten:
    "lfdb_baustein",
    "lfdb_themenblock",
    "lfdb_kompetenz",
    "fachplan",
    "leitidee",
    "pk_gruppe",
    "ik_kompetenz",
    "pk_kompetenz",
    "operator",
]

VALID_SCHULARTEN = {"GYM", "RS", "GMS", "GS", "BSO", "SBBZ"}
SCHULJAHR_RE = re.compile(r"^\d{4}/\d{2}$")


# -- Validierung ---------------------------------------------------------------


def validate_subjects_yaml(cfg: dict) -> list[str]:
    """Gibt Liste der Fehler zurueck (leer = OK)."""
    errors = []
    if cfg.get("schulart") not in VALID_SCHULARTEN:
        errors.append(f"schulart '{cfg.get('schulart')}' nicht in {VALID_SCHULARTEN}")
    # schuljahr ist optional — Single Source of Truth ist config/school_year.yaml.
    # Wenn dennoch gesetzt, wird nur das Format geprüft.
    sj = cfg.get("schuljahr")
    if sj is not None and not SCHULJAHR_RE.match(str(sj)):
        errors.append(
            f"schuljahr '{sj}' hat falsches Format (erwartet: YYYY/YY)"
        )
    # Editions-Fahrplan: Eine Edition der neuen Seitengeneration braucht die
    # Fassungsangabe für die Adresse. Der Scraper wirft sonst erst beim Lauf; hier
    # faellt es schon im Trockenlauf des Imports auf.
    for eintrag in cfg.get("bildungsplan_default", {}).get("editionen") or []:
        if str(eintrag.get("seitengeneration") or "").lower() != "gen2x":
            continue
        if not eintrag.get("quell_version"):
            errors.append(
                f"Edition '{eintrag.get('suffix') or 'Basis'}' hat "
                f"seitengeneration: gen2x, aber keine quell_version (z. B. 'V3.0')"
            )

    for fach in cfg.get("subjects", []):
        fach_code = fach.get("fach_code")
        suffix = fach.get("bildungsplan_suffix")
        if suffix is not None and not isinstance(suffix, str):
            errors.append(
                f"Fach '{fach['slug']}' hat ein nicht-textuelles bildungsplan_suffix"
            )
        elif suffix and not fach_code:
            errors.append(
                f"Fach '{fach['slug']}' hat bildungsplan_suffix aber keinen fach_code"
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
    input_path: Path, fach_filter: str | None = None
) -> tuple[list[dict[str, Any]], bool]:
    """Laedt JSONL-Dateien aus einem Verzeichnis oder einer einzelnen Datei.

    Gibt (nodes, is_full_import) zurück. is_full_import ist False wenn nur eine
    einzelne Datei geladen wurde (kein Verzeichnis-Scan), damit archive_removed_nodes
    nicht versehentlich andere Fächer archiviert.
    """
    nodes = []
    if input_path.is_file():
        # Einzelne JSONL-Datei: nur diese laden, kein Voll-Import
        with input_path.open(encoding="utf-8") as f:
            for line_nr, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    nodes.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning(f"{input_path.name}:{line_nr}: JSON-Fehler: {e}")
        return nodes, False

    for jsonl_file in sorted(input_path.glob("*.jsonl")):
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
    return nodes, True


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
    meta["bp_version"] = node.get("bp_version", "")
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
    niveau = node.get("niveau", "regulär")
    # Bildungsplan-Edition (z. B. "2016", "2016.V2") — maßgeblich vom Scraper.
    bp_version = node.get("bp_version", "")

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
        # INSERT — bewusst AUCH im Dry-Run ausgeführt. Alle Schreibvorgänge laufen
        # in einer Transaktion, die run_import am Ende per rollback() verwirft
        # (statt commit). Nur dadurch sehen die nachfolgenden resolve_edges-Lookups
        # die neu importierten Knoten — sonst würde der Dry-Run Querverweise auf
        # frisch gescrapte Knoten fälschlich als unaufgelöst melden (er fragte sonst
        # den zuletzt committeten DB-Stand ab).
        cur.execute(
            """
            INSERT INTO context_nodes
                (category, content_type, title, content, metadata,
                 read_scope, write_scope, status, owner_pseudonym, assistant_id,
                 subject_id, min_grade, max_grade, niveau, bp_version)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, 'active', NULL, NULL,
                 %s, %s, %s, %s, %s)
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
                niveau,
                bp_version,
            ),
        )
        node_id = cur.fetchone()[0]
        return "inserted", node_id

    existing_id, existing_hash = row
    if existing_hash == new_hash:
        # Content unverändert — abgeleitete Felder trotzdem aktualisieren, damit
        # Scraper-Korrekturen (z. B. das Jahrgangsband der Kursstufen-Basisfächer, Todo B1)
        # auch ohne Hash-Änderung durchschlagen. min_grade/max_grade/subject_id sind
        # deterministisch scraper-/config-abgeleitet → der NEUE Wert gewinnt, sofern gesetzt;
        # ein NULL aus dem Scrape überschreibt einen vorhandenen DB-Wert NICHT
        # (`COALESCE(neu, alt)` — Reihenfolge wichtig).
        if not dry_run:
            cur.execute(
                """
                UPDATE context_nodes
                SET title      = CASE WHEN title_locked THEN title ELSE %s END,
                    metadata   = %s,
                    subject_id = COALESCE(%s, subject_id),
                    min_grade  = COALESCE(%s, min_grade),
                    max_grade  = COALESCE(%s, max_grade),
                    niveau     = %s,
                    bp_version = %s,
                    status      = 'active',
                    archived_at = NULL
                WHERE id = %s
                """,
                (title, json.dumps(metadata), subject_id, min_grade, max_grade,
                 niveau, bp_version, existing_id),
            )
        return "skipped", UUID(str(existing_id))

    # UPDATE (Hash geaendert -> embedding zuruecksetzen, auch neue Felder aktualisieren)
    if not dry_run:
        cur.execute(
            """
            UPDATE context_nodes
            SET content = %s,
                title = CASE WHEN title_locked THEN title ELSE %s END,
                metadata = %s,
                subject_id = %s,
                min_grade = %s,
                max_grade = %s,
                niveau = %s,
                bp_version = %s,
                embedding = NULL,
                status = 'active',
                archived_at = NULL,
                updated_at = now()
            WHERE id = %s
        """,
            (content, title, json.dumps(metadata, ensure_ascii=False),
             subject_id, min_grade, max_grade, niveau, bp_version, existing_id),
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


def archive_removed_nodes(
    cur,
    known_bp_ids: set[str],
    dry_run: bool,
    subject_ids: set[int] | None = None,
    mit_fachlosen: bool = True,
) -> int:
    """Setzt status='archived' fuer Knoten die nicht mehr im JSONL vorkommen.

    ⚠️ **Nur innerhalb der Fächer, die der Import gesehen hat** (`subject_ids`).

    Vorher lief die Abfrage über die ganze Tabelle: Jeder aktive BP-Knoten, dessen `bp_id`
    nicht in den gelesenen Dateien stand, wurde archiviert — auch der von Fächern, die gar
    nicht Teil des Imports waren. Der vorhandene Schutz (`is_full_import and not
    fach_filter`) deckte nur den Einzeldatei-Fall ab, nicht diesen: **Englisch und
    Französisch werden aus PDFs importiert** und liegen in einem anderen
    Ausgabeverzeichnis. Ein Voll-Import über das Scraper-Verzeichnis sah sie nie und legte
    beide Fächer vollständig still — 959 Knoten, unbemerkt.

    `mit_fachlosen` steuert dasselbe für Knoten **ohne** Fach (Leitperspektiven und ihre
    Aspekte). Sie gehören zu keinem Fach und würden von einer reinen Fach-Einschränkung
    nie erfasst; enthielt der Import solche Knoten, sollen veraltete darunter aber sehr
    wohl archiviert werden.

    Ein ganzes Fach stilllegen geht damit nicht mehr nebenbei — das ist Absicht und
    passiert jetzt über das Fehlen in `subjects.yaml` plus `--prune-subjects`.
    """
    if not known_bp_ids:
        return 0
    if subject_ids is None:
        subject_ids = set()
    placeholders = ",".join(["%s"] * len(known_bp_ids))
    cur.execute(
        f"""
        SELECT id, metadata->>'bp_id'
        FROM context_nodes
        WHERE category = 'knowledge'
          AND content_type = ANY(%s)
          AND status = 'active'
          AND metadata->>'bp_id' NOT IN ({placeholders})
          AND (subject_id = ANY(%s) OR (subject_id IS NULL AND %s))
    """,
        (
            [ct for ct in BP_CONTENT_TYPES],
            *known_bp_ids,
            list(subject_ids),
            mit_fachlosen,
        ),
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


def stillgelegte_faecher(
    cur, subjects_cfg: dict, prune: bool, dry_run: bool
) -> tuple[int, list[tuple[str, str, int]]]:
    """Fächer, die aus `subjects.yaml` verschwunden sind, aber noch einen aktiven BP haben.

    Ein Fach aus der Konfiguration zu entfernen ist die Art, „dieses Fach gibt es nicht
    mehr" auszudrücken — dort steht ohnehin, welche Fächer existieren. Das **Melden**
    passiert deshalb immer; das **Archivieren** nur mit ``--prune-subjects``.

    Warum nicht automatisch, obwohl das Signal eindeutig aussieht:

    * ``config/subjects.yaml`` ist **gitignored**. Es gibt keinen Commit, kein Diff, kein
      `git blame` — ein verrutschter Editiervorgang ist von einer Entscheidung nicht zu
      unterscheiden.
    * ``--subjects`` ist ein **Pfadparameter**. Zeigt er versehentlich auf
      `subjects.example.yaml` (2 Fächer statt 27), fielen 25 Fächer auf einmal weg.

    Beides sind stille Fehler mit großer Reichweite. Ein bestätigender Schalter kostet
    einen Aufruf in einem Fall, der alle paar Jahre eintritt.

    Rückgabe: (archivierte Knoten, [(fach_code, name, knotenzahl)])
    """
    konfigurierte = {
        f["fach_code"] for f in subjects_cfg.get("subjects", []) if f.get("fach_code")
    }
    if not konfigurierte:
        # Leere oder unlesbare Konfiguration: nichts folgern. Sonst wäre „Datei kaputt"
        # gleichbedeutend mit „alle Fächer abgeschafft".
        logger.warning("Keine Fächer in der Konfiguration — Stilllegungs-Prüfung übersprungen")
        return 0, []

    cur.execute(
        """
        SELECT s.fach_code, s.name, count(*)
        FROM context_nodes n
        JOIN subjects s ON s.id = n.subject_id
        WHERE n.category = 'knowledge'
          AND n.content_type = ANY(%s)
          AND n.status = 'active'
          AND s.fach_code IS NOT NULL
          AND NOT (s.fach_code = ANY(%s))
        GROUP BY 1, 2
        ORDER BY 1
        """,
        ([ct for ct in BP_CONTENT_TYPES], list(konfigurierte)),
    )
    betroffen = [(r[0], r[1], r[2]) for r in cur.fetchall()]
    if not betroffen:
        return 0, []

    for code, name, anzahl in betroffen:
        logger.warning(
            "Fach '%s' (%s) steht nicht mehr in subjects.yaml, hat aber %d aktive "
            "Bildungsplan-Knoten.", code, name, anzahl,
        )

    if not prune:
        logger.warning(
            "Nicht archiviert. Mit --prune-subjects stilllegen, wenn das so gewollt ist."
        )
        return 0, betroffen

    if dry_run:
        return sum(a for _, _, a in betroffen), betroffen

    cur.execute(
        """
        UPDATE context_nodes n
        SET status = 'archived', archived_at = now()
        FROM subjects s
        WHERE s.id = n.subject_id
          AND n.category = 'knowledge'
          AND n.content_type = ANY(%s)
          AND n.status = 'active'
          AND s.fach_code IS NOT NULL
          AND NOT (s.fach_code = ANY(%s))
        """,
        ([ct for ct in BP_CONTENT_TYPES], list(konfigurierte)),
    )
    return cur.rowcount, betroffen


def archive_superseded_nodes(
    cur,
    subjects_cfg: dict,
    subject_id_lookup: dict[str, int],
    dry_run: bool,
) -> int:
    """Archiviert BP-Knoten die durch eine neuere Edition überholt sind, gemäß
    subjects.yaml.

    Maßgeblich ist ``bildungsplan_suffix`` (z.B. ".V2") — das ganze Fach steht auf einer
    Edition; fach-weit werden die Knoten ohne den Editions-Marker archiviert.

    Erkennung: bp_id des veralteten Knotens enthält NICHT '{fach_code}{suffix}'
    (z.B. 'M.V2'), während der neuere Knoten dieses Segment enthält.
    Nur Knoten mit gesetzten Klassenstufen (min_grade/max_grade NOT NULL) werden
    archiviert — Leitideen und Fachpläne bleiben unberührt.
    """
    total_archived = 0
    default_suffix = subjects_cfg.get("bildungsplan_default", {}).get("suffix", "")

    # Das laufende Schuljahr entscheidet, welche Editionen noch gebraucht werden.
    # Quelle ist `config/school_year.yaml` (bzw. SCHOOL_YEAR_PATH) — dieselbe, aus der
    # auch die Anzeige ihre Frontier berechnet.
    #
    # Ohne das `app`-Paket ist der Fahrplan nicht bestimmbar. Dann wird dieser Schritt
    # übersprungen statt den Import abzubrechen: Er läuft **nach** dem Schreiben der
    # Knoten, ein Abbruch verwirft also den vollständigen, gültigen Import. Und
    # „nicht archivieren" ist die harmlose Richtung — es verschwindet nichts, und der
    # Schritt lässt sich jederzeit nachholen.
    try:
        from app.context.editions import aktuelles_schuljahr_start
    except ModuleNotFoundError:
        logger.error(
            "archive_superseded UEBERSPRUNGEN — 'app'-Paket nicht gefunden (gesucht: %s). "
            "Ueberholte Editionen bleiben aktiv; nach Behebung erneut importieren.",
            ", ".join(str(p) for p in BACKEND_KANDIDATEN),
        )
        return 0

    schuljahr_start = aktuelles_schuljahr_start()

    for fach in subjects_cfg.get("subjects", []):
        subject_suffix = fach.get("bildungsplan_suffix", default_suffix)
        # Nichts zu tun, wenn keine vom Basis-Default abweichende Fach-Edition konfiguriert ist.
        if not subject_suffix:
            continue
        fach_slug = fach.get("slug")
        fach_code = fach.get("fach_code")
        if not fach_slug or not fach_code:
            continue
        subject_id = subject_id_lookup.get(fach_slug)
        if subject_id is None:
            logger.warning(
                f"archive_superseded: subject_id für '{fach_slug}' nicht gefunden"
            )
            continue

        # Fach-weite Edition (z.B. ganzes Fach auf '.V2')
        total_archived += _archive_subject_edition(
            cur, subject_id, fach_slug, fach_code, subject_suffix, dry_run,
            cfg=subjects_cfg, fach=fach, schuljahr_start=schuljahr_start,
        )

    return total_archived


def benoetigte_editionen(
    cfg: dict, fach: dict, schuljahr_start: int, verfuegbar: set[str]
) -> set[str]:
    """Welche Editionen (``bp_version``) dieses Fach laut Fahrplan noch braucht.

    Für jede Klassenstufe des Fachs die geltende Edition bestimmen und einsammeln. Mit
    dem Editions-Fahrplan gilt in einem Fach **nicht mehr eine einzige Fassung**: Im
    Schuljahr 2026/27 stehen die Stufen 5–7 auf V3, die Stufen 8–12 weiter auf V2 — beide
    müssen aktiv bleiben.
    """
    from app.context.editions import aktive_edition, load_edition_schedule

    editionen = load_edition_schedule(cfg)
    von = fach.get("min_grade") or 5
    bis = fach.get("max_grade") or 13
    benoetigt = set()
    for stufe in range(int(von), int(bis) + 1):
        e = aktive_edition(editionen, stufe, schuljahr_start, verfuegbar)
        if e:
            benoetigt.add(e.bp_version)
    return benoetigt


def _archive_subject_edition(
    cur,
    subject_id: int,
    fach_slug: str,
    fach_code: str,
    subject_suffix: str,
    dry_run: bool,
    cfg: dict | None = None,
    fach: dict | None = None,
    schuljahr_start: int | None = None,
) -> int:
    """Archiviert Editionen eines Fachs, die **keine Klassenstufe mehr braucht**.

    ⚠️ **Früher galt „ein Fach steht als Ganzes auf einer Edition"** — archiviert wurde
    alles ohne den aktuellen Editions-Marker. Diese Annahme stammt aus der Zeit vor dem
    Editions-Fahrplan und trägt seither nicht mehr: Ab 2026/27 stehen die Stufen 5–7 auf
    V3, die Stufen 8–12 weiterhin auf V2. Die alte Regel hätte beim Umstellen von
    Mathematik auf `.V3` **778 V2-Knoten archiviert** — genau die, die die Klassen 8–12
    noch brauchen.

    Besonders tückisch daran: Fachplan-Knoten wären aktiv geblieben, die Frontier hätte
    für Klasse 8 korrekt V2 gewählt und einen **leeren** Bildungsplan geladen. Kein
    Fehler, keine Meldung — nur kein Inhalt.

    Maßgeblich ist deshalb der Fahrplan: Welche Editionen für **irgendeine** Stufe des
    Fachs gelten, bleiben aktiv; nur der Rest wird archiviert.

    Sicherheitsnetz wie bisher: Ohne aktive Knoten der aktuellen Edition passiert nichts —
    sonst würde ein Teil-Import das gerade Importierte sofort wieder ablegen.
    """
    marker = fach_code + subject_suffix

    # Guard: ist die neue Edition überhaupt vorhanden?
    cur.execute(
        """
        SELECT count(*)
        FROM context_nodes
        WHERE subject_id = %s
          AND status = 'active'
          AND category = 'knowledge'
          AND content_type = ANY(%s)
          AND metadata->>'bp_id' LIKE %s
        """,
        (subject_id, list(BP_CONTENT_TYPES), f"%{marker}%"),
    )
    if cur.fetchone()[0] == 0:
        logger.info(
            f"archive_superseded: {fach_slug} (Edition {subject_suffix}) — "
            f"neue Edition noch nicht vorhanden, nichts archiviert"
        )
        return 0

    # Welche Editionen liegen für dieses Fach überhaupt aktiv vor?
    cur.execute(
        """
        SELECT DISTINCT metadata->>'bp_version'
        FROM context_nodes
        WHERE subject_id = %s AND status = 'active' AND category = 'knowledge'
          AND content_type = ANY(%s) AND metadata->>'bp_version' IS NOT NULL
        """,
        (subject_id, list(BP_CONTENT_TYPES)),
    )
    verfuegbar = {r[0] for r in cur.fetchall() if r[0]}

    if cfg is None or fach is None or schuljahr_start is None:
        # Ohne Fahrplan-Kontext nichts archivieren: lieber eine veraltete Edition zu
        # viel als eine, die eine Klassenstufe noch braucht.
        logger.info(
            f"archive_superseded: {fach_slug} — kein Fahrplan-Kontext, nichts archiviert"
        )
        return 0

    benoetigt = benoetigte_editionen(cfg, fach, schuljahr_start, verfuegbar)
    ueberzaehlig = verfuegbar - benoetigt
    if not ueberzaehlig:
        logger.info(
            f"archive_superseded: {fach_slug} (Edition {subject_suffix}) — "
            f"alle vorhandenen Editionen werden noch gebraucht "
            f"({', '.join(sorted(benoetigt)) or '—'}), nichts archiviert"
        )
        return 0

    cur.execute(
        """
        SELECT id, metadata->>'bp_id' AS bp_id
        FROM context_nodes
        WHERE subject_id = %s
          AND status = 'active'
          AND category = 'knowledge'
          AND content_type = ANY(%s)
          AND metadata->>'bp_version' = ANY(%s)
        """,
        (subject_id, list(BP_CONTENT_TYPES), list(ueberzaehlig)),
    )
    rows = cur.fetchall()
    if not rows:
        return 0

    logger.info(
        f"{'[DRY RUN] ' if dry_run else ''}"
        f"archive_superseded: {fach_slug} — Edition(en) {', '.join(sorted(ueberzaehlig))} "
        f"werden von keiner Klassenstufe mehr gebraucht, {len(rows)} Knoten archivieren "
        f"(weiter aktiv: {', '.join(sorted(benoetigt))})"
    )
    if not dry_run:
        cur.execute(
            """
            UPDATE context_nodes
            SET status = 'archived', archived_at = now()
            WHERE id = ANY(%s)
            """,
            ([row[0] for row in rows],),
        )
    return len(rows)


# -- Hauptfunktion ---------------------------------------------------------------


def run_import(
    subjects_path: str,
    input_dir: str,
    db_url: str,
    dry_run: bool = False,
    fach_filter: str | None = None,
    prune_subjects: bool = False,
    log_dir: str | None = None,
) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # Früh melden, nicht erst nach dem Import: Ohne `app`-Paket entfällt am Ende die
    # Archivierung überholter Editionen. Wer das hier liest, kann abbrechen, statt den
    # Lauf zu wiederholen.
    if BACKEND_WURZEL is None:
        logger.warning(
            "'app'-Paket nicht gefunden (gesucht: %s) — die Archivierung ueberholter "
            "Editionen wird am Ende uebersprungen.",
            ", ".join(str(p) for p in BACKEND_KANDIDATEN),
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
    nodes, is_full_import = load_jsonl_files(Path(input_dir), fach_filter)
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
    _edition_suffix = re.compile(r'\.\w+$')

    def _fach_slug_from_bp_id(bp_id: str) -> str | None:
        """Versucht den Fach-Slug aus der bp_id zu extrahieren.

        Bildungsplan-IDs enthalten den Fach-Code als Segment:
        'BP2016BW_ALLG_GYM_CH_IK_7-8_01'  -> 'CH'
        'BP2016BW_ALLG_GYM_M.V2_IK_5-6_01' -> 'M' (Edition-Suffix wird abgeschnitten)
        'BNE_01' (Leitperspektive)          -> None
        """
        parts = bp_id.split('_')
        for part in parts:
            # Edition-Suffix entfernen: "M.V2" → "M", "M.V3" → "M"
            part_clean = _edition_suffix.sub('', part)
            if part_clean in fach_code_to_slug:
                return fach_code_to_slug[part_clean]
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

            # Entfernte Knoten archivieren (nur beim echten Voll-Import: Verzeichnis
            # ohne --fach-Filter). Bei einzelner Datei oder --fach würden sonst alle
            # anderen Fächer versehentlich archiviert.
            #
            # Zusätzlich eingegrenzt auf die Fächer, die in diesem Import überhaupt
            # vorkamen — sonst legt ein Import aus dem Scraper-Verzeichnis die aus PDFs
            # importierten Fächer (E1, F2) still, die dort nie auftauchen.
            if is_full_import and not fach_filter:
                import_subject_ids = {
                    subject_id_lookup[slug]
                    for slug in (n.get("fach_slug") for n in nodes)
                    if slug and slug in subject_id_lookup
                }
                import_hat_fachlose = any(not n.get("fach_slug") for n in nodes)
                logger.info(
                    "Archivierung eingegrenzt auf %d Fach/Fächer%s",
                    len(import_subject_ids),
                    " + fachlose Knoten (Leitperspektiven)" if import_hat_fachlose else "",
                )
                stats["archived"] = archive_removed_nodes(
                    cur, known_bp_ids, dry_run,
                    subject_ids=import_subject_ids,
                    mit_fachlosen=import_hat_fachlose,
                )

            # Veraltete Knoten durch neuere BP-Version ersetzen
            superseded = archive_superseded_nodes(
                cur, cfg, subject_id_lookup, dry_run
            )
            stats["archived"] += superseded

            # Fächer, die aus subjects.yaml verschwunden sind: immer melden,
            # nur mit --prune-subjects auch archivieren.
            stillgelegt, _betroffen = stillgelegte_faecher(
                cur, cfg, prune_subjects, dry_run
            )
            stats["archived"] += stillgelegt

            if not dry_run:
                conn.commit()
            else:
                conn.rollback()
                logger.info("[DRY RUN] — keine Aenderungen geschrieben")

        # Zusammenfassung.
        #
        # „im Archiv" statt „archiviert": Die Zahl umfasst überwiegend Knoten, die schon
        # vorher archiviert waren. Liegt ein Fach auf `.V2`, stehen seine Basis-Dateien
        # weiterhin im Verzeichnis — `upsert_node` reaktiviert sie, direkt danach legt sie
        # `archive_superseded_nodes` wieder ab. Netto ändert sich nichts; „1368 archiviert"
        # las sich aber wie eine Stilllegung. Der Trockenlauf zeigt hier ohnehin 0, weil
        # ohne Reaktivierung nichts zu archivieren ist.
        logger.info(
            f"{'[DRY RUN] ' if dry_run else ''}"
            f"{stats['inserted']} insertiert, {stats['updated']} aktualisiert, "
            f"{stats['skipped']} unveraendert, {stats['archived']} im Archiv, "
            f"{stats['edges']} Kanten, {len(warnings)} Warnungen"
        )

        # Warnungs-Log schreiben.
        #
        # ⚠ Der Pfad ist an der **Projektwurzel** verankert, nicht am Arbeitsverzeichnis.
        # Vorher stand hier `Path("data/import_logs")`, und es entstanden zwei
        # gleichnamige Dateien mit völlig verschiedenem Inhalt: eine unter `backend/`
        # (wenn `pytest` dort lief, gefüllt mit Testfixtures wie `GYM_TST`) und eine an
        # der Wurzel (echte Importe). Beim Auswerten haben Nutzer und Assistent
        # verschiedene Dateien angesehen und aneinander vorbeigeredet.
        if warnings:
            log_dir = Path(log_dir) if log_dir else (PROJEKT_WURZEL / "data" / "import_logs")
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
        "--log-dir", default=None,
        help=(
            "Verzeichnis für das Warnungs-Log (Vorgabe: <Projektwurzel>/data/import_logs). "
            "Im Container auf ein gemountetes Volume legen — sonst sind die Warnungen "
            "nach einem `--rm`-Lauf verloren."
        ),
    )
    parser.add_argument(
        "--fach", default=None, help="Nur dieses Fach importieren (fach_code)"
    )
    parser.add_argument(
        "--prune-subjects",
        action="store_true",
        help=(
            "Fächer, die nicht mehr in subjects.yaml stehen, stilllegen (BP-Knoten "
            "archivieren). Ohne diesen Schalter werden sie nur gemeldet. Vorher mit "
            "--dry-run prüfen — ein falscher --subjects-Pfad trifft sonst viele Fächer."
        ),
    )
    args = parser.parse_args()

    if not args.db_url:
        logger.error("Kein --db-url und DATABASE_URL nicht gesetzt")
        sys.exit(1)

    run_import(
        args.subjects, args.input, args.db_url, args.dry_run, args.fach,
        args.prune_subjects, args.log_dir,
    )


if __name__ == "__main__":
    main()
