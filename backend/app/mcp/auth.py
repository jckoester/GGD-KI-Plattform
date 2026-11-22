"""Anmeldung am MCP-Server: Zugangstoken → ``AccessToken`` des SDK → ``JwtPayload``.

Die Prüfung ist dieselbe wie bei REST-Anfragen mit Token (`app.auth.tokens.pruefe`): Hash,
Ablauf, Widerruf, ``revoked_all_before`` und die Rollen **frisch** aus dem Audit; dazu
``last_used_at``. Hinzu kommt nur der Scope: Ohne ``curriculum:read`` kein Zugang, auch nicht
mit ``context:read`` — ein KI-Programm soll gezielt diese eine Berechtigung bekommen (F3).

Eine Vorschau gibt es mit Token nicht; ``preview`` bleibt leer.
"""
from __future__ import annotations

from collections.abc import Callable

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import tokens
from app.auth.jwt import JwtPayload

SCOPE = "curriculum:read"


class ZugangstokenPruefer:
    """``TokenVerifier`` des SDK für persönliche Zugangstoken.

    ``sitzung`` ist eine Fabrik für Datenbanksitzungen (Vorgabe ``AsyncSessionLocal``), damit
    Tests ihre eigene Datenbank einsetzen können.
    """

    def __init__(self, sitzung: Callable[[], AsyncSession] | None = None):
        if sitzung is None:
            from app.db.session import AsyncSessionLocal

            sitzung = AsyncSessionLocal
        self._sitzung = sitzung

    async def verify_token(self, token: str) -> AccessToken | None:
        async with self._sitzung() as db:
            ergebnis = await tokens.pruefe(db, token)
        if ergebnis is None:
            return None
        zeile, principal = ergebnis
        if SCOPE not in (zeile.scopes or []):
            return None
        return AccessToken(
            token=token,
            client_id=principal.jti,  # „pat:<id>“ — in AX steht hier der OAuth-Client
            scopes=list(zeile.scopes),
            expires_at=principal.exp,
            subject=principal.sub,
            claims={"roles": principal.roles, "grade": principal.grade, "iat": principal.iat},
        )


def principal(zugang: AccessToken | None = None) -> JwtPayload:
    """Die Person hinter dem Aufruf, als ``JwtPayload`` wie bei REST-Anfragen.

    Ohne Argument aus dem Kontext des laufenden Werkzeugaufrufs. Fehlt die Anmeldung, ist
    das ein Fehler im Aufbau (die Middleware des SDK lässt ohne Token nichts durch).
    """
    zugang = zugang or get_access_token()
    if zugang is None or SCOPE not in zugang.scopes:
        raise PermissionError("MCP-Aufruf ohne gültigen Zugang")
    claims = zugang.claims or {}
    return JwtPayload(
        sub=zugang.subject,
        roles=list(claims.get("roles") or []),
        grade=claims.get("grade"),
        jti=zugang.client_id,
        iat=int(claims.get("iat") or 0),
        exp=int(zugang.expires_at or 0),
        token_scopes=list(zugang.scopes),
    )
