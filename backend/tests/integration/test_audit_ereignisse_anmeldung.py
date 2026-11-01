"""Anmeldeereignisse im Audit-Log (0.28, Plan Schritt 5, zweiter Durchgang).

Eine gescheiterte direkte Anmeldung wird protokolliert — ohne Benutzernamen und ohne Passwort.
Erfordert TEST_DATABASE_URL.
"""
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


pytestmark = pytest.mark.asyncio


class _Abweisend:
    mode = "direct"

    async def authenticate_direct(self, username, password):
        return None


async def test_falsche_anmeldedaten(test_client, async_engine):
    from app.auth.dependencies import get_auth_adapter
    from app.main import app

    app.dependency_overrides[get_auth_adapter] = lambda: _Abweisend()
    try:
        resp = await test_client.post("/auth/login", json={"username": "max.muster", "password": "geheim123"})
    finally:
        app.dependency_overrides.pop(get_auth_adapter, None)
    assert resp.status_code == 401

    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        zeile = (await db.execute(sa.text(
            "SELECT category, actor_pseudonym, payload::text FROM audit_log"
            " WHERE event_type = 'login_failed' ORDER BY id DESC LIMIT 1"))).one()
    assert zeile[0] == "auth" and zeile[1] is None
    assert "max.muster" not in zeile[2] and "geheim123" not in zeile[2]
    assert "anmeldedaten" in zeile[2]
