"""Zustimmung zu einem KI-Programm (0.55, Päckchen AX Schritt 4).

Die Zustimmungsseite im Frontend (`/oauth/consent?anfrage=…`) fragt hier, **was** verbunden werden
soll, und meldet die Entscheidung. Den Rest — Code, Token, Verbindung — erledigt der Provider
(`app.mcp.oauth`).

- Nur eine **Browser-Sitzung** von Lehrkräften und Admins (F9). Ein Zugangstoken kommt nicht
  herein: `/oauth` steht nicht in `app.auth.scopes`, dort gilt deny-by-default.
- **Nicht in der Vorschau:** Dort sind die Rollen die einer Schüler:in, `require_any_role` sperrt.
- Ohne eingeschaltete Schnittstelle gibt es nichts zu bestätigen (`404`).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth.dependencies import require_any_role
from app.auth.jwt import JwtPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth", tags=["oauth"])

_LEHRKRAFT_ODER_ADMIN = require_any_role(["teacher", "admin"])


def _provider(request: Request):
    server = getattr(request.app.state, "mcp_server", None)
    provider = getattr(server, "_auth_server_provider", None) if server is not None else None
    if provider is None:
        raise HTTPException(status_code=404, detail="Die Schnittstelle für KI-Programme ist nicht eingeschaltet.")
    return provider


class Entscheidung(BaseModel):
    anfrage: str
    zulassen: bool


@router.get("/anfrage")
async def anfrage_zeigen(anfrage: str, request: Request,
                         user: JwtPayload = Depends(_LEHRKRAFT_ODER_ADMIN)) -> dict:
    """Programm, Rücksprung-Host, Berechtigung und Dauer — für die Zustimmungsseite."""
    from app.mcp.oauth import OAuthFehler

    try:
        return await _provider(request).anfrage_anzeigen(anfrage)
    except OAuthFehler as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/entscheidung")
async def entscheiden(eingabe: Entscheidung, request: Request,
                      user: JwtPayload = Depends(_LEHRKRAFT_ODER_ADMIN)) -> dict:
    """Zulassen → Rücksprung mit Code; ablehnen → Rücksprung mit `access_denied`.

    Die Adresse ist der beim Programm registrierte Rücksprung (das SDK prüft ihn bei
    `/authorize`), keine, die der Browser mitschickt.
    """
    from app.mcp.oauth import OAuthFehler

    provider = _provider(request)
    try:
        if not eingabe.zulassen:
            return {"weiter": provider.ablehnen(eingabe.anfrage)}
        # Kein Eintrag im Audit-Log, wie beim Anlegen eines Zugangstokens: Die Verbindung steht
        # im Profil, mit Datum, und lässt sich dort beenden.
        return {"weiter": await provider.code_ausstellen(eingabe.anfrage, user)}
    except OAuthFehler as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
