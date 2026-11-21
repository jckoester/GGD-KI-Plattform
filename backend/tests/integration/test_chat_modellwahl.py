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
from app.db.models import Assistant, Conversation, Message

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


# ── Schritt 2: Assistent mit Fähigkeiten braucht ⚙ (F3) ──────────────────────

FAEHIGKEITEN = {"chat-komplex": True, "chat-schnell": False}


@pytest_asyncio.fixture
async def planender(fabrik):
    async with fabrik() as db:
        a = Assistant(name=f"Planer {uuid.uuid4().hex[:6]}", system_prompt="P", model="chat-komplex",
                      status="active", audience="teacher", scope="teachers", creator_role="admin",
                      created_by="admin", tool_groups=["lesson_planning"])
        db.add(a)
        await db.commit()
        aid = a.id
    yield aid
    # Wieder weg: Ein aktiver Stundenassistent für Lehrkräfte gälte sonst in anderen Tests als
    # schulweite Vorlage (`test_eigener_stundenassistent`).
    async with fabrik() as db:
        await db.execute(Conversation.__table__.delete().where(Conversation.assistant_id == aid))
        await db.execute(Assistant.__table__.delete().where(Assistant.id == aid))
        await db.commit()


async def _antwort(client, kopf, **json):
    """`POST /chat` bis nach den Modellprüfungen: Danach hält die Suche den Lauf an."""
    async def anhalten(**_):
        raise _Angehalten

    with patch("app.chat.router._get_model_info", AsyncMock(return_value=FAEHIGKEITEN)), \
         patch("app.chat.router.kontext_fuer_frage", AsyncMock(side_effect=anhalten)):
        try:
            return await client.post("/chat", headers=kopf, json={
                "messages": [{"role": "user", "content": "Hallo"}], **json})
        except _Angehalten:
            return None


async def test_modell_ohne_funktionen_wird_abgewiesen(test_client, jwt_service, planender):
    kopf = _kopf(jwt_service, TEACHER1_PSEUDO, ["teacher"])
    antwort = await _antwort(test_client, kopf, assistant_id=planender, model_id="chat-schnell")
    assert antwort is not None and antwort.status_code == 403
    assert "⚙" in antwort.json()["detail"] and "chat-schnell" in antwort.json()["detail"]


async def test_modell_mit_funktionen_kommt_durch(test_client, jwt_service, planender):
    kopf = _kopf(jwt_service, TEACHER1_PSEUDO, ["teacher"])
    assert await _antwort(test_client, kopf, assistant_id=planender, model_id="chat-komplex") is None


async def test_ohne_faehigkeiten_bleibt_jedes_modell_waehlbar(test_client, jwt_service):
    kopf = _kopf(jwt_service, TEACHER1_PSEUDO, ["teacher"])
    assert await _antwort(test_client, kopf, assistant_id=ASSISTENT, model_id="chat-schnell") is None


# ── Schritt 3: bevorzugte Modelle speichern ──────────────────────────────────


@pytest_asyncio.fixture
async def ohne_vorliebe(test_client, jwt_service):
    """Lehrkraft ohne Vorliebe vorher und nachher — die Test-DB behält Einstellungen."""
    kopf = _kopf(jwt_service, TEACHER1_PSEUDO, ["teacher"])
    leer = {"modell_frei": None, "modell_planung": None}
    await test_client.patch("/preferences", headers=kopf, json=leer)
    yield kopf
    await test_client.patch("/preferences", headers=kopf, json=leer)


async def test_vorliebe_speichern_und_lesen(test_client, ohne_vorliebe, fabrik):
    from app.preferences.service import bevorzugte_modelle

    with patch("app.litellm.modell_eigenschaften.alle_eigenschaften", AsyncMock(return_value={})):
        r = await test_client.patch("/preferences", headers=ohne_vorliebe,
                                    json={"modell_frei": "chat-schnell", "modell_planung": "chat-komplex"})
    assert r.status_code == 200, r.text
    async with fabrik() as db:
        assert await bevorzugte_modelle(db, TEACHER1_PSEUDO) == {
            "modell_frei": "chat-schnell", "modell_planung": "chat-komplex"}


async def test_vorliebe_nur_fuer_lehrkraefte_und_nicht_in_der_vorschau(test_client, jwt_service):
    schuelerin = _kopf(jwt_service, STUDENT_PSEUDO, ["student"], grade="8")
    r = await test_client.patch("/preferences", headers=schuelerin, json={"modell_frei": "chat-schnell"})
    assert r.status_code == 403
    vorschau = _kopf(jwt_service, TEACHER1_PSEUDO, [], vorschau=True)
    r = await test_client.patch("/preferences", headers=vorschau, json={"modell_frei": "chat-schnell"})
    assert r.status_code == 403


async def test_vorliebe_ohne_funktionen_fuer_planung_abgewiesen(test_client, ohne_vorliebe):
    from app.litellm.modell_eigenschaften import Eigenschaften

    with patch("app.litellm.modell_eigenschaften.alle_eigenschaften",
               AsyncMock(return_value={"chat-schnell": Eigenschaften(funktionsaufrufe=False)})):
        r = await test_client.patch("/preferences", headers=ohne_vorliebe, json={"modell_planung": "chat-schnell"})
    assert r.status_code == 422 and "Funktionen" in r.json()["detail"]


async def test_keine_vorliebe_entfernt_den_schluessel(test_client, ohne_vorliebe):
    with patch("app.litellm.modell_eigenschaften.alle_eigenschaften", AsyncMock(return_value={})):
        await test_client.patch("/preferences", headers=ohne_vorliebe, json={"modell_frei": "chat-schnell"})
    r = await test_client.patch("/preferences", headers=ohne_vorliebe, json={"modell_frei": ""})
    assert "modell_frei" not in r.json()


# ── Schritt 4: Vorliebe beim Anlegen ─────────────────────────────────────────


async def _vorliebe(client, kopf, **werte):
    with patch("app.litellm.modell_eigenschaften.alle_eigenschaften", AsyncMock(return_value={})):
        r = await client.patch("/preferences", headers=kopf, json=werte)
    assert r.status_code == 200, r.text


async def test_vorliebe_im_freien_chat(test_client, ohne_vorliebe):
    await _vorliebe(test_client, ohne_vorliebe, modell_frei="chat-schnell")
    assert await _modell(test_client, ohne_vorliebe) == "chat-schnell"
    # Ausdrückliche Wahl schlägt die Vorliebe.
    assert await _modell(test_client, ohne_vorliebe, model_id="chat-komplex") == "chat-komplex"


async def test_vorliebe_fuer_planungs_assistenten_auch_gegen_sein_modell(test_client, ohne_vorliebe, planender):
    await _vorliebe(test_client, ohne_vorliebe, modell_planung="ant-sonnet")
    with patch("app.chat.router._get_model_info", AsyncMock(return_value={"ant-sonnet": True})):
        assert await _modell(test_client, ohne_vorliebe, assistant_id=planender) == "ant-sonnet"


async def test_andere_assistenten_behalten_ihr_modell(test_client, ohne_vorliebe):
    await _vorliebe(test_client, ohne_vorliebe, modell_frei="chat-schnell", modell_planung="ant-sonnet")
    assert await _modell(test_client, ohne_vorliebe, assistant_id=ASSISTENT) == SEIN_MODELL


async def test_vorliebe_ohne_funktionen_faellt_zurueck(test_client, ohne_vorliebe, planender):
    """Die Eigenschaft hat sich seit dem Speichern geändert: Modell des Assistenten, mit Hinweis."""
    await _vorliebe(test_client, ohne_vorliebe, modell_planung="ant-sonnet")
    from app.chat.modellwahl import vorliebe_anwenden

    gesehen = []
    echt = vorliebe_anwenden

    async def mitschreiben(*a, **k):
        ergebnis = await echt(*a, **k)
        gesehen.append(ergebnis)
        return ergebnis

    with patch("app.chat.router._get_model_info", AsyncMock(return_value={"ant-sonnet": False})), \
         patch("app.chat.router.vorliebe_anwenden", mitschreiben):
        assert await _modell(test_client, ohne_vorliebe, assistant_id=planender) == "chat-komplex"
    assert gesehen and "keine Funktionen" in gesehen[0][1]


async def test_bestehende_konversation_behaelt_ihr_modell(test_client, ohne_vorliebe, fabrik):
    await _vorliebe(test_client, ohne_vorliebe, modell_frei="chat-schnell")
    cid = await _bestehender_chat(fabrik, TEACHER1_PSEUDO, assistant_id=None, modell="chat-standard")
    assert await _modell(test_client, ohne_vorliebe, conversation_id=cid) == "chat-standard"


async def test_schuelerin_bekommt_keine_vorliebe(test_client, jwt_service, ohne_vorliebe):
    # Die Lehrkraft hat eine — für Schüler:innen gibt es keine (F8), und ihre gilt nicht für andere.
    await _vorliebe(test_client, ohne_vorliebe, modell_frei="chat-schnell")
    kopf = _kopf(jwt_service, STUDENT_PSEUDO, ["student"], grade="8")
    from app.config import settings
    assert await _modell(test_client, kopf) == settings.chat_default_model
