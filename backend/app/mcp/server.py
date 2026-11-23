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

from app.mcp.auth import SCOPE

logger = logging.getLogger(__name__)

PFAD = "/mcp"

ANLEITUNG = (
    "Lesender Zugang zu einer Schulplattform: Curricula der Fachschaften (veröffentlicht und "
    "Entwürfe), die Bildungspläne Baden-Württemberg 2016 mit Kompetenzen und Leitperspektiven, "
    "und die Leitlinien der Schule. Schreiben ist über diese Schnittstelle nicht möglich."
)


def aussteller(oeffentliche_url: str) -> str:
    """Der OAuth-Issuer: die öffentliche Adresse ohne das letzte `/mcp`.

    `https://ki.schule.de/api/mcp` → `https://ki.schule.de/api`. Die Endpunkte des
    Autorisierungsservers liegen dann unter `/api/authorize` usw. und laufen durch dieselbe
    Proxy-Regel wie die übrige API (`/api/…` → Backend `/…`). Mit der Domain als Issuer
    landeten sie im Frontend.
    """
    teile = urlsplit(oeffentliche_url)
    pfad = teile.path.rstrip("/")
    return f"{teile.scheme}://{teile.netloc}{pfad[: -len(PFAD)] if pfad.endswith(PFAD) else pfad}"


def baue_server(sitzung: Callable[[], AsyncSession] | None = None, *, oeffentliche_url: str,
                geheimnis: str, frontend: str) -> MCPServer:
    """Der MCP-Server mit Anmeldung per OAuth (AX) und per Zugangstoken (AW).

    Mit `auth_server_provider` baut das SDK den Token-Prüfer selbst aus
    `Provider.load_access_token`; der nimmt beide Token-Arten an.
    """
    from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions

    from app.mcp.oauth import Provider
    from app.version import plattformversion

    return MCPServer(
        name="ggd-ki-plattform",
        version=plattformversion(),
        instructions=ANLEITUNG,
        auth_server_provider=Provider(oeffentliche_url=oeffentliche_url, geheimnis=geheimnis, sitzung=sitzung,
                                      zustimmungsseite=f"{frontend.rstrip('/')}/oauth/consent"),
        auth=AuthSettings(
            issuer_url=aussteller(oeffentliche_url),
            resource_server_url=oeffentliche_url,
            required_scopes=[SCOPE],
            # Nur Token für genau diesen Server (RFC 8707). Der Provider setzt `resource` auf jeden
            # Zugriff, auch auf Zugangstoken aus AW.
            validate_token_resource=True,
            # Offene Registrierung (F12): Claude braucht sie. Schutz: Redirect-Regel im Provider,
            # Drossel je IP, Zustimmung der Lehrkraft, Aufräumen nach 30 Tagen.
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]),
            revocation_options=RevocationOptions(enabled=True),
        ),
    )


def transportschutz(oeffentliche_url: str) -> TransportSecuritySettings:
    """Nur Host und Origin der öffentlichen Adresse (Schutz vor DNS-Rebinding im SDK)."""
    teile = urlsplit(oeffentliche_url)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[teile.netloc],
        allowed_origins=[f"{teile.scheme}://{teile.netloc}"],
    )


def _schluessel_token(scope) -> str | None:
    kopf = dict(scope.get("headers") or []).get(b"authorization", b"")
    return hashlib.sha256(kopf).hexdigest() if kopf else None


def _schluessel_ip(scope) -> str | None:
    from starlette.requests import Request

    from app.config import settings
    from app.core.client_ip import client_ip

    return client_ip(Request(scope), settings.trusted_proxies)


class _Gedrosselt:
    """ASGI-Hülle: Drossel vor dem SDK, gezählt je POST.

    - `/mcp`: Eimer `mcp` je Token (F5).
    - `/register`, `/token`, `/authorize`, `/revoke`: Eimer `oauth` je Client-IP — registrieren
      kann jede:r, ohne Drossel wäre das eine offene Schreibtür.

    Eine Klasse, keine Funktion: Starlette nimmt eine Funktion als Endpunkt (Request →
    Response, nur GET), eine Instanz mit ``__call__`` dagegen als ASGI-App.
    """

    def __init__(self, innen, eimer: str = "mcp", schluessel=_schluessel_token):
        self.innen, self.eimer, self.schluessel = innen, eimer, schluessel

    async def __call__(self, scope, receive, send):
        from app.ratelimit.drossel import pruefe as drossel_pruefe

        if scope["type"] == "http" and scope["method"] == "POST":
            if wer := self.schluessel(scope):
                try:
                    drossel_pruefe(self.eimer, wer, [])
                except HTTPException as e:
                    koerper = json.dumps({"detail": e.detail}).encode()
                    await send({"type": "http.response.start", "status": e.status_code, "headers": [
                        (b"content-type", b"application/json"),
                        *((k.lower().encode(), v.encode()) for k, v in (e.headers or {}).items())]})
                    await send({"type": "http.response.body", "body": koerper})
                    return
        await self.innen(scope, receive, send)


def einhaengen(app: FastAPI, *, aktiv: bool, oeffentliche_url: str,
               sitzung: Callable[[], AsyncSession] | None = None, geheimnis: str | None = None,
               frontend: str | None = None) -> MCPServer | None:
    """Hängt den Server an `app`, wenn er eingeschaltet ist. Gibt ihn zurück (für den
    Lebenszyklus), sonst `None`."""
    if not aktiv:
        return None
    teile = urlsplit(oeffentliche_url)
    if teile.scheme not in ("https", "http") or not teile.path.rstrip("/").endswith(PFAD):
        logger.error("MCP_AKTIV ist gesetzt, aber MCP_OEFFENTLICHE_URL fehlt, ist keine http(s)-Adresse "
                     "oder endet nicht auf /mcp — die Schnittstelle für KI-Abos bleibt aus.")
        return None
    if teile.scheme == "http" and teile.hostname not in ("localhost", "127.0.0.1", "::1"):
        logger.error("MCP_OEFFENTLICHE_URL muss https:// sein (OAuth verlangt es; http nur für localhost) "
                     "— die Schnittstelle für KI-Abos bleibt aus.")
        return None
    from app.config import settings

    server = baue_server(sitzung, oeffentliche_url=oeffentliche_url, geheimnis=geheimnis or settings.jwt_secret,
                         frontend=frontend or settings.frontend_origin)
    from app.mcp import werkzeuge

    werkzeuge.registrieren(server, sitzung)
    innen = server.streamable_http_app(streamable_http_path=PFAD, stateless_http=True,
                                       json_response=True,
                                       transport_security=transportschutz(oeffentliche_url))
    app.router.routes.append(Route(PFAD, endpoint=_Gedrosselt(innen), methods=None))
    # Die übrigen Routen der Unter-App: OAuth-Endpunkte und die Metadaten (RFC 8414, RFC 9728).
    # Sie brauchen keine Anmeldung und keine Host-Prüfung des SDK; die Host-Liste der App gilt.
    for route in innen.routes:
        pfad = getattr(route, "path", None)
        if pfad == PFAD:
            continue
        if pfad == "/.well-known/oauth-authorization-server":
            # RFC 8414 §3: Bei einem Issuer mit Pfad (`…/api`) fragt der Client an der Wurzel mit
            # angehängtem Pfad; nginx reicht `/.well-known/oauth-…` ungekürzt durch.
            if pfad_issuer := urlsplit(aussteller(oeffentliche_url)).path:
                app.router.routes.append(Route(pfad + pfad_issuer, endpoint=route.endpoint, methods=route.methods))
            app.router.routes.append(route)
        elif pfad.startswith("/.well-known/"):
            app.router.routes.append(route)
        else:
            app.router.routes.append(Route(pfad, endpoint=_Gedrosselt(route.app, "oauth", _schluessel_ip),
                                           methods=None))
    logger.info("Schnittstelle für KI-Abos (MCP) unter %s, OAuth-Issuer %s",
                oeffentliche_url, aussteller(oeffentliche_url))
    return server


@asynccontextmanager
async def lebenszyklus(server: MCPServer | None):
    """Der Session-Manager des SDK läuft im `lifespan` der App mit."""
    if server is None:
        yield
        return
    async with server.session_manager.run():
        yield
