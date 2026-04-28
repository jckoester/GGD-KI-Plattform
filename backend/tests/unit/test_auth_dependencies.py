import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock

from app.auth.dependencies import require_role, require_any_role
from app.auth.jwt import JwtPayload


def make_payload(roles: list[str]) -> JwtPayload:
    return JwtPayload(sub="pseudo", roles=roles, grade=None, jti="x", iat=0, exp=9999999999)


@pytest.mark.asyncio
async def test_require_role_grants_access():
    guard = require_role("admin")
    payload = make_payload(["teacher", "admin"])
    result = await guard(current_user=payload)
    assert result == payload


@pytest.mark.asyncio
async def test_require_role_denies_access():
    guard = require_role("admin")
    payload = make_payload(["teacher"])
    with pytest.raises(HTTPException) as exc:
        await guard(current_user=payload)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_any_role_grants_if_one_matches():
    guard = require_any_role(["statistics", "admin"])
    payload = make_payload(["teacher", "statistics"])
    result = await guard(current_user=payload)
    assert result == payload


@pytest.mark.asyncio
async def test_require_any_role_denies_if_none_match():
    guard = require_any_role(["statistics", "admin"])
    payload = make_payload(["teacher"])
    with pytest.raises(HTTPException) as exc:
        await guard(current_user=payload)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_any_role_with_budget_role():
    guard = require_any_role(["budget", "admin"])
    payload = make_payload(["budget"])
    result = await guard(current_user=payload)
    assert result == payload


@pytest.mark.asyncio
async def test_require_any_role_with_budget_and_admin_combination():
    guard = require_any_role(["budget", "admin"])
    payload = make_payload(["teacher", "budget"])
    result = await guard(current_user=payload)
    assert result == payload
