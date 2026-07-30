"""Unit-Tests für Migration 0043 (Vektorbreite von context_nodes.embedding).

Die eigentliche Umstellungslogik liegt in app/db/embedding_column.py und ist dort getestet
(test_embedding_column_resize.py). Hier geht es nur um die Migrationshülle: Woher kommt die
Zielbreite, und ist der Offline-Modus gesperrt?

Die Migration liegt unter alembic/versions/ und ist kein importierbares Paket (Dateiname
beginnt mit einer Ziffer), daher wird sie über importlib per Pfad geladen.
"""
import importlib.util
from pathlib import Path

import pytest

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic" / "versions" / "0043_embedding_dimensions.py"
)


@pytest.fixture
def migration():
    spec = importlib.util.spec_from_file_location("migration_0043", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def online(migration, monkeypatch):
    """Tut so, als liefe die Migration online (mit Datenbankverbindung)."""
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)


def test_upgrade_reads_target_from_settings(migration, monkeypatch, online):
    """Die Zielbreite kommt aus den Settings — kein Literal in der Migration."""
    from app.config import settings

    monkeypatch.setattr(settings, "embedding_dimensions", 768)
    calls = []
    monkeypatch.setattr(migration, "_apply", lambda target: calls.append(target))

    migration.upgrade()

    assert calls == [768]


def test_downgrade_targets_the_pre_migration_width(migration, monkeypatch):
    """downgrade() stellt 1536 her — den Stand aus 0018, unabhängig von der .env."""
    calls = []
    monkeypatch.setattr(migration, "_apply", lambda target: calls.append(target))

    migration.downgrade()

    assert calls == [1536]


def test_offline_mode_is_refused(migration, monkeypatch):
    """`alembic upgrade --sql` muss abbrechen, nicht raten.

    Die Idempotenz-Sperre braucht die tatsächliche Spaltenbreite aus dem Katalog; ohne
    Verbindung ist die nicht zu bekommen. Ein generiertes SQL-Skript würde im Zweifel alle
    Embeddings verwerfen.
    """
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: True)

    with pytest.raises(RuntimeError) as exc:
        migration._apply(1024)

    assert "Offline" in str(exc.value)
    assert "resize_embedding_column" in str(exc.value)


def test_skip_is_logged_without_touching_anything(migration, monkeypatch, online, caplog):
    """Bei passender Breite meldet die Migration das Überspringen."""
    from app.db.embedding_column import ResizeResult

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(
        migration, "resize_embedding_column",
        lambda conn, target: ResizeResult(changed=False, previous=1536, target=1536),
    )

    with caplog.at_level("INFO", logger="alembic.runtime.migration"):
        migration._apply(1536)

    assert any("übersprungen" in r.getMessage() for r in caplog.records)


def test_cleared_count_is_logged_as_warning(migration, monkeypatch, online, caplog):
    """Verworfene Embeddings müssen unübersehbar im Log stehen — mit Anzahl."""
    from app.db.embedding_column import ResizeResult

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(
        migration, "resize_embedding_column",
        lambda conn, target: ResizeResult(
            changed=True, previous=1536, target=1024, cleared=4711
        ),
    )

    with caplog.at_level("INFO", logger="alembic.runtime.migration"):
        migration._apply(1024)

    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("4711" in m and "embedding_backfill" in m for m in warnings)
