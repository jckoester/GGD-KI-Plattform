"""Der Chat setzt die Modell-Freigabe durch (0.27, Plan Schritt 6).

⚠️ Der Proxy tut es nicht: Die Schlüssel der Nutzer:innen tragen kein Team, LiteLLM prüft die
Team-Modelle dann nicht. Bis 0.27 lief jedes Modell, das im Request stand. Die Ablehnung kommt
vor dem Aufruf an LiteLLM — der Test braucht keinen Proxy. Erfordert TEST_DATABASE_URL.
"""
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation
from app.litellm import team_models

pytestmark = pytest.mark.asyncio


@pytest.fixture
def nur_standard(monkeypatch):
    team_models.invalidate_team_models_cache()
    monkeypatch.setattr(team_models._client, "get_team_info",
                        AsyncMock(return_value={"models": ["chat-standard", "system-titel"]}))
    yield
    team_models.invalidate_team_models_cache()


async def _anzahl(async_engine, pseudonym):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        return (await db.execute(sa.select(sa.func.count()).select_from(Conversation)
                                 .where(Conversation.pseudonym == pseudonym))).scalar_one()


async def test_gesperrtes_modell_wird_abgelehnt(test_client, auth_headers_student, nur_standard, async_engine):
    vorher = await _anzahl(async_engine, "student1-pseudo")
    resp = await test_client.post("/chat", headers=auth_headers_student, json={
        "model_id": "chat-komplex", "messages": [{"role": "user", "content": "Hallo"}]})
    assert resp.status_code == 403, resp.text
    assert "nicht freigeschaltet" in resp.json()["detail"]
    # Keine leere Konversation zurückgelassen.
    assert await _anzahl(async_engine, "student1-pseudo") == vorher
