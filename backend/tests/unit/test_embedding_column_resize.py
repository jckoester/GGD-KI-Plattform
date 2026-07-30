"""Unit-Tests für die Umstellung der Vektorbreite (app/db/embedding_column.py).

Schwerpunkt ist die **Idempotenz-Sperre**: Entspricht die Spalte bereits der Zielbreite,
darf nichts passieren. Ohne sie würde jeder Aufruf — ob per Migration 0043 oder per
scripts/resize_embedding_column.py — sämtliche Embeddings verwerfen, obwohl sich das Modell
nicht geändert hat, und ein stundenlanges Re-Embedding erzwingen.

Ergänzend: die zwingende Statement-Reihenfolge (der HNSW-Index blockiert sonst den
Typwechsel) und die Index-Definition, die zu models.py / Migration 0018 passen muss.
"""
from unittest.mock import MagicMock

import pytest

from app.db.embedding_column import (
    HNSW_MAX_DIM,
    current_dimension,
    resize_embedding_column,
)


def _fake_conn(current_type: str | None, *, rowcount: int = 0, node_count: int = 0):
    """Mockt eine SQLAlchemy-Connection; sammelt alle ausgeführten Statements."""
    executed: list[str] = []

    def _exec(sql):
        executed.append(sql)
        result = MagicMock()
        if "format_type" in sql:
            result.scalar = MagicMock(return_value=current_type)
        elif sql.strip().startswith("SELECT count(*)"):
            result.scalar = MagicMock(return_value=node_count)
        result.rowcount = rowcount
        return result

    conn = MagicMock()
    conn.exec_driver_sql = _exec
    return conn, executed


def _writes(executed):
    """Nur die schreibenden Statements, in Ausführungsreihenfolge."""
    return [
        s.strip().split()[0]
        for s in executed
        if any(k in s for k in ("DROP INDEX", "UPDATE context_nodes", "ALTER TABLE", "CREATE INDEX"))
    ]


# ── Idempotenz ───────────────────────────────────────────────────────────────

def test_skips_when_dimension_already_matches():
    """Gleiche Breite → keine Schreibzugriffe. Die zentrale Schutzsperre."""
    conn, executed = _fake_conn("vector(1536)")

    result = resize_embedding_column(conn, 1536)

    assert result.changed is False
    assert result.cleared == 0
    assert _writes(executed) == [], f"hätte nichts schreiben dürfen: {executed}"


def test_skip_reports_previous_and_target():
    conn, _ = _fake_conn("vector(1024)")
    result = resize_embedding_column(conn, 1024)
    assert (result.previous, result.target) == (1024, 1024)


# ── Umstellung ───────────────────────────────────────────────────────────────

def test_resizes_and_clears_when_dimension_differs():
    conn, executed = _fake_conn("vector(1536)", rowcount=42)

    result = resize_embedding_column(conn, 1024)

    assert result.changed is True
    assert (result.previous, result.target, result.cleared) == (1536, 1024, 42)
    joined = " | ".join(executed)
    assert "UPDATE context_nodes SET embedding = NULL" in joined
    assert "ALTER TABLE context_nodes ALTER COLUMN embedding TYPE vector(1024)" in joined


def test_statement_order_is_mandatory():
    """Index weg → NULL → ALTER → Index neu.

    Der HNSW-Index blockiert den Typwechsel, und ein ALTER auf Vektoren fremder Breite
    schlägt fehl — die Reihenfolge ist also keine Stilfrage.
    """
    conn, executed = _fake_conn("vector(1536)", rowcount=1)

    resize_embedding_column(conn, 768)

    assert _writes(executed) == ["DROP", "UPDATE", "ALTER", "CREATE"]


def test_recreated_index_matches_original_definition():
    """Der neue Index muss dem aus Migration 0018 / models.py entsprechen."""
    conn, executed = _fake_conn("vector(1536)")

    resize_embedding_column(conn, 1024)

    create = next(s for s in executed if "CREATE INDEX" in s)
    assert "USING hnsw (embedding vector_cosine_ops)" in create
    assert "m = 16" in create and "ef_construction = 64" in create
    assert "WHERE embedding IS NOT NULL" in create


def test_handles_column_without_typmod():
    """'vector' ohne Breitenangabe → als unbekannt behandeln und umstellen, nicht crashen."""
    conn, executed = _fake_conn("vector")

    result = resize_embedding_column(conn, 1024)

    assert result.previous is None and result.changed is True
    assert "ALTER" in _writes(executed)


def test_handles_missing_column():
    """Fehlt die Spalte, ist die Breite unbekannt — kein Absturz beim Parsen."""
    conn, _ = _fake_conn(None)
    assert current_dimension(conn) is None


# ── Schutzgrenzen ────────────────────────────────────────────────────────────

def test_rejects_dimension_above_hnsw_limit():
    """pgvector indiziert HNSW nur bis 2000 Dim. — früh und verständlich abbrechen."""
    conn, executed = _fake_conn("vector(1536)")

    with pytest.raises(ValueError) as exc:
        resize_embedding_column(conn, HNSW_MAX_DIM + 1)

    assert str(HNSW_MAX_DIM) in str(exc.value)
    assert _writes(executed) == [], "bei Abbruch darf nichts geschrieben worden sein"


# ── Dry-Run ──────────────────────────────────────────────────────────────────

def test_dry_run_reports_without_writing():
    conn, executed = _fake_conn("vector(1536)", node_count=1234)

    result = resize_embedding_column(conn, 1024, dry_run=True)

    assert result.changed is True and result.cleared == 1234
    assert _writes(executed) == [], f"dry-run hätte nichts schreiben dürfen: {executed}"


def test_dry_run_on_matching_dimension_reports_no_change():
    conn, executed = _fake_conn("vector(1024)", node_count=999)

    result = resize_embedding_column(conn, 1024, dry_run=True)

    assert result.changed is False and result.cleared == 0
    assert _writes(executed) == []
