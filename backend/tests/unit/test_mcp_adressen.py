"""Adressen der Schnittstelle für KI-Abos (0.55, Päckchen AX Schritt 3): Issuer, Pflicht zu https
und zu `/mcp` am Ende."""
import pytest
from fastapi import FastAPI

from app.mcp.server import aussteller, einhaengen


@pytest.mark.parametrize("url, issuer", [
    ("https://ki.schule.de/api/mcp", "https://ki.schule.de/api"),
    ("https://ki.schule.de/api/mcp/", "https://ki.schule.de/api"),
    ("https://schule.de/ki/api/mcp", "https://schule.de/ki/api"),
    ("http://localhost:8000/mcp", "http://localhost:8000"),
])
def test_issuer_ist_die_adresse_ohne_mcp(url, issuer):
    assert aussteller(url) == issuer


@pytest.mark.parametrize("url", [
    "", "ki.schule.de/api/mcp", "https://ki.schule.de/api", "http://ki.schule.de/api/mcp",
])
def test_unbrauchbare_adresse_laesst_die_schnittstelle_aus(url):
    app = FastAPI()
    assert einhaengen(app, aktiv=True, oeffentliche_url=url, geheimnis="x") is None
    assert not [r for r in app.router.routes if getattr(r, "path", "") == "/mcp"]


def test_routen_fuer_issuer_mit_pfad():
    app = FastAPI()
    assert einhaengen(app, aktiv=True, oeffentliche_url="https://ki.schule.de/api/mcp", geheimnis="x")
    pfade = {getattr(r, "path", "") for r in app.router.routes}
    assert {"/mcp", "/authorize", "/token", "/register", "/revoke",
            "/.well-known/oauth-authorization-server", "/.well-known/oauth-authorization-server/api",
            "/.well-known/oauth-protected-resource/api/mcp"} <= pfade
