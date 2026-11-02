"""Tests: Audit-Log lesen (0.28, Plan Schritt 6)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin.audit import BEZEICHNUNG, KATEGORIEN, router
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.core.audit import EREIGNISSE
from app.db.session import get_db


def _app(roles):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: JwtPayload(
        sub="p", roles=list(roles), grade=None, jti="j", iat=1, exp=9999999999)

    async def _get_db():
        yield None

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app, raise_server_exceptions=False)


def test_jedes_ereignis_hat_eine_bezeichnung():
    fehlend = {e for es in EREIGNISSE.values() for e in es} - BEZEICHNUNG.keys()
    assert not fehlend, f"Bezeichnung fehlt in app/api/admin/audit.py: {sorted(fehlend)}"


def test_jede_kategorie_mit_ereignissen_erscheint_im_katalog():
    assert {k for k, es in EREIGNISSE.items() if es} <= KATEGORIEN.keys()


def test_katalog_nennt_aufbewahrung():
    resp = _app(["teacher", "admin"]).get("/audit/katalog")
    assert resp.status_code == 200
    kategorien = {k["name"]: k for k in resp.json()["kategorien"]}
    assert kategorien["auth"]["aufbewahrung_tage"] == 180
    assert "login_failed" in {e["name"] for e in kategorien["auth"]["ereignisse"]}


def test_nur_fuer_admins():
    client = _app(["teacher"])
    assert client.get("/audit").status_code == 403
    assert client.get("/audit/katalog").status_code == 403


def test_unbekannte_kategorie_und_verkehrter_zeitraum():
    client = _app(["teacher", "admin"])
    assert client.get("/audit", params={"kategorie": "nix"}).status_code == 422
    assert client.get("/audit", params={"von": "2026-11-02", "bis": "2026-11-01"}).status_code == 422
    assert client.get("/audit", params={"pro_seite": 500}).status_code == 422
