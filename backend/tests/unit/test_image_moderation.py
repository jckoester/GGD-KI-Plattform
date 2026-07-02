import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import app.chat.image_moderation as im
from app.chat.image_moderation import (
    ImageBlockRule,
    ImageBlocklist,
    image_prompt_block_reason,
    invalidate_image_blocklist_cache,
    load_image_blocklist,
)


def test_empty_prompt_passes():
    assert image_prompt_block_reason("") is None
    assert image_prompt_block_reason("   ") is None


def test_harmless_prompt_passes():
    """Normaler Bildwunsch → kein Block (weder Krisen-Scan noch Blockliste greifen)."""
    assert image_prompt_block_reason("ein roter Würfel auf einer grünen Wiese") is None


def test_crisis_prompt_blocked(monkeypatch):
    """Krisen-Treffer ist für Bilder blockierend (anders als im Text-Chat)."""
    monkeypatch.setattr(im, "crisis_scan", lambda _p: object())  # simulierter Treffer
    reason = image_prompt_block_reason("irgendein prompt")
    assert reason == "Zu dieser Anfrage wird kein Bild erstellt."


def test_blocklist_pattern_blocked():
    """Ein Blocklisten-Pattern greift → dessen reason wird zurückgegeben."""
    invalidate_image_blocklist_cache()
    im._blocklist_cache = ImageBlocklist(
        rules=[ImageBlockRule(category="test", patterns=["verbotenxyz"], reason="Testgrund")]
    )
    try:
        assert image_prompt_block_reason("bitte VERBOTENxyz malen") == "Testgrund"
        assert image_prompt_block_reason("etwas harmloses") is None
    finally:
        invalidate_image_blocklist_cache()


def test_missing_blocklist_file_raises(monkeypatch, tmp_path):
    """Fehlt die YAML, faultet der Loader (wie crisis_triggers) — kein stiller Moderationsverlust."""
    invalidate_image_blocklist_cache()
    monkeypatch.setattr(im.settings, "image_blocklist_path", str(tmp_path / "nope.yaml"))
    try:
        with pytest.raises(FileNotFoundError):
            load_image_blocklist()
    finally:
        invalidate_image_blocklist_cache()


def test_shipped_blocklist_loads_and_compiles():
    """Die ausgelieferte config/image_blocklist.yaml lädt, validiert und kompiliert."""
    invalidate_image_blocklist_cache()
    try:
        bl = load_image_blocklist()
        assert len(bl.rules) >= 1
        assert all(r.compiled for r in bl.rules)
        assert all(r.reason for r in bl.rules)
    finally:
        invalidate_image_blocklist_cache()
