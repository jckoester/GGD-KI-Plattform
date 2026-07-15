from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.auth.audit import get_primary_role, roles_were_removed, upsert_pseudonym_audit
from app.auth.base import NormalizedIdentity


def test_get_primary_role_prioritizes_teacher():
    assert get_primary_role(["teacher", "admin"]) == "teacher"
    assert get_primary_role(["student"]) == "student"
    assert get_primary_role(["admin"]) == "teacher"


# ── roles_were_removed (Sicherheits-Audit #11 „E") ──────────────────────────

def test_roles_were_removed_no_baseline():
    # Erster Login nach Rollout (keine gespeicherten roles) → keine Revocation.
    assert roles_were_removed(None, ["teacher", "admin"]) is False


def test_roles_were_removed_additive_role_dropped():
    assert roles_were_removed(["teacher", "admin"], ["teacher"]) is True


def test_roles_were_removed_review_dropped():
    assert roles_were_removed(["teacher", "review"], ["teacher"]) is True


def test_roles_were_removed_downgrade_teacher_to_student():
    assert roles_were_removed(["teacher"], ["student"]) is True


def test_roles_were_removed_unchanged():
    assert roles_were_removed(["teacher", "admin"], ["admin", "teacher"]) is False


def test_roles_were_removed_pure_addition():
    # Hochstufung: nur hinzugefügt → keine Revocation (Alt-Session nur unterprivilegiert).
    assert roles_were_removed(["teacher"], ["teacher", "admin"]) is False


# ── upsert_pseudonym_audit ──────────────────────────────────────────────────

def _capture_insert(db) -> str:
    """Gibt das kompilierte INSERT-Statement (2. execute-Aufruf) als SQL-Text zurück."""
    insert_stmt = db.execute.await_args_list[1].args[0]
    return str(insert_stmt.compile(dialect=postgresql.dialect()))


@pytest.mark.asyncio
async def test_upsert_pseudonym_audit_returns_old_values():
    db = AsyncMock()
    first_result = MagicMock()
    first_result.fetchone.return_value = SimpleNamespace(role="student", grade=9, roles=["student"])
    db.execute = AsyncMock(side_effect=[first_result, MagicMock()])

    identity = NormalizedIdentity(external_id="ext-1", roles=["student"], grade="10")

    old_role, old_grade = await upsert_pseudonym_audit(db, "pseudo-1", identity)

    assert old_role == "student"
    assert old_grade == 9
    assert db.execute.await_count == 2
    db.commit.assert_awaited_once()
    # Rollen unverändert → keine Revocation im INSERT.
    assert "revoked_all_before" not in _capture_insert(db)


@pytest.mark.asyncio
async def test_upsert_pseudonym_audit_first_login_returns_none_values():
    db = AsyncMock()
    first_result = MagicMock()
    first_result.fetchone.return_value = None
    db.execute = AsyncMock(side_effect=[first_result, MagicMock()])

    identity = NormalizedIdentity(external_id="ext-2", roles=["student"], grade="7")

    old_role, old_grade = await upsert_pseudonym_audit(db, "pseudo-2", identity)

    assert old_role is None
    assert old_grade is None
    assert db.execute.await_count == 2
    db.commit.assert_awaited_once()
    assert "revoked_all_before" not in _capture_insert(db)


@pytest.mark.asyncio
async def test_upsert_revokes_sessions_when_role_removed():
    db = AsyncMock()
    first_result = MagicMock()
    first_result.fetchone.return_value = SimpleNamespace(
        role="teacher", grade=None, roles=["teacher", "admin"]
    )
    db.execute = AsyncMock(side_effect=[first_result, MagicMock()])

    # admin entzogen → nur noch teacher.
    identity = NormalizedIdentity(external_id="ext-3", roles=["teacher"], grade=None)

    await upsert_pseudonym_audit(db, "pseudo-3", identity)

    # E: bei Rollen-Schrumpfung wird revoked_all_before im INSERT gesetzt.
    assert "revoked_all_before" in _capture_insert(db)


@pytest.mark.asyncio
async def test_upsert_no_revoke_on_pure_addition():
    db = AsyncMock()
    first_result = MagicMock()
    first_result.fetchone.return_value = SimpleNamespace(
        role="teacher", grade=None, roles=["teacher"]
    )
    db.execute = AsyncMock(side_effect=[first_result, MagicMock()])

    identity = NormalizedIdentity(external_id="ext-4", roles=["teacher", "admin"], grade=None)

    await upsert_pseudonym_audit(db, "pseudo-4", identity)

    assert "revoked_all_before" not in _capture_insert(db)
