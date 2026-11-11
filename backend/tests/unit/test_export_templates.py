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


# ── Eingebaute Vorlage A4 und Vorrang der Schulvorlage (0.39) ──────────────────

import io as _io
import zipfile as _zipfile

from app.export import pandoc as _pandoc

_needs_pandoc = pytest.mark.skipif(not _pandoc.pandoc_available(), reason="pandoc nicht installiert")


def test_a4_ersetzt_pandocs_letter_im_odt():
    xml = '<style:page-layout-properties fo:page-width="8.5in" fo:page-height="11in" fo:margin-top="1in"/>'
    neu = et._a4("odt", xml)
    assert 'fo:page-width="21cm"' in neu and 'fo:page-height="29.7cm"' in neu
    assert 'fo:margin-top="2cm"' in neu


def test_a4_ergaenzt_das_fehlende_format_im_docx():
    neu = et._a4("docx", "<w:sectPr><w:footnotePr/></w:sectPr>")
    # pgSz steht hinter footnotePr — die Reihenfolge schreibt das Schema vor.
    assert neu.index("<w:footnotePr/>") < neu.index('<w:pgSz w:w="11906" w:h="16838"')
    assert et._a4("docx", neu) == neu, "ein vorhandenes Format bleibt"


@_needs_pandoc
@pytest.mark.parametrize("fmt, eintrag, merkmal", [
    ("docx", "word/document.xml", '<w:pgSz w:w="11906" w:h="16838"'),
    ("odt", "styles.xml", 'fo:page-width="21cm"'),
])
def test_eingebaute_vorlage_ist_a4(monkeypatch, tmp_path, fmt, eintrag, merkmal):
    monkeypatch.setattr(et.settings, "export_template_dir", str(tmp_path))
    pfad = et.vorlage(fmt)
    assert pfad and pfad.endswith(f"reference.{fmt}")
    z = _zipfile.ZipFile(pfad)
    assert merkmal in z.read(eintrag).decode()
    if fmt == "odt":
        erster = z.infolist()[0]
        assert erster.filename == "mimetype" and erster.compress_type == _zipfile.ZIP_STORED


def test_schulvorlage_hat_vorrang(monkeypatch, tmp_path):
    monkeypatch.setattr(et.settings, "export_template_dir", str(tmp_path))
    et.save_reference("docx", b"PK-schule")
    assert et.vorlage("docx") == str(tmp_path / "reference.docx")


def test_ohne_pandoc_keine_eingebaute(monkeypatch, tmp_path):
    monkeypatch.setattr(et.settings, "export_template_dir", str(tmp_path))
    monkeypatch.setattr(et, "_eingebaut", {})
    monkeypatch.setattr(_pandoc.settings, "pandoc_bin", "definitiv-kein-pandoc-xyz")
    assert et.vorlage("odt") is None
