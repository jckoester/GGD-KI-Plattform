"""Unit-Tests für den Startup-Konsistenzcheck Spaltenbreite ↔ EMBEDDING_DIMENSIONS.

Der Check ist die einzige Stelle, an der eine vergessene Migration nach einem Modellwechsel
laut auffällt. Ohne ihn bliebe nur `metadata.embedding_error` pro Knoten — nach außen sähe es
schlicht so aus, als fände die semantische Suche nichts.

Wichtig ist dabei auch, was der Check NICHT tut: Er darf den Start nie verhindern. Chat,
Assistenten und Unterrichtsplanung laufen ohne Embeddings weiter.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.main import check_embedding_dimension


@asynccontextmanager
async def _session_yielding(value):
    """AsyncSessionLocal-Ersatz, dessen execute().scalar() `value` liefert."""
    result = MagicMock()
    result.scalar = MagicMock(return_value=value)
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    yield session


@asynccontextmanager
async def _session_raising():
    raise RuntimeError("DB nicht erreichbar")
    yield  # pragma: no cover


def _patch_session(factory):
    return patch("app.main.AsyncSessionLocal", factory)


async def test_matching_dimension_passes(monkeypatch, caplog):
    monkeypatch.setattr(settings, "embedding_dimensions", 1536)

    with _patch_session(lambda: _session_yielding("vector(1536)")):
        with caplog.at_level("INFO", logger="app.main"):
            ok = await check_embedding_dimension()

    assert ok is True
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


async def test_mismatch_is_logged_as_error_with_both_widths(monkeypatch, caplog):
    """Die Meldung muss beide Breiten nennen — sonst rät der Betreiber."""
    monkeypatch.setattr(settings, "embedding_dimensions", 1024)

    with _patch_session(lambda: _session_yielding("vector(1536)")):
        with caplog.at_level("ERROR", logger="app.main"):
            ok = await check_embedding_dimension()

    assert ok is False
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 1
    assert "1536" in errors[0] and "1024" in errors[0]


async def test_mismatch_message_names_both_ways_out(monkeypatch, caplog):
    """Handlungsanweisung: Konfiguration korrigieren ODER Schema angleichen."""
    monkeypatch.setattr(settings, "embedding_dimensions", 1024)

    with _patch_session(lambda: _session_yielding("vector(1536)")):
        with caplog.at_level("ERROR", logger="app.main"):
            await check_embedding_dimension()

    message = next(r.getMessage() for r in caplog.records if r.levelname == "ERROR")
    assert "EMBEDDING_DIMENSIONS" in message
    assert "resize_embedding_column" in message
    assert "embedding_backfill" in message
    assert "modellwechsel.md" in message


async def test_unknown_dimension_warns_but_does_not_fail(monkeypatch, caplog):
    """Frische DB ohne Migrationen → Hinweis, kein Fehler."""
    monkeypatch.setattr(settings, "embedding_dimensions", 1536)

    with _patch_session(lambda: _session_yielding(None)):
        with caplog.at_level("WARNING", logger="app.main"):
            ok = await check_embedding_dimension()

    assert ok is False
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("alembic upgrade head" in m for m in warnings)
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


async def test_database_error_does_not_propagate(monkeypatch, caplog):
    """Ist die DB nicht erreichbar, darf der Check den Start nicht abbrechen."""
    monkeypatch.setattr(settings, "embedding_dimensions", 1536)

    with _patch_session(_session_raising):
        with caplog.at_level("WARNING", logger="app.main"):
            ok = await check_embedding_dimension()  # darf NICHT werfen

    assert ok is False
    assert any(r.levelname == "WARNING" for r in caplog.records)


async def test_lifespan_completes_despite_mismatch(monkeypatch, caplog):
    """Der Start läuft trotz Fehlkonfiguration durch — kein Hard-Fail.

    Kernzusage des Schritts: Ein Detail des Kontextspeichers darf die Plattform nicht
    lahmlegen. Der echte Check läuft hier mit (nicht gemockt), damit der Test das auch
    tatsächlich zeigt und nicht nur behauptet.
    """
    from app.main import lifespan

    monkeypatch.setattr(settings, "embedding_dimensions", 999)
    entered = False

    # `get_auth_adapter` wird in der Lifespan lokal importiert — also am Ursprungsmodul
    # patchen, nicht an app.main. Sonst hinge der Test an einer vorhandenen auth.yaml.
    with patch("app.auth.dependencies.get_auth_adapter", MagicMock()), \
         _patch_session(lambda: _session_yielding("vector(1536)")), \
         caplog.at_level("ERROR", logger="app.main"):
        async with lifespan(MagicMock()):
            entered = True

    assert entered is True
    # Und der Fehler wurde dabei wirklich gemeldet:
    assert any(
        "KONFIGURATIONSFEHLER" in r.getMessage()
        for r in caplog.records if r.levelname == "ERROR"
    )


async def test_dimension_is_read_from_settings_not_hardcoded(monkeypatch, caplog):
    """Gegenprobe: bei 768 gilt 768 als korrekt, nicht 1536."""
    monkeypatch.setattr(settings, "embedding_dimensions", 768)

    with _patch_session(lambda: _session_yielding("vector(768)")):
        ok = await check_embedding_dimension()

    assert ok is True
