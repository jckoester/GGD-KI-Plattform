import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from jose import JWTError

from app.auth.audit import get_primary_role, upsert_pseudonym_audit
from app.auth.base import AuthAdapter, LoginChallenge
from app.auth.config import load_auth_config
from app.auth.dependencies import get_auth_adapter, get_current_user, get_jwt_service
from app.auth.group_sync import sync_groups
from app.auth.jwt import JwtPayload, JwtService
from app.auth.pseudonym import pseudonymize
from app.auth.stepup import (
    STEPUP_TTL_SECONDS,
    auth_time_is_fresh,
    is_stepup_state,
    issue_stepup_token,
    parse_stepup_state,
    sign_stepup_state,
)
from app.config import settings
from app.db.session import get_db
from app.litellm.user_service import ensure_litellm_team_membership, ensure_litellm_user
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/login")
async def get_login_challenge_v1(
    adapter: AuthAdapter = Depends(get_auth_adapter),
) -> LoginChallenge:
    return await adapter.get_login_challenge()


@router.get("/login-challenge")
async def login_challenge(
    adapter: AuthAdapter = Depends(get_auth_adapter),
) -> LoginChallenge:
    return await adapter.get_login_challenge()


@router.get("/callback")
async def auth_callback(
    request: Request,
    response: Response,
    adapter: AuthAdapter = Depends(get_auth_adapter),
    db: AsyncSession = Depends(get_db),
    jwt_service: JwtService = Depends(get_jwt_service),
) -> RedirectResponse | dict:
    if adapter.mode != "redirect":
        raise HTTPException(status_code=405, detail="Adapter unterstützt kein OIDC-Callback")
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if code is None or state is None:
        raise HTTPException(status_code=400, detail="Missing code or state")
    # Step-up-Rückkehr nutzt denselben redirect_uri; am State-Präfix unterscheidbar.
    if is_stepup_state(state):
        return await _handle_stepup_callback(
            request, db, jwt_service, adapter, code, state
        )
    try:
        identity = await adapter.exchange_code(code, state)
    except Exception:
        raise HTTPException(status_code=401, detail="Authentifizierung fehlgeschlagen")
    pseudonym = pseudonymize(identity.external_id, settings.school_secret)
    old_role, old_grade = await upsert_pseudonym_audit(db, pseudonym, identity)
    await ensure_litellm_user(
        db,
        pseudonym,
        identity.roles,
        identity.grade,
        old_role=old_role,
        old_grade=old_grade,
    )
    await ensure_litellm_team_membership(pseudonym, identity.roles, identity.grade)
    
    # Sync SSO-Gruppen
    auth_config = load_auth_config(settings.auth_config_path)
    primary_role = get_primary_role(identity.roles)
    await sync_groups(
        db=db,
        pseudonym=pseudonym,
        sso_groups=identity.sso_groups,
        primary_role=primary_role,
        patterns=auth_config.sso.groups,
        aliases=auth_config.sso.subject_aliases,
    )
    
    token, _ = jwt_service.issue(
        pseudonym, identity.roles, identity.grade, identity.display_name
    )
    secure = settings.environment != "development"
    redirect = RedirectResponse(url="/welcome", status_code=303)
    redirect.set_cookie(
        "session", token,
        httponly=True, secure=secure, samesite="lax",
        max_age=30 * 24 * 3600, path="/",
    )
    return redirect


# ===== Step-up-Re-Authentifizierung (Phase 12, Schritt 5) =====

def _safe_return_to(return_to: str) -> str:
    """Schützt vor Open-Redirect: nur lokale Pfade zulassen."""
    if not return_to.startswith("/") or return_to.startswith("//"):
        return "/welcome"
    return return_to


async def _handle_stepup_callback(
    request: Request,
    db: AsyncSession,
    jwt_service: JwtService,
    adapter: AuthAdapter,
    code: str,
    state: str,
) -> RedirectResponse:
    # Step-up frischt eine *laufende* Sitzung auf — Session muss gültig bestehen.
    session_token = request.cookies.get("session")
    if not session_token:
        raise HTTPException(status_code=401, detail="Keine Sitzung")
    try:
        current = jwt_service.verify(session_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Ungültige Sitzung")
    if await jwt_service.is_revoked(db, current):
        raise HTTPException(status_code=401, detail="Sitzung revoziert")

    parsed = parse_stepup_state(settings.school_secret, state)
    if parsed is None:
        raise HTTPException(status_code=400, detail="Ungültiger Step-up-State")
    state_sub, return_to = parsed
    if state_sub != current.sub:
        raise HTTPException(status_code=401, detail="Step-up gehört zu anderem Nutzer")

    try:
        fresh = await adapter.exchange_code_fresh(code, state)
    except Exception:
        raise HTTPException(status_code=401, detail="Re-Authentifizierung fehlgeschlagen")

    # Frische-Sicherheitsnetz: honoriert der IdP prompt=login nicht, ist auth_time alt.
    now_ts = int(datetime.now(timezone.utc).timestamp())
    if not auth_time_is_fresh(fresh.auth_time, now_ts):
        raise HTTPException(status_code=401, detail="Re-Authentifizierung nicht frisch genug")
    if pseudonymize(fresh.identity.external_id, settings.school_secret) != current.sub:
        raise HTTPException(status_code=401, detail="Re-Authentifizierung als anderer Nutzer")

    token = issue_stepup_token(settings.jwt_secret, current.sub)
    secure = settings.environment != "development"
    redirect = RedirectResponse(url=_safe_return_to(return_to), status_code=303)
    redirect.set_cookie(
        "stepup", token,
        httponly=True, secure=secure, samesite="lax",
        max_age=STEPUP_TTL_SECONDS, path="/",
    )
    return redirect


@router.get("/step-up")
async def step_up_challenge(
    return_to: str = "/welcome",
    current_user: JwtPayload = Depends(get_current_user),
    adapter: AuthAdapter = Depends(get_auth_adapter),
) -> dict:
    """Beschreibt, wie sich der:die Nutzer:in frisch authentifiziert.

    direct: Frontend zeigt Passwort-Dialog (→ POST /step-up).
    redirect: Frontend leitet auf die zurückgegebene URL (prompt=login) weiter.
    """
    if adapter.mode == "direct":
        return {"mode": "direct"}
    nonce = secrets.token_urlsafe(16)
    state = sign_stepup_state(
        settings.school_secret, current_user.sub, _safe_return_to(return_to), nonce
    )
    challenge = await adapter.get_stepup_challenge(state)
    return {"mode": "redirect", "redirect_url": challenge.redirect_url}


@router.post("/step-up")
async def step_up_direct(
    request: Request,
    response: Response,
    current_user: JwtPayload = Depends(get_current_user),
    adapter: AuthAdapter = Depends(get_auth_adapter),
) -> dict:
    """Direct-Adapter: Passwort-Re-Entry → frisches Step-up-Token (`stepup`-Cookie)."""
    if adapter.mode != "direct":
        raise HTTPException(status_code=405, detail="Adapter unterstützt kein direktes Step-up")
    body = await request.json()
    username = body.get("username")
    password = body.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Missing username or password")
    identity = await adapter.authenticate_direct(username, password)
    if identity is None:
        raise HTTPException(status_code=401, detail="Re-Authentifizierung fehlgeschlagen")
    if pseudonymize(identity.external_id, settings.school_secret) != current_user.sub:
        raise HTTPException(status_code=401, detail="Re-Authentifizierung als anderer Nutzer")
    token = issue_stepup_token(settings.jwt_secret, current_user.sub)
    secure = settings.environment != "development"
    response.set_cookie(
        "stepup", token,
        httponly=True, secure=secure, samesite="lax",
        max_age=STEPUP_TTL_SECONDS, path="/",
    )
    return {"ok": True}


@router.post("/login")
async def login_direct(
    request: Request,
    response: Response,
    adapter: AuthAdapter = Depends(get_auth_adapter),
    db: AsyncSession = Depends(get_db),
    jwt_service: JwtService = Depends(get_jwt_service),
) -> dict:
    if adapter.mode != "direct":
        raise HTTPException(status_code=405, detail="Adapter unterstützt kein direktes Login")
    body = await request.json()
    username = body.get("username")
    password = body.get("password")
    if username is None or password is None:
        raise HTTPException(status_code=400, detail="Missing username or password")
    identity = await adapter.authenticate_direct(username, password)
    if identity is None:
        raise HTTPException(status_code=401, detail="Falsche Anmeldedaten")
    pseudonym = pseudonymize(identity.external_id, settings.school_secret)
    old_role, old_grade = await upsert_pseudonym_audit(db, pseudonym, identity)
    await ensure_litellm_user(
        db,
        pseudonym,
        identity.roles,
        identity.grade,
        old_role=old_role,
        old_grade=old_grade,
    )
    await ensure_litellm_team_membership(pseudonym, identity.roles, identity.grade)
    
    # Sync SSO-Gruppen
    auth_config = load_auth_config(settings.auth_config_path)
    primary_role = get_primary_role(identity.roles)
    await sync_groups(
        db=db,
        pseudonym=pseudonym,
        sso_groups=identity.sso_groups,
        primary_role=primary_role,
        patterns=auth_config.sso.groups,
        aliases=auth_config.sso.subject_aliases,
    )
    
    token, _ = jwt_service.issue(
        pseudonym, identity.roles, identity.grade, identity.display_name
    )
    secure = settings.environment != "development"
    response.set_cookie(
        "session", token,
        httponly=True, secure=secure, samesite="lax",
        max_age=30 * 24 * 3600, path="/",
    )
    return {
        "ok": True,
        "display_name": identity.display_name,
        "username": username,
    }


@router.post("/logout")
async def logout(
    response: Response,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    jwt_service: JwtService = Depends(get_jwt_service),
) -> dict:
    await jwt_service.revoke(
        db,
        jti=current_user.jti,
        pseudonym=current_user.sub,
        expires_at=datetime.fromtimestamp(current_user.exp, timezone.utc),
        reason="user_logout",
    )
    response.delete_cookie("session", httponly=True, samesite="lax")
    return {"ok": True}


@router.get("/me")
async def get_me(current_user: JwtPayload = Depends(get_current_user)) -> dict:
    return {
        "pseudonym": current_user.sub,
        "roles": current_user.roles,
        "grade": current_user.grade,
        "display_name": current_user.display_name,
    }
