"""Unit-Tests: schulweite Export-Vorlagen (Phase 19, Schritt 6)."""
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.api.admin.export_templates import router
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.session import get_db
from app.export import templates as et

_PK = b"PK\x03\x04rest-of-a-zip"


def _user(roles) -> JwtPayload:
    return JwtPayload(sub="p", roles=roles, grade=None, jti="j", iat=1, exp=9999999999)


def _client(payload):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: payload
    app.dependency_overrides[get_db] = lambda: MagicMock()
    return TestClient(app)


# ── templates.py Helfer ───────────────────────────────────────────────────────

async def test_get_export_css(monkeypatch):
    res = MagicMock(); res.scalar_one_or_none = MagicMock(return_value="h1{color:red}")
    db = MagicMock(); db.execute = AsyncMock(return_value=res)
    assert await et.get_export_css(db) == "h1{color:red}"


async def test_get_export_css_empty(monkeypatch):
    res = MagicMock(); res.scalar_one_or_none = MagicMock(return_value=None)
    db = MagicMock(); db.execute = AsyncMock(return_value=res)
    assert await et.get_export_css(db) == ""


def test_reference_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(et.settings, "export_template_dir", str(tmp_path))
    assert et.has_reference("docx") is False
    assert et.reference_path("docx") is None
    et.save_reference("docx", _PK)
    assert et.has_reference("docx") is True
    assert et.reference_path("docx").read_bytes() == _PK
    assert et.delete_reference("docx") is True
    assert et.has_reference("docx") is False


def test_reference_bad_format(monkeypatch, tmp_path):
    monkeypatch.setattr(et.settings, "export_template_dir", str(tmp_path))
    assert et.reference_path("pdf") is None
    with pytest.raises(ValueError):
        et.save_reference("pdf", _PK)


# ── Admin-Endpunkte ───────────────────────────────────────────────────────────

def test_status_requires_admin(monkeypatch, tmp_path):
    monkeypatch.setattr(et.settings, "export_template_dir", str(tmp_path))
    resp = _client(_user(["teacher"])).get("/export-templates")
    assert resp.status_code == 403


def test_status_and_css_update(monkeypatch, tmp_path):
    monkeypatch.setattr(et.settings, "export_template_dir", str(tmp_path))
    monkeypatch.setattr(et, "get_export_css", AsyncMock(return_value="body{}"))
    monkeypatch.setattr(et, "set_export_css", AsyncMock())
    # GET-Status liest site_config direkt → execute mocken
    import app.api.admin.export_templates as mod
    row = MagicMock(); row.value = "body{}"; row.updated_at = None; row.updated_by = "p"
    res = MagicMock(); res.scalar_one_or_none = MagicMock(return_value=row)
    app = FastAPI(); app.include_router(router)
    db = MagicMock(); db.execute = AsyncMock(return_value=res)
    app.dependency_overrides[get_current_user] = lambda: _user(["admin"])
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    r1 = client.get("/export-templates")
    assert r1.status_code == 200
    assert r1.json()["css"] == "body{}"
    r2 = client.put("/export-templates/css", json={"css": "h1{}"})
    assert r2.status_code == 200


def test_upload_reference_validation(monkeypatch, tmp_path):
    monkeypatch.setattr(et.settings, "export_template_dir", str(tmp_path))
    row = MagicMock(); row.value = ""; row.updated_at = None; row.updated_by = None
    res = MagicMock(); res.scalar_one_or_none = MagicMock(return_value=row)
    app = FastAPI(); app.include_router(router)
    db = MagicMock(); db.execute = AsyncMock(return_value=res)
    app.dependency_overrides[get_current_user] = lambda: _user(["admin"])
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    # gültiges DOCX (PK-Signatur)
    ok = client.post("/export-templates/reference/docx", files={"file": ("r.docx", _PK)})
    assert ok.status_code == 200
    assert et.has_reference("docx") is True
    # falsches Format
    assert client.post("/export-templates/reference/pdf", files={"file": ("r.pdf", _PK)}).status_code == 422
    # keine ZIP-Signatur
    bad = client.post("/export-templates/reference/odt", files={"file": ("r.odt", b"not-a-zip")})
    assert bad.status_code == 422
    # zu groß
    monkeypatch.setattr(et.settings, "export_reference_max_bytes", 3)
    big = client.post("/export-templates/reference/docx", files={"file": ("r.docx", _PK)})
    assert big.status_code == 413
