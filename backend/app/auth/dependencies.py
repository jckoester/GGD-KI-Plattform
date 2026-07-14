from collections.abc import Callable
from datetime import datetime, timezone
from functools import lru_cache
from uuid import UUID

from fastapi import Depends, HTTPException, Path, Request
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthAdapter
from app.auth.config import SsoConfig, load_auth_config
from app.auth.jwt import JwtPayload, JwtService
from app.auth.stepup import decode_stepup_token
from app.auth.stepup_nonce import consume_stepup_jti
from app.config import settings
from app.db.session import get_db


@lru_cache(maxsize=1)
def get_auth_adapter() -> AuthAdapter:
    auth_config = load_auth_config(settings.auth_config_path)
    group_role_map = auth_config.group_role_map_dict
    if auth_config.adapter == "oauth":
        from app.auth.adapters.oauth import OAuthAdapter

        return OAuthAdapter(auth_config.oauth, settings, group_role_map)
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


@lru_cache(maxsize=1)
def get_sso_config() -> SsoConfig:
    """Gibt die SSO-Konfiguration zurück (gecacht; Neustart bei Änderung)."""
    return load_auth_config(settings.auth_config_path).sso


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

    async def _guard(
        current_user: JwtPayload = Depends(get_current_user),
    ) -> JwtPayload:
        if role not in current_user.roles:
            raise HTTPException(status_code=403, detail="Keine Berechtigung")
        return current_user

    return _guard


def require_any_role(roles: list[str]) -> Callable:
    """Dependency-Factory: 403 wenn keine der `roles` in user.roles."""

    async def _guard(
        current_user: JwtPayload = Depends(get_current_user),
    ) -> JwtPayload:
        if not any(r in current_user.roles for r in roles):
            raise HTTPException(status_code=403, detail="Keine Berechtigung")
        return current_user

    return _guard


_STEPUP_REQUIRED = HTTPException(
    status_code=401,
    detail="Re-Authentifizierung erforderlich",
    headers={"X-Stepup-Required": "1"},
)


def require_fresh_stepup_for(action: str) -> Callable:
    """Dependency-Fabrik: verlangt ein frisches Step-up-Token, das an **genau diese**
    `action` und den Pfad-Parameter `request_id` (Ressource) gebunden ist, und löst es
    **einmalig** ein (Nonce). Schließt Cross-Action-Reuse und Replay (Audit #3 Teil B/C).

    Ersetzt das frühere, nur an `sub` gebundene `require_fresh_stepup`.
    """
    async def _guard(
        request: Request,
        request_id: UUID = Path(...),
        current_user: JwtPayload = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> JwtPayload:
        token = request.cookies.get("stepup")
        claims = decode_stepup_token(token, settings.jwt_secret) if token else None
        if (
            not claims
            or claims.get("sub") != current_user.sub
            or claims.get("action") != action
            or claims.get("resource_id") != str(request_id)
        ):
            raise _STEPUP_REQUIRED
        jti = claims.get("jti")
        exp = claims.get("exp")
        if not jti or not exp:
            raise _STEPUP_REQUIRED
        expires_at = datetime.fromtimestamp(int(exp), tz=timezone.utc)
        # Einmalverwendung: bereits eingelöst → Replay, ablehnen.
        if not await consume_stepup_jti(db, jti, expires_at):
            raise _STEPUP_REQUIRED
        return current_user

    return _guard
