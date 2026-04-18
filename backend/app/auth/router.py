from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.auth.base import AuthAdapter, LoginChallenge, NormalizedIdentity
from app.auth.dependencies import get_auth_adapter

router = APIRouter()


@router.get("/login")
async def get_login_challenge(
    adapter: AuthAdapter = Depends(get_auth_adapter),
) -> LoginChallenge:
    return await adapter.get_login_challenge()


@router.get("/callback")
async def auth_callback(
    request: Request,
    adapter: AuthAdapter = Depends(get_auth_adapter),
) -> JSONResponse:
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if code is None or state is None:
        raise HTTPException(status_code=400, detail="Missing code or state")
    raise HTTPException(status_code=501, detail="Schritt 1c + 1d: Pseudonymisierung + JWT noch nicht implementiert")


@router.post("/login")
async def login_direct(
    request: Request,
    adapter: AuthAdapter = Depends(get_auth_adapter),
) -> JSONResponse:
    body = await request.json()
    username = body.get("username")
    password = body.get("password")
    if username is None or password is None:
        raise HTTPException(status_code=400, detail="Missing username or password")
    raise HTTPException(status_code=501, detail="Schritt 1c + 1d: Pseudonymisierung + JWT noch nicht implementiert")


@router.post("/logout")
async def logout(
    response: Response,
) -> JSONResponse:
    raise HTTPException(status_code=501, detail="Schritt 1c: JWT-Revokation noch nicht implementiert")


@router.get("/me")
async def get_me(
    request: Request,
) -> JSONResponse:
    raise HTTPException(status_code=501, detail="Schritt 1c: JWT-Validierung noch nicht implementiert")
