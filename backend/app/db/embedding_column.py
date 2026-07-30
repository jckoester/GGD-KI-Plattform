"""Vektorbreite von ``context_nodes.embedding`` umstellen (Schema-Wartung).

Gemeinsame Implementierung für **zwei Einstiegspunkte**, damit beide garantiert identisch
arbeiten:

* **Alembic-Migration 0043** — der Pfad für Neuinstallationen und Deployments.
* **``scripts/resize_embedding_column.py``** — der Pfad für einen späteren Modellwechsel im
  laufenden Betrieb. Nötig, weil Alembic eine bereits angewendete Revision nicht erneut
  ausführt: Sobald Migrationen oberhalb von 0043 existieren, ist
  ``downgrade 0042 && upgrade head`` keine Option mehr (es würde die späteren Revisionen
  mit aus- und wieder einbauen).

⚠️ **Kopplung Migration ↔ App-Code:** Migration 0043 importiert dieses Modul. Migrationen
sind normalerweise eingefrorene historische Artefakte; hier ist die gemeinsame Nutzung
gewollt, weil ein Auseinanderlaufen der beiden Pfade genau das Risiko wäre. Die API unten
(``current_dimension``/``resize_embedding_column``) ist deshalb absichtlich minimal und
soll stabil bleiben — Änderungen daran immer gegen 0043 prüfen.

Warum die Vektoren dabei verworfen werden: Embeddings verschiedener Modelle liegen in
unterschiedlichen Vektorräumen, die Kosinus-Distanz zwischen ihnen ist bedeutungslos. Ein
Cast auf die neue Breite wäre nicht nur formal unmöglich, sondern inhaltlich falsch. Nach
der Umstellung ist ein vollständiges Re-Embedding nötig
(``scripts/embedding_backfill.py``).
"""

from dataclasses import dataclass

# pgvector indiziert HNSW bis 2000 Dimensionen. Darüber schlägt erst die Index-Anlage fehl —
# mit einer Meldung, die den Zusammenhang zur Konfiguration nicht nennt.
HNSW_MAX_DIM = 2000

_CURRENT_DIM_SQL = """
    SELECT format_type(a.atttypid, a.atttypmod)
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = 'context_nodes'
      AND a.attname = 'embedding'
      AND a.attnum > 0
      AND NOT a.attisdropped
"""

# Muss der Definition in models.py (ContextNode.__table_args__) und Migration 0018
# entsprechen — sonst weicht der Index nach einer Umstellung stillschweigend ab.
_CREATE_INDEX_SQL = """
    CREATE INDEX idx_context_nodes_embedding
    ON context_nodes
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE embedding IS NOT NULL
"""


@dataclass(frozen=True)
class ResizeResult:
    """Ergebnis einer Umstellung.

    ``changed=False`` heißt: Die Spalte entsprach bereits der Zielbreite, es wurde nichts
    angefasst und die vorhandenen Embeddings sind unverändert.
    """

    changed: bool
    previous: int | None
    target: int
    cleared: int = 0


def current_dimension(conn) -> int | None:
    """Aktuelle Vektorbreite der Spalte aus dem Katalog.

    Gibt ``None`` zurück, wenn die Spalte fehlt oder keine Breitenangabe trägt
    (``vector`` ohne Typmod) — beides wird von der Umstellung als „unbekannt" behandelt.
    """
    raw = conn.exec_driver_sql(_CURRENT_DIM_SQL).scalar()
    if not raw or "(" not in raw:
        return None
    try:
        return int(raw.split("(", 1)[1].rstrip(")"))
    except ValueError:
        return None


def resize_embedding_column(conn, target: int, *, dry_run: bool = False) -> ResizeResult:
    """Stellt ``context_nodes.embedding`` auf ``target`` Dimensionen um.

    **Idempotent:** Stimmt die Spaltenbreite bereits, passiert nichts. Ohne diese Sperre
    würde jeder Aufruf sämtliche Embeddings verwerfen, obwohl sich nichts geändert hat —
    und ein stundenlanges Re-Embedding erzwingen.

    Reihenfolge ist zwingend: Der HNSW-Index blockiert den Typwechsel, und ein ``ALTER`` auf
    Vektoren fremder Breite schlägt fehl. Also Index weg → Vektoren auf NULL → ``ALTER`` →
    Index neu. Die Neuanlage ist billig, weil der partielle Index durch die NULL-Setzung
    leer ist.

    ``dry_run=True`` ermittelt nur, was passieren würde (inkl. Anzahl betroffener Zeilen),
    und schreibt nichts.

    Wirft ``ValueError``, wenn ``target`` das HNSW-Limit überschreitet.
    """
    if target > HNSW_MAX_DIM:
        raise ValueError(
            f"{target} Dimensionen überschreiten das HNSW-Limit von {HNSW_MAX_DIM} "
            f"(pgvector). Ein Modell mit schmaleren Vektoren wählen."
        )

    previous = current_dimension(conn)
    if previous == target:
        return ResizeResult(changed=False, previous=previous, target=target)

    if dry_run:
        affected = conn.exec_driver_sql(
            "SELECT count(*) FROM context_nodes WHERE embedding IS NOT NULL"
        ).scalar()
        return ResizeResult(
            changed=True, previous=previous, target=target, cleared=int(affected or 0)
        )

    conn.exec_driver_sql("DROP INDEX IF EXISTS idx_context_nodes_embedding")
    cleared = conn.exec_driver_sql(
        "UPDATE context_nodes SET embedding = NULL WHERE embedding IS NOT NULL"
    ).rowcount
    conn.exec_driver_sql(
        f"ALTER TABLE context_nodes ALTER COLUMN embedding TYPE vector({target})"
    )
    conn.exec_driver_sql(_CREATE_INDEX_SQL)

    return ResizeResult(
        changed=True, previous=previous, target=target, cleared=int(cleared or 0)
    )
