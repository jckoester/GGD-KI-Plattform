from collections.abc import Callable
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthAdapter
from app.auth.config import load_auth_config
from app.auth.jwt import JwtPayload, JwtService
from app.config import settings
from app.db.session import get_db


@lru_cache(maxsize=1)
def get_auth_adapter() -> AuthAdapter:
    auth_config = load_auth_config(settings.auth_config_path)
    group_role_map = auth_config.group_role_map_dict
    if auth_config.adapter == "iserv":
        from app.auth.adapters.iserv import IServAdapter
        return IServAdapter(auth_config.iserv, settings, group_role_map)
    elif auth_config.adapter == "yaml_test":
        from app.auth.adapters.yaml_test import YamlTestAdapter
        return YamlTestAdapter(auth_config.yaml_test, group_role_map)
    raise ValueError(f"Unbekannter Adapter: {auth_config.adapter}")


@lru_cache(maxsize=1)
def get_jwt_service() -> JwtService:
    return JwtService(
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    jwt_service: JwtService = Depends(get_jwt_service),
) -> JwtPayload:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Nicht authentifiziert")
    try:
        payload = jwt_service.verify(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Ungültiger Token")
    if await jwt_service.is_revoked(db, payload):
        raise HTTPException(status_code=401, detail="Token revoziert")
    return payload


def require_role(role: str) -> Callable:
    """Dependency-Factory: 403 wenn `role` nicht in user.roles."""
    async def _guard(current_user: JwtPayload = Depends(get_current_user)) -> JwtPayload:
        if role not in current_user.roles:
            raise HTTPException(status_code=403, detail="Keine Berechtigung")
        return current_user
    return _guard


def require_any_role(roles: list[str]) -> Callable:
    """Dependency-Factory: 403 wenn keine der `roles` in user.roles."""
    async def _guard(current_user: JwtPayload = Depends(get_current_user)) -> JwtPayload:
        if not any(r in current_user.roles for r in roles):
            raise HTTPException(status_code=403, detail="Keine Berechtigung")
        return current_user
    return _guard
