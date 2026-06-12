"""Unit-Tests für app.planning.permissions."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.planning.permissions import require_group_teacher


def _mock_user(sub: str = "teacher1", roles: list[str] | None = None) -> MagicMock:
    user = MagicMock()
    user.sub = sub
    user.roles = roles or ["teacher"]
    return user


def _mock_group(gid: int = 1, gtype: str = "teaching_group") -> MagicMock:
    g = MagicMock()
    g.id = gid
    g.type = gtype
    return g


def _mock_membership(role: str | None = "teacher") -> MagicMock | None:
    if role is None:
        return None
    m = MagicMock()
    m.role_in_group = role
    return m


@pytest.mark.asyncio
async def test_lehrkraft_der_gruppe_hat_zugriff():
    db = AsyncMock()
    db.get = AsyncMock(return_value=_mock_group())
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: _mock_membership("teacher")))

    group = await require_group_teacher(1, _mock_user(), db)
    assert group.id == 1


@pytest.mark.asyncio
async def test_gruppe_nicht_gefunden_ergibt_404():
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await require_group_teacher(1, _mock_user(), db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_falsche_gruppe_type_ergibt_404():
    db = AsyncMock()
    db.get = AsyncMock(return_value=_mock_group(gtype="activity_group"))

    with pytest.raises(HTTPException) as exc:
        await require_group_teacher(1, _mock_user(), db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_nicht_mitglied_ergibt_403():
    db = AsyncMock()
    db.get = AsyncMock(return_value=_mock_group())
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

    with pytest.raises(HTTPException) as exc:
        await require_group_teacher(1, _mock_user(), db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_schueler_der_gruppe_ergibt_403():
    db = AsyncMock()
    db.get = AsyncMock(return_value=_mock_group())
    # DB gibt None zurück (kein Eintrag mit role_in_group='teacher')
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

    user = _mock_user(roles=["student"])
    with pytest.raises(HTTPException) as exc:
        await require_group_teacher(1, user, db)
    assert exc.value.status_code == 403
