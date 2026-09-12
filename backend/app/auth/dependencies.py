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
from app.auth.scopes import pruefe_zugang
from app.auth.stepup import decode_stepup_token, ressource_erwartet
from app.auth.stepup_nonce import consume_stepup_jti
from app.config import settings
from app.db.session import get_db
from app.ratelimit.drossel import pruefe as drossel_pruefe


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
    """Der Principal — aus dem Session-Cookie oder aus einem Zugangstoken.

    Zwei Wege, ein Ergebnis: Alles dahinter (`require_role`, `require_group_teacher`, die
    Sichtbarkeitsfilter) arbeitet unverändert weiter. Der Unterschied steckt allein in
    `token_scopes` und wird **hier** ausgewertet, bevor irgendein Router etwas sieht —
    siehe `app.auth.scopes`.
    """
    token = request.cookies.get("session")
    if token:
        try:
            payload = jwt_service.verify(token)
        except JWTError:
            raise HTTPException(status_code=401, detail="Ungültiger Token")
        if await jwt_service.is_revoked(db, payload):
            raise HTTPException(status_code=401, detail="Token revoziert")
        return payload

    kopfzeile = request.headers.get("authorization") or ""
    if kopfzeile.lower().startswith("bearer "):
        from app.auth import tokens as token_modul

        ergebnis = await token_modul.pruefe(db, kopfzeile[7:].strip())
        if ergebnis is None:
            raise HTTPException(status_code=401, detail="Ungültiges Zugangstoken")
        zeile, payload = ergebnis
        # Vor dem Router, nicht in ihm: Ein Token, dessen Scope diesen Pfad nicht deckt,
        # kommt gar nicht erst bis zur Rechteprüfung.
        pruefe_zugang(payload.token_scopes or [], request.method, request.url.path)
        # Gedrosselt wird **je Token**, nicht je Person: Ein Mensch im Browser bremst
        # sich selbst, eine Sync-Schleife nicht — und ein eigener Zähler sorgt dafür,
        # dass ein durchdrehender Client seine Besitzerin nicht aus der Oberfläche
        # aussperrt. `planning` und `context` tragen selbst keine Drossel; für
        # Browser-Verkehr bleibt das bewusst so.
        drossel_pruefe("token", str(zeile.id), payload.roles)
        return payload

    raise HTTPException(status_code=401, detail="Nicht authentifiziert")


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


async def _stepup_pruefen(
    request: Request, action: str, resource_id: str, current_user: JwtPayload, db: AsyncSession
) -> JwtPayload:
    """Gemeinsamer Kern beider Guard-Formen: Claims prüfen und die Nonce einlösen."""
    token = request.cookies.get("stepup")
    claims = decode_stepup_token(token, settings.jwt_secret) if token else None
    if (
        not claims
        or claims.get("sub") != current_user.sub
        or claims.get("action") != action
        or (claims.get("resource_id") or "") != resource_id
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
        return await _stepup_pruefen(request, action, str(request_id), current_user, db)

    return _guard


def require_fresh_stepup_ohne_ressource(action: str) -> Callable:
    """Dieselbe Prüfung für Aktionen, die kein Gegenüber haben — etwa das **Anlegen**
    eines Zugangstokens: Die Ressource entsteht erst dadurch.

    Bewusst eine **zweite Fabrik** statt eines Schalters an der ersten: Der Unterschied
    liegt in der Signatur, nicht im Verhalten. Eine Fabrik mit `ressourcengebunden=False`
    müsste den Pfad-Parameter `request_id` je nach Argument deklarieren oder eben nicht —
    FastAPI liest die Signatur aber einmalig beim Registrieren, und ein optionaler
    `request_id` hieße: Wer ihn wegzulassen vergisst, bekommt still keine Bindung.

    Die Aktion muss in `STEPUP_AKTIONEN_OHNE_RESSOURCE` stehen. Sonst verlöre ein
    ressourcengebundener Guard hier unbemerkt seine Bindung.
    """
    if ressource_erwartet(action):
        raise ValueError(
            f"'{action}' ist ressourcengebunden — `require_fresh_stepup_for` verwenden "
            f"oder die Aktion in STEPUP_AKTIONEN_OHNE_RESSOURCE aufnehmen."
        )

    async def _guard(
        request: Request,
        current_user: JwtPayload = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> JwtPayload:
        return await _stepup_pruefen(request, action, "", current_user, db)

    return _guard
