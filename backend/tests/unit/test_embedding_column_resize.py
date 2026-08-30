"""Unit-Tests für die Umstellung der Vektorbreite (app/db/embedding_column.py).

Schwerpunkt ist die **Idempotenz-Sperre**: Entspricht die Spalte bereits der Zielbreite,
darf nichts passieren. Ohne sie würde jeder Aufruf — ob per Migration 0043 oder per
scripts/resize_embedding_column.py — sämtliche Embeddings verwerfen, obwohl sich das Modell
nicht geändert hat, und ein stundenlanges Re-Embedding erzwingen.

Ergänzend: die zwingende Statement-Reihenfolge (ein vorhandener Index blockiert sonst den
Typwechsel) und die Zusage, dass **kein** Vektorindex neu angelegt wird — die semantische
Suche läuft seit Migration 0052 absichtlich als vollständiger Durchlauf.
"""
from unittest.mock import MagicMock

import pytest

from app.db.embedding_column import (
    VECTOR_MAX_DIM,
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
    """Index weg → NULL → ALTER. Danach wird **kein** Index mehr angelegt.

    Ein vorhandener Index blockiert den Typwechsel, und ein ALTER auf Vektoren fremder
    Breite schlägt fehl — die Reihenfolge ist also keine Stilfrage. Das abschließende
    CREATE ist mit Migration 0052 entfallen.
    """
    conn, executed = _fake_conn("vector(1536)", rowcount=1)

    resize_embedding_column(conn, 768)

    assert _writes(executed) == ["DROP", "UPDATE", "ALTER"]


def test_modell_deklariert_keinen_vektorindex():
    """Zweite Hälfte der Zusage aus Migration 0052 — die für `autogenerate`.

    Migration und Modell müssen zusammenpassen: Stünde der Index weiter in
    ``ContextNode.__table_args__``, würde die nächste generierte Migration ihn
    kommentarlos wieder anlegen und die Suchgüte still halbieren.
    """
    from app.db.models import ContextNode

    verdaechtig = [
        i.name for i in ContextNode.__table__.indexes
        if "embedding" in (i.name or "") or "embedding" in {c.name for c in i.columns}
    ]
    assert verdaechtig == [], f"Vektorindex im Modell wieder aufgetaucht: {verdaechtig}"


def test_legt_keinen_vektorindex_an():
    """Gegenprobe zu Migration 0052: Die Umstellung darf keinen Index zurückbringen.

    Der frühere HNSW-Index lieferte nur rund die Hälfte der ähnlichsten Knoten. Käme er
    über diesen Weg zurück, fiele das nirgends auf — er wirft keinen Fehler, er liefert
    stillschweigend schlechtere Treffer.
    """
    conn, executed = _fake_conn("vector(1536)")

    resize_embedding_column(conn, 1024)

    assert not [s for s in executed if "CREATE INDEX" in s]
    assert not [s for s in executed if "hnsw" in s.lower()]


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

def test_rejects_dimension_above_vector_limit():
    """Der pgvector-Typ speichert bis 16.000 Dim. — früh und verständlich abbrechen.

    Bis 08/2026 lag die Grenze bei 2000: der Indexgrenze von HNSW. Mit dem Index
    (Migration 0052) ist sie entfallen — breitere Modelle sind seither nutzbar, kosten
    ohne Index aber linear mehr Suchzeit.
    """
    conn, executed = _fake_conn("vector(1536)")

    with pytest.raises(ValueError) as exc:
        resize_embedding_column(conn, VECTOR_MAX_DIM + 1)

    assert str(VECTOR_MAX_DIM) in str(exc.value)
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
