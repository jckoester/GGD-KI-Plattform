"""Fehlermarke `embedding_error` fällt mit einer gelungenen Einbettung weg (0.46).

Der Backfill räumte sie schon ab; der Sofortweg nach dem Anlegen (`enqueue_embedding_job`) ließ
sie stehen — wer nach Knoten mit Fehlermarke suchte, fand längst eingebettete.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.context.embedding import EMBEDDING_CONTENT_TYPES, enqueue_embedding_job
from app.db.models import ContextNode

pytestmark = pytest.mark.asyncio


async def test_erfolg_entfernt_die_fehlermarke(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    monkeypatch.setattr(settings, "embeddings_enabled", True)
    assert "kapitel" in EMBEDDING_CONTENT_TYPES
    node = ContextNode(category="knowledge", content_type="kapitel", title="Optik", status="active",
                       read_scope="global", write_scope="global", owner_pseudonym="system",
                       metadata_={"embedding_error": "429", "std": "12"})
    db_session.add(node)
    await db_session.flush()

    with patch("app.context.embedding.generate_embedding",
               AsyncMock(return_value=[0.1] * settings.embedding_dimensions)):
        await enqueue_embedding_job(node.id, db_session)
    await db_session.refresh(node)
    assert node.embedding is not None
    assert node.metadata_ == {"std": "12"}
