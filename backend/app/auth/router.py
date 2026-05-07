from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.auth.audit import get_primary_role, upsert_pseudonym_audit
from app.auth.base import AuthAdapter, LoginChallenge
from app.auth.config import load_auth_config
from app.auth.dependencies import get_auth_adapter, get_current_user, get_jwt_service
from app.auth.group_sync import sync_groups
from app.auth.jwt import JwtPayload, JwtService
from app.auth.pseudonym import pseudonymize
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
) -> dict:
    if adapter.mode != "redirect":
        raise HTTPException(status_code=405, detail="Adapter unterstützt kein OIDC-Callback")
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if code is None or state is None:
        raise HTTPException(status_code=400, detail="Missing code or state")
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
    
    token, _ = jwt_service.issue(pseudonym, identity.roles, identity.grade)
    secure = settings.environment != "development"
    response.set_cookie(
        "session", token,
        httponly=True, secure=secure, samesite="lax",
        max_age=30 * 24 * 3600, path="/",
    )
    return {
        "ok": True,
        "display_name": identity.display_name,
    }


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
    
    token, _ = jwt_service.issue(pseudonym, identity.roles, identity.grade)
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
    }
