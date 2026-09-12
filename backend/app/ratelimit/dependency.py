"""FastAPI-Dependency für das Ratelimiting (Sicherheits-Audit #2)."""
from fastapi import Depends

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.ratelimit.drossel import pruefe


def rate_limit(bucket: str):
    """Dependency-Fabrik: drosselt pro Nutzer:in (JWT `sub`) nach `rate_limits.yaml`.

    Gibt die `JwtPayload` zurück → **Drop-in-Ersatz** für `get_current_user`. 429 mit
    `Retry-After`, wenn das Fenster-Limit überschritten ist.
    """
    async def _dep(current_user: JwtPayload = Depends(get_current_user)) -> JwtPayload:
        pruefe(bucket, current_user.sub, current_user.roles)
        return current_user

    return _dep
