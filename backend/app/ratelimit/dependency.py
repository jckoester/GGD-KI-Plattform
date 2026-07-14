"""FastAPI-Dependency für das Ratelimiting (Sicherheits-Audit #2)."""
from fastapi import Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.ratelimit import config, store


def rate_limit(bucket: str):
    """Dependency-Fabrik: drosselt pro Nutzer:in (JWT `sub`) nach `rate_limits.yaml`.

    Gibt die `JwtPayload` zurück → **Drop-in-Ersatz** für `get_current_user`. 429 mit
    `Retry-After`, wenn das Fenster-Limit überschritten ist.
    """
    async def _dep(current_user: JwtPayload = Depends(get_current_user)) -> JwtPayload:
        limit, window = config.resolve(bucket, current_user.roles)
        ok, retry_after = store.allow(bucket, current_user.sub, limit, window)
        if not ok:
            raise HTTPException(
                status_code=429,
                detail="Zu viele Anfragen. Bitte kurz warten und erneut versuchen.",
                headers={"Retry-After": str(int(retry_after) + 1)},
            )
        return current_user

    return _dep
