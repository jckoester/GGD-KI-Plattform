"""Adressen der Schnittstelle für KI-Abos (0.55, Päckchen AX Schritt 3): Issuer, Pflicht zu https
und zu `/api/mcp` am Ende (lokal `/mcp`)."""
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
    # 0.55.1: ohne /api fände kein Programm Metadaten, /authorize und /token (Prod-Test 23.11.)
    "https://ki.schule.de/mcp", "https://ki.schule.de/ki/mcp",
])
def test_unbrauchbare_adresse_laesst_die_schnittstelle_aus(url):
    app = FastAPI()
    assert einhaengen(app, aktiv=True, oeffentliche_url=url, geheimnis="x") is None
    assert not [r for r in app.router.routes if getattr(r, "path", "") == "/mcp"]


def test_ohne_api_nennt_das_log_die_richtige_form(caplog):
    einhaengen(FastAPI(), aktiv=True, oeffentliche_url="https://ki.schule.de/mcp", geheimnis="x")
    assert "https://ki.schule.de/api/mcp" in caplog.text


@pytest.mark.parametrize("url", ["https://schule.de/ki/api/mcp/", "http://localhost:8000/mcp"])
def test_brauchbare_adressen(url):
    assert einhaengen(FastAPI(), aktiv=True, oeffentliche_url=url, geheimnis="x") is not None


def test_routen_fuer_issuer_mit_pfad():
    app = FastAPI()
    assert einhaengen(app, aktiv=True, oeffentliche_url="https://ki.schule.de/api/mcp", geheimnis="x")
    pfade = {getattr(r, "path", "") for r in app.router.routes}
    assert {"/mcp", "/authorize", "/token", "/register", "/revoke",
            "/.well-known/oauth-authorization-server", "/.well-known/oauth-authorization-server/api",
            "/.well-known/oauth-protected-resource/api/mcp"} <= pfade
