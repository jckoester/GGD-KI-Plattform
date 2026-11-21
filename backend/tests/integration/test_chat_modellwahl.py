"""Wer im Chat das Modell wählen darf (0.51, Päckchen AV Schritt 1).

Schüler:innen und die Vorschau bleiben bei aktivem Assistenten bei dessen Modell; ein
mitgeschicktes `model_id` wird verworfen (F6). Lehrkräfte dürfen umstellen. Im freien Chat
gilt das gewählte Modell für alle.

Gemessen wird das Modell an der Stelle, an der der Chat die Freigabe prüft — noch vor dem
Aufruf an LiteLLM. Dafür gibt `erlaubte_modelle_fuer` hier eine Menge zurück, die die Frage
festhält und den Lauf anhält. Erfordert TEST_DATABASE_URL.
"""
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import Vorschau
from app.db.models import Conversation, Message

from .conftest import STUDENT_PSEUDO, TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio

ASSISTENT = 1           # Test-Assistent aus der conftest, Modell „gpt-4o“
SEIN_MODELL = "gpt-4o"
GEWAEHLT = "chat-komplex"


class _Angehalten(Exception):
    pass


class _Festhalten(set):
    """Menge, die die Frage „ist Modell X erlaubt?“ festhält und den Chat dann anhält."""

    def __init__(self, gesehen):
        super().__init__()
        self.gesehen = gesehen

    def __contains__(self, modell):
        self.gesehen.append(modell)
        raise _Angehalten


async def _modell(client, kopf, **json) -> str:
    gesehen: list[str] = []
    with patch("app.chat.router.erlaubte_modelle_fuer", AsyncMock(return_value=_Festhalten(gesehen))):
        try:
            await client.post("/chat", headers=kopf, json={
                "messages": [{"role": "user", "content": "Hallo"}], **json})
        except _Angehalten:
            pass
    assert gesehen, "Der Chat kam nicht bis zur Prüfung der Freigabe"
    return gesehen[0]


def _kopf(jwt_service, pseudonym, rollen, grade=None, vorschau=False):
    if vorschau:
        jetzt = int(time.time())
        token, _ = jwt_service.issue(
            pseudonym=pseudonym, roles=["student"], grade="9",
            preview=Vorschau(echte_rollen=["teacher"], gruppe_id=None, beginn=jetzt,
                             sitzung_ablauf=jetzt + 3600),
            exp=jetzt + 3600)
    else:
        token, _ = jwt_service.issue(pseudonym=pseudonym, roles=rollen, grade=grade)
    return {"Cookie": f"session={token}"}


@pytest_asyncio.fixture
async def fabrik(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def _bestehender_chat(fabrik, pseudonym, assistant_id=ASSISTENT, modell=SEIN_MODELL) -> str:
    async with fabrik() as db:
        k = Conversation(pseudonym=pseudonym, model_used=modell, assistant_id=assistant_id,
                         title=f"Modellwahl {uuid.uuid4().hex[:6]}")
        db.add(k)
        await db.flush()
        db.add(Message(conversation_id=k.id, role="user", content="vorher"))
        await db.commit()
        return str(k.id)


# ── Neuer Chat mit Assistent ─────────────────────────────────────────────────


async def test_schuelerin_bleibt_beim_modell_des_assistenten(test_client, jwt_service):
    kopf = _kopf(jwt_service, STUDENT_PSEUDO, ["student"], grade="8")
    assert await _modell(test_client, kopf, assistant_id=ASSISTENT, model_id=GEWAEHLT) == SEIN_MODELL


async def test_lehrkraft_stellt_um(test_client, jwt_service):
    kopf = _kopf(jwt_service, TEACHER1_PSEUDO, ["teacher"])
    assert await _modell(test_client, kopf, assistant_id=ASSISTENT, model_id=GEWAEHLT) == GEWAEHLT


async def test_vorschau_bleibt_beim_modell_des_assistenten(test_client, jwt_service):
    kopf = _kopf(jwt_service, TEACHER1_PSEUDO, [], vorschau=True)
    assert await _modell(test_client, kopf, assistant_id=ASSISTENT, model_id=GEWAEHLT) == SEIN_MODELL


# ── Freier Chat: Wahl gilt für alle ──────────────────────────────────────────


async def test_schuelerin_waehlt_im_freien_chat(test_client, jwt_service):
    kopf = _kopf(jwt_service, STUDENT_PSEUDO, ["student"], grade="8")
    assert await _modell(test_client, kopf, model_id=GEWAEHLT) == GEWAEHLT


# ── Mitten im Chat ───────────────────────────────────────────────────────────


async def test_schuelerin_wechselt_nicht_mitten_im_assistenten_chat(test_client, jwt_service, fabrik):
    cid = await _bestehender_chat(fabrik, STUDENT_PSEUDO)
    kopf = _kopf(jwt_service, STUDENT_PSEUDO, ["student"], grade="8")
    assert await _modell(test_client, kopf, conversation_id=cid, model_id=GEWAEHLT) == SEIN_MODELL


async def test_lehrkraft_wechselt_mitten_im_assistenten_chat(test_client, jwt_service, fabrik):
    cid = await _bestehender_chat(fabrik, TEACHER1_PSEUDO)
    kopf = _kopf(jwt_service, TEACHER1_PSEUDO, ["teacher"])
    assert await _modell(test_client, kopf, conversation_id=cid, model_id=GEWAEHLT) == GEWAEHLT


async def test_schuelerin_wechselt_assistent_mit_modell(test_client, jwt_service, fabrik):
    """Wechsel des Assistenten mitten im freien Chat: dessen Modell, nicht das mitgeschickte."""
    cid = await _bestehender_chat(fabrik, STUDENT_PSEUDO, assistant_id=None, modell="chat-standard")
    kopf = _kopf(jwt_service, STUDENT_PSEUDO, ["student"], grade="8")
    assert await _modell(test_client, kopf, conversation_id=cid, assistant_id=ASSISTENT,
                         model_id=GEWAEHLT) == SEIN_MODELL
