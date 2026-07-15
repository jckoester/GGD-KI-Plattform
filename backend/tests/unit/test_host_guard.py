"""Unit-Tests: TrustedHostMiddleware / Host-Header-Schutz (Sicherheits-Audit #18)."""
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main


def _app_with_settings(allowed_hosts, environment="production"):
    fresh = FastAPI()

    @fresh.get("/health")
    async def _health():
        return {"status": "ok"}

    original = main.settings
    main.settings = SimpleNamespace(allowed_hosts=allowed_hosts, environment=environment)
    try:
        applied = main.configure_host_guard(fresh)
    finally:
        main.settings = original
    return fresh, applied


def test_wildcard_does_not_add_middleware():
    fresh, applied = _app_with_settings(["*"])
    assert applied is False
    # Ohne Middleware wird jeder Host akzeptiert.
    client = TestClient(fresh)
    resp = client.get("/health", headers={"host": "evil.example.com"})
    assert resp.status_code == 200


def test_real_allowlist_rejects_foreign_host():
    fresh, applied = _app_with_settings(["ki.example.de"])
    assert applied is True
    client = TestClient(fresh)
    resp = client.get("/health", headers={"host": "evil.example.com"})
    assert resp.status_code == 400


def test_real_allowlist_accepts_configured_host():
    fresh, _ = _app_with_settings(["ki.example.de"])
    client = TestClient(fresh)
    resp = client.get("/health", headers={"host": "ki.example.de"})
    assert resp.status_code == 200
