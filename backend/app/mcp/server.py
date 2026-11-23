"""Der MCP-Server und wie er in die FastAPI-App kommt (0.54, Päckchen AW Schritt 3).

**Einhängen.** FastAPI sieht kein `/api` (nginx schneidet es ab): intern `/mcp`, öffentlich
`MCP_OEFFENTLICHE_URL`, etwa `https://ki.schule.de/api/mcp`. Der Server hängt als **eine
Route** `/mcp` an der App, nicht als `Mount`: Ein Mount auf `/mcp` beantwortet `/mcp` ohne
Schrägstrich mit einer Weiterleitung auf `/mcp/` — hinter dem Proxy ohne `/api`, also ins
Leere.

**Zustandslos, JSON.** Jede Nachricht ist eine eigene HTTP-Anfrage mit JSON-Antwort, ohne
Sitzung im Server und ohne SSE-Strom (`stateless_http`, `json_response`). Die Werkzeuge lesen
nur; serverseitige Nachrichten an den Client braucht es nicht. So überlebt eine Verbindung
auch einen Neustart des Backends.

**Schutz.**
- Anmeldung: `ZugangstokenPruefer` (Scope `curriculum:read` Pflicht) über die Middleware des
  SDK; ohne gültiges Token `401`.
- Host und Origin: nur die der öffentlichen Adresse (Schutz vor DNS-Rebinding im SDK).
- Drossel `mcp` je Token (F5), gezählt je POST, also je Nachricht.
- Aus ist aus: Ohne `MCP_AKTIV` gibt es die Route nicht (`404`).
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from mcp.server import MCPServer
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.routing import Route

from app.mcp.auth import SCOPE, ZugangstokenPruefer

logger = logging.getLogger(__name__)

PFAD = "/mcp"

ANLEITUNG = (
    "Lesender Zugang zu einer Schulplattform: Curricula der Fachschaften (veröffentlicht und "
    "Entwürfe), die Bildungspläne Baden-Württemberg 2016 mit Kompetenzen und Leitperspektiven, "
    "und die Leitlinien der Schule. Schreiben ist über diese Schnittstelle nicht möglich."
)


def baue_server(pruefer: ZugangstokenPruefer | None = None, *, oeffentliche_url: str) -> MCPServer:
    """Der MCP-Server mit Anmeldung. Werkzeuge registriert `app.mcp.werkzeuge` (Schritt 4)."""
    from app.version import plattformversion

    teile = urlsplit(oeffentliche_url)
    ursprung = f"{teile.scheme}://{teile.netloc}"
    return MCPServer(
        name="ggd-ki-plattform",
        version=plattformversion(),
        instructions=ANLEITUNG,
        token_verifier=pruefer or ZugangstokenPruefer(),
        # In AW nur Ressourcenserver ohne veröffentlichte OAuth-Metadaten
        # (`resource_server_url=None`): Ein Client soll nicht nach einer Anmeldung suchen, die es
        # erst mit AX gibt. `issuer_url` verlangt das SDK trotzdem.
        auth=AuthSettings(issuer_url=ursprung, resource_server_url=None, required_scopes=[SCOPE]),
    )


def transportschutz(oeffentliche_url: str) -> TransportSecuritySettings:
    """Nur Host und Origin der öffentlichen Adresse (Schutz vor DNS-Rebinding im SDK)."""
    teile = urlsplit(oeffentliche_url)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[teile.netloc],
        allowed_origins=[f"{teile.scheme}://{teile.netloc}"],
    )


class _Gedrosselt:
    """ASGI-Hülle: Drossel `mcp` je Token, bevor das SDK die Nachricht liest.

    Eine Klasse, keine Funktion: Starlette nimmt eine Funktion als Endpunkt (Request →
    Response, nur GET), eine Instanz mit ``__call__`` dagegen als ASGI-App.
    """

    def __init__(self, innen):
        self.innen = innen

    async def __call__(self, scope, receive, send):
        from app.ratelimit.drossel import pruefe as drossel_pruefe

        if scope["type"] == "http" and scope["method"] == "POST":
            kopf = dict(scope.get("headers") or []).get(b"authorization", b"")
            if kopf:
                try:
                    drossel_pruefe("mcp", hashlib.sha256(kopf).hexdigest(), [])
                except HTTPException as e:
                    koerper = json.dumps({"detail": e.detail}).encode()
                    await send({"type": "http.response.start", "status": e.status_code, "headers": [
                        (b"content-type", b"application/json"),
                        *((k.lower().encode(), v.encode()) for k, v in (e.headers or {}).items())]})
                    await send({"type": "http.response.body", "body": koerper})
                    return
        await self.innen(scope, receive, send)


def einhaengen(app: FastAPI, *, aktiv: bool, oeffentliche_url: str,
               sitzung: Callable[[], AsyncSession] | None = None) -> MCPServer | None:
    """Hängt den Server an `app`, wenn er eingeschaltet ist. Gibt ihn zurück (für den
    Lebenszyklus), sonst `None`."""
    if not aktiv:
        return None
    if not oeffentliche_url.startswith(("https://", "http://")):
        logger.error("MCP_AKTIV ist gesetzt, aber MCP_OEFFENTLICHE_URL fehlt oder ist keine "
                     "http(s)-Adresse — die Schnittstelle für KI-Abos bleibt aus.")
        return None
    server = baue_server(ZugangstokenPruefer(sitzung), oeffentliche_url=oeffentliche_url)
    from app.mcp import werkzeuge

    werkzeuge.registrieren(server, sitzung)
    innen = server.streamable_http_app(streamable_http_path=PFAD, stateless_http=True,
                                       json_response=True,
                                       transport_security=transportschutz(oeffentliche_url))
    app.router.routes.append(Route(PFAD, endpoint=_Gedrosselt(innen), methods=None))
    logger.info("Schnittstelle für KI-Abos (MCP) unter %s", oeffentliche_url)
    return server


@asynccontextmanager
async def lebenszyklus(server: MCPServer | None):
    """Der Session-Manager des SDK läuft im `lifespan` der App mit."""
    if server is None:
        yield
        return
    async with server.session_manager.run():
        yield
