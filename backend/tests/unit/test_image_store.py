import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from fastapi import HTTPException

import app.chat.image_store as store
from app.config import settings


# ── Speichern / Lesen ──────────────────────────────────────────────────────────

async def test_save_and_read_roundtrip(monkeypatch, tmp_path):
    """save schreibt Datei + Row (committed); read_image_bytes liest die Bytes zurück."""
    monkeypatch.setattr(store.settings, "image_storage_dir", str(tmp_path))
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    image_id = await store.save_generated_image(
        db, pseudonym="p", conversation_id=uuid4(),
        image_bytes=b"PNGDATA", model="gpt-image-1", size="1024x1024",
    )

    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    rec = SimpleNamespace(id=image_id, mime_type="image/png")
    assert store.read_image_bytes(rec) == b"PNGDATA"


def test_read_missing_file_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(store.settings, "image_storage_dir", str(tmp_path))
    rec = SimpleNamespace(id=uuid4(), mime_type="image/png")
    assert store.read_image_bytes(rec) is None


# ── Datei-Löschung in den Lösch-Pfaden ──────────────────────────────────────────

async def test_collect_and_unlink_conversation_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(store.settings, "image_storage_dir", str(tmp_path))
    image_id = uuid4()
    (tmp_path / f"{image_id}.png").write_bytes(b"x")

    exec_result = MagicMock()
    exec_result.all.return_value = [(image_id, "image/png")]
    db = MagicMock()
    db.execute = AsyncMock(return_value=exec_result)

    paths = await store.collect_conversation_image_paths(db, [uuid4()])
    assert len(paths) == 1
    assert store.unlink_paths(paths) == 1
    assert not (tmp_path / f"{image_id}.png").exists()


async def test_collect_empty_conversation_ids_shortcircuits():
    db = MagicMock()
    db.execute = AsyncMock()
    assert await store.collect_conversation_image_paths(db, []) == []
    db.execute.assert_not_called()


# ── message_id-Verknüpfung (Schritt 5) ─────────────────────────────────────────

async def test_link_images_to_message_issues_update():
    db = MagicMock()
    db.execute = AsyncMock()
    await store.link_images_to_message(db, [uuid4(), uuid4()], uuid4())
    db.execute.assert_awaited_once()


async def test_link_images_to_message_empty_shortcircuits():
    db = MagicMock()
    db.execute = AsyncMock()
    await store.link_images_to_message(db, [], uuid4())
    db.execute.assert_not_called()


async def test_persist_links_generated_images():
    """_persist flusht + verknüpft die mid-Stream erzeugten Bilder mit der Nachricht."""
    from app.chat import router
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    ids = [uuid4()]
    with patch.object(router, "link_images_to_message", new=AsyncMock()) as link:
        await router._persist(
            db, uuid4(), "hallo", [], "antwort", {}, "model-x", generated_image_ids=ids,
        )
    db.flush.assert_awaited_once()
    link.assert_awaited_once()
    assert link.await_args.args[1] == ids
    db.commit.assert_awaited_once()


async def test_persist_without_images_does_not_link_or_flush():
    from app.chat import router
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    with patch.object(router, "link_images_to_message", new=AsyncMock()) as link:
        await router._persist(db, uuid4(), "hallo", [], "antwort", {}, "model-x")
    link.assert_not_awaited()
    db.flush.assert_not_awaited()


# ── Backstop-Cron: verwaist + über-alt ──────────────────────────────────────────

async def test_cleanup_removes_orphans_and_aged_keeps_live(monkeypatch, tmp_path):
    monkeypatch.setattr(store.settings, "image_storage_dir", str(tmp_path))
    now = datetime(2026, 7, 2, tzinfo=timezone.utc)

    live = uuid4()        # DB-Row + neu       → behalten
    aged = uuid4()        # DB-Row + zu alt    → Datei + Row löschen
    orphan_old = uuid4()  # keine Row + alt    → verwaist löschen
    orphan_new = uuid4()  # keine Row + neu    → Grace, behalten

    for i in (live, aged, orphan_old, orphan_new):
        (tmp_path / f"{i}.png").write_bytes(b"x")
    old_ts = (now - timedelta(days=500)).timestamp()
    new_ts = now.timestamp()
    os.utime(tmp_path / f"{aged}.png", (old_ts, old_ts))
    os.utime(tmp_path / f"{orphan_old}.png", (old_ts, old_ts))
    os.utime(tmp_path / f"{live}.png", (new_ts, new_ts))
    os.utime(tmp_path / f"{orphan_new}.png", (new_ts, new_ts))

    known = MagicMock()
    known.all.return_value = [(live,), (aged,)]
    db = MagicMock()
    db.execute = AsyncMock(return_value=known)
    db.commit = AsyncMock()

    stats = await store.cleanup_generated_images(db, now=now, max_age_days=400)

    assert (tmp_path / f"{live}.png").exists()
    assert (tmp_path / f"{orphan_new}.png").exists()
    assert not (tmp_path / f"{aged}.png").exists()
    assert not (tmp_path / f"{orphan_old}.png").exists()
    assert stats.aged_removed == 1
    assert stats.orphans_removed == 1
    assert stats.kept == 2
    db.commit.assert_awaited()  # aged-Row-Löschung committed


async def test_cleanup_dry_run_deletes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(store.settings, "image_storage_dir", str(tmp_path))
    now = datetime(2026, 7, 2, tzinfo=timezone.utc)
    orphan = uuid4()
    (tmp_path / f"{orphan}.png").write_bytes(b"x")
    os.utime(tmp_path / f"{orphan}.png", ((now - timedelta(days=500)).timestamp(),) * 2)

    known = MagicMock()
    known.all.return_value = []
    db = MagicMock()
    db.execute = AsyncMock(return_value=known)
    db.commit = AsyncMock()

    stats = await store.cleanup_generated_images(db, now=now, dry_run=True)

    assert (tmp_path / f"{orphan}.png").exists()  # dry-run löscht nicht
    assert stats.orphans_removed == 1             # gezählt
    db.commit.assert_not_awaited()


# ── Serving-Endpoint (Pseudonym-Autorisierung) ─────────────────────────────────

async def test_serving_returns_image_for_owner():
    from app.chat import router
    rec = SimpleNamespace(id=uuid4(), pseudonym="me", mime_type="image/png")
    with patch.object(router, "get_image_record", new=AsyncMock(return_value=rec)), \
         patch.object(router, "read_image_bytes", return_value=b"PNG"):
        resp = await router.get_generated_image(rec.id, SimpleNamespace(sub="me"), MagicMock())
    assert resp.body == b"PNG"
    assert resp.media_type == "image/png"


async def test_serving_403_for_foreign_pseudonym():
    from app.chat import router
    rec = SimpleNamespace(id=uuid4(), pseudonym="owner", mime_type="image/png")
    with patch.object(router, "get_image_record", new=AsyncMock(return_value=rec)):
        with pytest.raises(HTTPException) as ei:
            await router.get_generated_image(rec.id, SimpleNamespace(sub="intruder"), MagicMock())
    assert ei.value.status_code == 403


async def test_serving_404_missing_record():
    from app.chat import router
    with patch.object(router, "get_image_record", new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as ei:
            await router.get_generated_image(uuid4(), SimpleNamespace(sub="me"), MagicMock())
    assert ei.value.status_code == 404


async def test_serving_404_missing_file():
    from app.chat import router
    rec = SimpleNamespace(id=uuid4(), pseudonym="me", mime_type="image/png")
    with patch.object(router, "get_image_record", new=AsyncMock(return_value=rec)), \
         patch.object(router, "read_image_bytes", return_value=None):
        with pytest.raises(HTTPException) as ei:
            await router.get_generated_image(rec.id, SimpleNamespace(sub="me"), MagicMock())
    assert ei.value.status_code == 404
