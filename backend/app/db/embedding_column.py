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

# Speichergrenze des pgvector-Typs ``vector``. Darüber schlägt erst der ``ALTER TABLE``
# fehl — mit einer Meldung, die den Zusammenhang zur Konfiguration nicht nennt.
#
# Hier stand bis 08/2026 die weit engere Indexgrenze von 2000 (HNSW). Sie ist mit dem
# Vektorindex entfallen (Migration 0052); Modelle mit breiteren Vektoren sind seither
# nutzbar. **Ohne Index kostet Breite aber unmittelbar Suchzeit:** Der vollständige
# Durchlauf ist linear in der Dimensionszahl, 4096 Dimensionen suchen also viermal so
# lange wie 1024. Siehe docs/admin/vor-der-installation.md.
VECTOR_MAX_DIM = 16000

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


def _parse_dim(raw: str | None) -> int | None:
    """``'vector(1536)'`` → ``1536``; ``None``/``'vector'`` → ``None``."""
    if not raw or "(" not in raw:
        return None
    try:
        return int(raw.split("(", 1)[1].rstrip(")"))
    except ValueError:
        return None


def current_dimension(conn) -> int | None:
    """Aktuelle Vektorbreite der Spalte aus dem Katalog (synchron).

    Für Migration und Wartungsskript. Gibt ``None`` zurück, wenn die Spalte fehlt oder keine
    Breitenangabe trägt (``vector`` ohne Typmod) — beides wird als „unbekannt" behandelt.
    """
    return _parse_dim(conn.exec_driver_sql(_CURRENT_DIM_SQL).scalar())


async def current_dimension_async(session) -> int | None:
    """Wie :func:`current_dimension`, aber für eine ``AsyncSession`` (Backend-Startup)."""
    from sqlalchemy import text as sa_text

    result = await session.execute(sa_text(_CURRENT_DIM_SQL))
    return _parse_dim(result.scalar())


def resize_embedding_column(conn, target: int, *, dry_run: bool = False) -> ResizeResult:
    """Stellt ``context_nodes.embedding`` auf ``target`` Dimensionen um.

    **Idempotent:** Stimmt die Spaltenbreite bereits, passiert nichts. Ohne diese Sperre
    würde jeder Aufruf sämtliche Embeddings verwerfen, obwohl sich nichts geändert hat —
    und ein stundenlanges Re-Embedding erzwingen.

    Reihenfolge ist zwingend: Ein ``ALTER`` auf Vektoren fremder Breite schlägt fehl, also
    Vektoren auf NULL → ``ALTER``. Das vorangestellte ``DROP INDEX IF EXISTS`` bleibt
    stehen, obwohl seit Migration 0052 kein Vektorindex mehr angelegt wird: Ein Index
    blockiert den Typwechsel, und auf einer Datenbank, die aus welchem Grund auch immer
    noch einen trägt, würde die Umstellung sonst scheitern. **Neu angelegt wird keiner** —
    die Suche läuft absichtlich als vollständiger Durchlauf.

    ``dry_run=True`` ermittelt nur, was passieren würde (inkl. Anzahl betroffener Zeilen),
    und schreibt nichts.

    Wirft ``ValueError``, wenn ``target`` die Speichergrenze des Typs überschreitet.
    """
    if target > VECTOR_MAX_DIM:
        raise ValueError(
            f"{target} Dimensionen überschreiten die Grenze des pgvector-Typs "
            f"von {VECTOR_MAX_DIM}. Ein Modell mit schmaleren Vektoren wählen."
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

    return ResizeResult(
        changed=True, previous=previous, target=target, cleared=int(cleared or 0)
    )
