import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import app.artifacts.limits as limits
import app.artifacts.store as store

_NOW = datetime(2026, 7, 7, tzinfo=timezone.utc)


# ── Limits (role-/jahrgangsbasiert) ──────────────────────────────────────────

def test_get_artifact_limits_teacher_student_fallback():
    cfg = {
        "roles": {"teacher": {"retention_days": 730, "quota_bytes": 999}},
        "grades": {5: {"retention_days": 365, "quota_bytes": 50}},
    }
    with patch("app.artifacts.limits._load", return_value=cfg):
        assert limits.get_artifact_limits(["teacher"], None) == (730, 999)
        assert limits.get_artifact_limits(["teacher", "admin"], None) == (730, 999)  # admin=teacher
        assert limits.get_artifact_limits(["student"], 5) == (365, 50)
        # unbekannter Jahrgang → Default-Student
        assert limits.get_artifact_limits(["student"], 99)[0] == 365
        # keine Rolle → Fallback
        assert limits.get_artifact_limits([], None)[0] == 365


def test_limits_fallback_when_file_missing(monkeypatch):
    monkeypatch.setattr(limits.settings, "artifact_limits_path", "/nichtvorhanden/x.yaml")
    limits.invalidate_cache()
    try:
        assert limits.get_artifact_limits(["teacher"], None) == (730, 1073741824)  # Built-in-Default
    finally:
        limits.invalidate_cache()


# ── Store ────────────────────────────────────────────────────────────────────

async def test_save_artifact_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(store.settings, "artifact_storage_dir", str(tmp_path))
    monkeypatch.setattr(store, "get_artifact_limits", lambda roles, grade: (365, 10_000))
    res = MagicMock(); res.scalar_one = MagicMock(return_value=0)
    db = MagicMock(); db.add = MagicMock(); db.commit = AsyncMock(); db.execute = AsyncMock(return_value=res)

    art = await store.save_artifact(
        db, owner_pseudonym="p", roles=["student"], grade=5, kind="image",
        mime_type="image/png", data=b"PNG", title="Bild", now=_NOW,
    )

    assert art.byte_size == 3
    assert art.expires_at == _NOW + timedelta(days=365)   # Aufbewahrung eingefroren
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    rec = SimpleNamespace(id=art.id, mime_type="image/png")
    assert store.read_artifact_bytes(rec) == b"PNG"


async def test_save_artifact_quota_exceeded(monkeypatch, tmp_path):
    monkeypatch.setattr(store.settings, "artifact_storage_dir", str(tmp_path))
    monkeypatch.setattr(store, "get_artifact_limits", lambda roles, grade: (365, 100))
    res = MagicMock(); res.scalar_one = MagicMock(return_value=90)  # 90 belegt
    db = MagicMock(); db.add = MagicMock(); db.commit = AsyncMock(); db.execute = AsyncMock(return_value=res)

    with pytest.raises(store.QuotaExceeded):
        await store.save_artifact(
            db, owner_pseudonym="p", roles=["student"], grade=5, kind="image",
            mime_type="image/png", data=b"x" * 20, title="x",  # 90+20 > 100
        )
    db.add.assert_not_called()  # nichts gespeichert


def test_read_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(store.settings, "artifact_storage_dir", str(tmp_path))
    assert store.read_artifact_bytes(SimpleNamespace(id=uuid4(), mime_type="image/png")) is None


async def test_cleanup_removes_expired(monkeypatch, tmp_path):
    monkeypatch.setattr(store.settings, "artifact_storage_dir", str(tmp_path))
    aid = uuid4()
    (tmp_path / f"{aid}.svg").write_bytes(b"svg")
    art = SimpleNamespace(id=aid, mime_type="image/svg+xml")
    sel = MagicMock(); sel.scalars.return_value.all.return_value = [art]
    db = MagicMock(); db.commit = AsyncMock(); db.execute = AsyncMock(side_effect=[sel, MagicMock()])

    stats = await store.cleanup_artifacts(db, now=_NOW)

    assert stats.expired_removed == 1
    assert not (tmp_path / f"{aid}.svg").exists()  # Datei mitgelöscht
