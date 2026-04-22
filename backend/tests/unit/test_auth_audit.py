from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.auth.audit import get_primary_role, upsert_pseudonym_audit
from app.auth.base import NormalizedIdentity


def test_get_primary_role_prioritizes_teacher():
    assert get_primary_role(["teacher", "admin"]) == "teacher"
    assert get_primary_role(["student"]) == "student"
    assert get_primary_role(["admin"]) == "teacher"


@pytest.mark.asyncio
async def test_upsert_pseudonym_audit_returns_old_values():
    db = AsyncMock()
    first_result = MagicMock()
    first_result.fetchone.return_value = SimpleNamespace(role="student", grade=9)
    db.execute = AsyncMock(side_effect=[first_result, MagicMock()])

    identity = NormalizedIdentity(
        external_id="ext-1",
        roles=["student"],
        grade="10",
    )

    old_role, old_grade = await upsert_pseudonym_audit(db, "pseudo-1", identity)

    assert old_role == "student"
    assert old_grade == 9
    assert db.execute.await_count == 2
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_pseudonym_audit_first_login_returns_none_values():
    db = AsyncMock()
    first_result = MagicMock()
    first_result.fetchone.return_value = None
    db.execute = AsyncMock(side_effect=[first_result, MagicMock()])

    identity = NormalizedIdentity(
        external_id="ext-2",
        roles=["student"],
        grade="7",
    )

    old_role, old_grade = await upsert_pseudonym_audit(db, "pseudo-2", identity)

    assert old_role is None
    assert old_grade is None
    assert db.execute.await_count == 2
    db.commit.assert_awaited_once()
