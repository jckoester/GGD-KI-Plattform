"""Unit-Tests für app.api.pii (Phase 14, Schritt 2)."""

import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.api.pii import router
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload


def _make_app(authed=True):
    app = FastAPI()
    app.include_router(router)
    if authed:
        async def fake_user():
            return JwtPayload(sub="p", roles=["student"], grade="8", jti="j", iat=1, exp=9999999999)
        app.dependency_overrides[get_current_user] = fake_user
    return app


def test_scan_returns_spans_for_name():
    r = TestClient(_make_app()).post("/pii/scan", json={"text": "Ich heiße Lena Hoffmann."})
    assert r.status_code == 200
    spans = r.json()["spans"]
    assert any(s["category"] == "name" for s in spans)
    s = spans[0]
    assert {"category", "start", "end", "text"} <= s.keys()


def test_scan_returns_wohnort():
    r = TestClient(_make_app()).post(
        "/pii/scan", json={"text": "Ich wohne in der Lindenstraße 4 in Reutlingen."}
    )
    assert r.status_code == 200
    assert any(s["category"] == "wohnort" for s in r.json()["spans"])


def test_scan_empty_for_topic():
    r = TestClient(_make_app()).post("/pii/scan", json={"text": "Erklär mir die Photosynthese."})
    assert r.status_code == 200
    assert r.json()["spans"] == []


def test_scan_ignores_structured_pii():
    # E-Mail/Telefon werden client-seitig erkannt (D-C) — der Endpoint warnt hier nicht.
    r = TestClient(_make_app()).post(
        "/pii/scan", json={"text": "Erreichbar unter info@beispielschule.de"}
    )
    assert r.status_code == 200
    assert r.json()["spans"] == []


def test_scan_requires_auth():
    r = TestClient(_make_app(authed=False)).post("/pii/scan", json={"text": "x"})
    assert r.status_code == 401


def test_scan_rejects_overlong_text():
    r = TestClient(_make_app()).post("/pii/scan", json={"text": "x" * 20001})
    assert r.status_code == 422
