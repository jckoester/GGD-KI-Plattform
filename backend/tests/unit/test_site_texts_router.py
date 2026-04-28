"""
Tests für app.site_texts.router und app.api.admin.site_texts
"""
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.models import SiteText
from app.db.session import get_db
from app.site_texts.router import router as site_texts_router
from app.api.admin.site_texts import router as admin_site_texts_router


# ========== Hilfsfunktionen ==========

def _fake_admin_payload() -> JwtPayload:
    return JwtPayload(sub="p-1", roles=["admin"], grade=None,
                      jti="j-1", iat=1, exp=9999999999)


def _fake_budget_payload() -> JwtPayload:
    return JwtPayload(sub="p-1", roles=["budget"], grade=None,
                      jti="j-1", iat=1, exp=9999999999)


def _fake_teacher_payload() -> JwtPayload:
    return JwtPayload(sub="p-1", roles=["teacher"], grade=None,
                      jti="j-1", iat=1, exp=9999999999)


def _make_site_texts_app() -> FastAPI:
    """App für öffentliche Site-Texts Endpoints (kein Auth-Override nötig)"""
    app = FastAPI()
    app.include_router(site_texts_router)
    
    async def fake_db():
        yield AsyncMock()
    
    app.dependency_overrides[get_db] = fake_db
    return app


def _make_admin_site_texts_app(payload: JwtPayload, mock_db) -> FastAPI:
    """App für Admin Site-Texts Endpoints"""
    app = FastAPI()
    app.include_router(admin_site_texts_router)
    
    async def fake_user():
        return payload
    
    async def fake_db():
        yield mock_db
    
    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[get_db] = fake_db
    return app


def _mock_site_text_db(site_text: SiteText | None) -> AsyncMock:
    """DB-Mock für SiteText-Abfragen"""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = site_text
    session.execute.return_value = result
    return session


# ========== Öffentliche Endpoint Tests ==========


def test_get_site_text_returns_content():
    """DB liefert SiteText(key="impressum", content="Test"), 200 erwartet"""
    mock_site_text = MagicMock(spec=SiteText)
    mock_site_text.key = "impressum"
    mock_site_text.content = "Test"
    mock_site_text.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    
    app = _make_site_texts_app()
    
    with patch("app.site_texts.router.select") as mock_select:
        with patch("app.site_texts.router.get_db") as mock_get_db:
            mock_select.return_value = MagicMock()
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_site_text
            mock_session.execute.return_value = mock_result
            mock_get_db.return_value = mock_session
            
            from app.db.session import get_db as get_db_orig
            with patch.object(app, 'dependency_overrides', {}):
                app.dependency_overrides[get_db] = lambda: mock_session
                
                client = TestClient(app, raise_server_exceptions=True)
                response = client.get("/site-texts/impressum")
    
    assert response.status_code == 200
    data = response.json()
    assert data["key"] == "impressum"
    assert data["content"] == "Test"
    assert data["updated_at"] == "2026-01-01T00:00:00+00:00"


def test_get_site_text_unknown_key_returns_404():
    """key="unbekannt" → 404 (Whitelist-Check vor DB-Zugriff)"""
    app = FastAPI()
    app.include_router(site_texts_router)
    
    client = TestClient(app)
    response = client.get("/site-texts/unbekannt")
    
    assert response.status_code == 404


def test_get_site_text_missing_in_db_returns_404():
    """key in Whitelist, aber DB liefert None → 404"""
    app = FastAPI()
    app.include_router(site_texts_router)
    
    async def mock_db():
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        return session
    
    app.dependency_overrides[get_db] = mock_db
    
    client = TestClient(app)
    response = client.get("/site-texts/impressum")
    
    assert response.status_code == 404


def test_get_site_text_requires_no_auth():
    """Kein Auth-Override → 200 (kein 401/403)"""
    mock_site_text = MagicMock(spec=SiteText)
    mock_site_text.key = "impressum"
    mock_site_text.content = "Test"
    mock_site_text.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    
    app = FastAPI()
    app.include_router(site_texts_router)
    
    async def mock_db():
        from sqlalchemy import select
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_site_text
        session.execute.return_value = result
        return session
    
    app.dependency_overrides[get_db] = mock_db
    
    client = TestClient(app)
    response = client.get("/site-texts/impressum")
    
    assert response.status_code == 200


# ========== Admin-Endpoint Tests ==========


def test_put_site_text_requires_admin_role():
    """budget-only → 403"""
    mock_db = AsyncMock()
    app = _make_admin_site_texts_app(_fake_budget_payload(), mock_db)
    
    client = TestClient(app)
    response = client.put("/site-texts/impressum", json={"content": "Neuer Text"})
    
    assert response.status_code == 403


def test_put_site_text_updates_content():
    """admin, body={content: "Neuer Text"} → 200, updated_at in Antwort"""
    from sqlalchemy import select, update as sql_update
    
    mock_site_text = MagicMock(spec=SiteText)
    mock_site_text.key = "impressum"
    mock_site_text.content = "Alter Text"
    mock_site_text.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    
    new_updated_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    mock_updated_text = MagicMock(spec=SiteText)
    mock_updated_text.key = "impressum"
    mock_updated_text.content = "Neuer Text"
    mock_updated_text.updated_at = new_updated_at
    
    session = AsyncMock()
    
    # Erste Abfrage: SiteText finden
    result1 = MagicMock()
    result1.scalar_one_or_none.return_value = mock_site_text
    
    # Update-Abfrage
    result2 = MagicMock()
    
    # Zweite Abfrage: Aktualisierten Datensatz holen
    result3 = MagicMock()
    result3.scalar_one.return_value = mock_updated_text
    
    session.execute.side_effect = [result1, result2, result3]
    session.commit = AsyncMock()
    
    app = _make_admin_site_texts_app(_fake_admin_payload(), session)
    
    client = TestClient(app)
    response = client.put("/site-texts/impressum", json={"content": "Neuer Text"})
    
    assert response.status_code == 200
    data = response.json()
    assert data["key"] == "impressum"
    assert "updated_at" in data


def test_put_site_text_unknown_key_returns_404():
    """key="unbekannt", admin → 404"""
    session = AsyncMock()
    
    app = _make_admin_site_texts_app(_fake_admin_payload(), session)
    
    client = TestClient(app)
    response = client.put("/site-texts/unbekannt", json={"content": "Text"})
    
    assert response.status_code == 404


def test_put_site_text_too_long_returns_422():
    """content mit 50 001 Zeichen → 422"""
    app = _make_admin_site_texts_app(_fake_admin_payload(), AsyncMock())
    
    client = TestClient(app)
    long_content = "a" * 50_001
    response = client.put("/site-texts/impressum", json={"content": long_content})
    
    assert response.status_code == 422


def test_put_site_text_empty_content_allowed():
    """content="" → 200 (leerer String ist gültig)"""
    from sqlalchemy import select, update as sql_update
    
    mock_site_text = MagicMock(spec=SiteText)
    mock_site_text.key = "impressum"
    mock_site_text.content = "Alter Text"
    mock_site_text.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    
    new_updated_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    mock_updated_text = MagicMock(spec=SiteText)
    mock_updated_text.key = "impressum"
    mock_updated_text.content = ""
    mock_updated_text.updated_at = new_updated_at
    
    session = AsyncMock()
    
    result1 = MagicMock()
    result1.scalar_one_or_none.return_value = mock_site_text
    
    result2 = MagicMock()
    
    result3 = MagicMock()
    result3.scalar_one.return_value = mock_updated_text
    
    session.execute.side_effect = [result1, result2, result3]
    session.commit = AsyncMock()
    
    app = _make_admin_site_texts_app(_fake_admin_payload(), session)
    
    client = TestClient(app)
    response = client.put("/site-texts/impressum", json={"content": ""})
    
    assert response.status_code == 200
