import os
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.crons.cleanup_service import (
    cleanup_inactive_accounts,
    cleanup_stale_conversations,
)


class _FakeAsyncContext(AbstractAsyncContextManager):
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _ResultList:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


def _audit_entry(pseudonym: str, litellm_key: str | None = None):
    entry = MagicMock()
    entry.pseudonym = pseudonym
    entry.litellm_key = litellm_key
    return entry


class _ResultCount:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


def _antworten(kandidaten, *, fehler_beim_ersten_delete=False):
    """`db.execute`-Ersatz, der nach **Art** des Statements antwortet, nicht nach Position.

    ⚠️ Vorher stand hier eine positionsgebundene `side_effect`-Liste — eine Zeile je
    erwartetem Aufruf, in genau der Reihenfolge. Sie ist innerhalb von zwei Tagen zweimal
    gebrochen, als die Kontolöschung neue Statements bekam (Wissensbausteine 07.09.,
    Bibliothek/Lernzustand/Mitgliedschaften 08.09.) — beide Male mit einem
    `StopAsyncIteration` mitten im Lauf, das mit der geprüften Zusage nichts zu tun hat.

    Diese Fassung koppelt nur an das, worum es geht: SELECTs liefern Ergebnislisten
    (die erste die Kandidaten, jede weitere leer), alles andere quittiert. Ein neues
    DELETE in `cleanup_inactive_accounts` lässt diese Tests künftig in Ruhe.
    """
    from sqlalchemy import Select

    zustand = {"selects": 0, "deletes": 0}

    def antwort(statement, *args, **kwargs):
        if isinstance(statement, Select):
            zustand["selects"] += 1
            # 1. SELECT = Kandidatenabfrage, danach: Bildpfade, Artefaktpfade, und beim
            # zweiten Schleifendurchlauf wieder die Kandidaten — dann leer.
            return _ResultList(kandidaten if zustand["selects"] == 1 else [])
        zustand["deletes"] += 1
        if fehler_beim_ersten_delete and zustand["deletes"] == 1:
            raise RuntimeError("delete failed")
        return MagicMock()

    return antwort


@pytest.mark.asyncio
async def test_cleanup_inactive_accounts_dry_run_counts_only():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ResultCount(3))

    stats = await cleanup_inactive_accounts(db, dry_run=True, now=datetime.now(timezone.utc))

    assert stats.found == 3
    assert stats.deleted_local == 0
    assert stats.errors == 0


@pytest.mark.asyncio
async def test_cleanup_inactive_accounts_litellm_error_does_not_block_local_delete():
    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=_FakeAsyncContext())
    db.scalar = AsyncMock(return_value=None)  # keine Krisen-Schutz-Konversation
    db.execute = AsyncMock(side_effect=_antworten([_audit_entry("pseudo-1")]))

    with patch("app.crons.cleanup_service.LiteLLMClient") as client_cls:
        client = AsyncMock()
        client.delete_user.side_effect = RuntimeError("litellm unavailable")
        client_cls.return_value = client

        stats = await cleanup_inactive_accounts(
            db, dry_run=False, now=datetime.now(timezone.utc), limit=10
        )

    assert stats.found == 1
    assert stats.litellm_delete_failed == 1
    assert stats.deleted_local == 1
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_cleanup_inactive_accounts_rolls_back_single_pseudonym_on_local_error():
    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=_FakeAsyncContext())
    db.scalar = AsyncMock(return_value=None)  # keine Krisen-Schutz-Konversation
    db.execute = AsyncMock(
        side_effect=_antworten([_audit_entry("pseudo-1")], fehler_beim_ersten_delete=True)
    )

    with patch("app.crons.cleanup_service.LiteLLMClient") as client_cls:
        client = AsyncMock()
        client.delete_user.return_value = None
        client_cls.return_value = client

        stats = await cleanup_inactive_accounts(
            db, dry_run=False, now=datetime.now(timezone.utc), limit=10
        )

    assert stats.found == 1
    assert stats.deleted_local == 0
    assert stats.errors == 1
    db.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_cleanup_stale_conversations_dry_run_counts_only():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ResultCount(7))

    stats = await cleanup_stale_conversations(db, dry_run=True, now=datetime.now(timezone.utc))

    assert stats.found == 7
    assert stats.deleted_local == 0


@pytest.mark.asyncio
async def test_cleanup_stale_conversations_deletes_batch():
    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=_FakeAsyncContext())
    db.execute = AsyncMock(
        side_effect=[
            _ResultList(["conv-1", "conv-2"]),  # select ids
            _ResultList([]),  # collect_conversation_image_paths (keine Bilder)
            MagicMock(),  # delete batch
            _ResultList([]),
        ]
    )

    stats = await cleanup_stale_conversations(
        db, dry_run=False, now=datetime.now(timezone.utc), limit=100
    )

    assert stats.found == 2
    assert stats.deleted_local == 2
    assert stats.errors == 0
    db.commit.assert_awaited()
