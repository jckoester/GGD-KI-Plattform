"""Endpoint-Tests für /upload/session — Magic-Byte-Prüfung (Sicherheits-Audit #14)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.ratelimit import store
from app.upload.router import router

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _user() -> JwtPayload:
    return JwtPayload(sub="pseudo-1", roles=["teacher"], grade=None, jti="j1", iat=1, exp=9999999999)


@pytest.fixture
def client():
    store.reset()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app, raise_server_exceptions=False)


def test_valid_png_accepted(client):
    resp = client.post("/upload/session", files={"file": ("bild.png", PNG, "image/png")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "image"
    assert body["mime_type"] == "image/png"


def test_html_renamed_as_png_rejected(client):
    html = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
    resp = client.post("/upload/session", files={"file": ("bild.png", html, "image/png")})
    assert resp.status_code == 415
    assert "passt nicht zur Endung" in resp.json()["detail"]


def test_plaintext_accepted(client):
    resp = client.post("/upload/session", files={"file": ("notiz.txt", b"Hallo Welt", "text/plain")})
    assert resp.status_code == 200
    assert resp.json()["type"] == "text"


def test_binary_renamed_as_txt_rejected(client):
    resp = client.post("/upload/session", files={"file": ("notiz.txt", b"ab\x00cd", "text/plain")})
    assert resp.status_code == 415


def test_unsupported_extension_still_415(client):
    resp = client.post("/upload/session", files={"file": ("x.exe", b"MZ\x00\x00", "application/octet-stream")})
    assert resp.status_code == 415
