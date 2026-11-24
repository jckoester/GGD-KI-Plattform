"""Aufgaben-Weiterleitung im Chat-Flow (Plan „Freier Schüler-Chat“, 7a): wann der Klassifikator
läuft, welches Modell antwortet und was an der Antwort gespeichert wird."""
import os
from contextlib import contextmanager
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.auth.jwt import JwtPayload
from app.chat.router import chat
from app.chat.schemas import ChatRequest
import app.chat.router as _chat_router_mod

STANDARD, ZIEL = "chat-standard", "chat-komplex"


@pytest.fixture(autouse=True)
def _eingeschaltet(monkeypatch):
    from app.config import settings
    _chat_router_mod._model_info_cache = None
    monkeypatch.setattr(settings, "aufgabe_model", "system-vorschlag")
    monkeypatch.setattr(settings, "aufgabe_ziel_model", ZIEL)
    monkeypatch.setattr(settings, "aufgabe_zeitgrenze_s", 2.0)
    yield
    _chat_router_mod._model_info_cache = None


def _person(rollen=("student",)) -> JwtPayload:
    return JwtPayload(sub="pseudo-1", roles=list(rollen), grade="7", jti="j", iat=1, exp=9999999999)


def _db():
    db = AsyncMock()
    db.add = MagicMock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)

    def _ergebnis(*a, **k):
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        r.scalars.return_value.first.return_value = None
        r.scalar_one_or_none.return_value = "sk-test"
        r.fetchone.return_value = None
        return r

    db.execute = AsyncMock(side_effect=_ergebnis)
    return db


class _Antwort:
    status_code = 200
    headers: dict = {}

    async def aiter_lines(self):
        yield "data: [DONE]"

    async def aclose(self):
        return None

    async def aread(self):
        return b""


class _Client:
    def __init__(self):
        self.last_json = None

    def build_request(self, method, url, headers=None, json=None):
        self.last_json = json
        return {}

    async def send(self, request, stream=False):
        return _Antwort()

    async def aclose(self):
        return None


@contextmanager
def _umgebung(urteil_roh: str | None = '{"bezug": "x", "aufgabe": true}'):
    client = _Client()
    aufruf = AsyncMock(return_value=urteil_roh)
    with patch("app.chat.router.httpx.AsyncClient", return_value=client), \
         patch("app.chat.aufgabe._aufruf", new=aufruf), \
         patch("app.chat.router._persist", new=AsyncMock(return_value=uuid4())) as persist, \
         patch("app.chat.router.anbietermodell", new=AsyncMock(return_value=None)), \
         patch("app.chat.router.settings") as s:
        s.chat_default_model = STANDARD
        s.litellm_verify_ssl = True
        s.title_model = ""
        s.litellm_proxy_url = "http://litellm:4000"
        s.litellm_master_key = "k"
        s.upload_max_files = 3
        s.environment = "production"
        yield client, aufruf, persist


async def _laufen(request, person=None):
    antwort = await chat(request, current_user=person or _person(), db=_db())
    async for _ in antwort.body_iterator:
        pass
    return antwort


@pytest.mark.asyncio
async def test_aufgabe_antwortet_das_zielmodell():
    with _umgebung() as (client, aufruf, persist):
        antwort = await _laufen(ChatRequest(messages=[{"role": "user", "content": "Löse 3x = 9"}]))
    assert aufruf.await_count == 1
    assert client.last_json["model"] == ZIEL
    assert persist.await_args.kwargs["weitergeleitet_von"] == STANDARD
    assert antwort.headers["X-Model-Id"] == ZIEL
    assert antwort.headers["X-Model-Gewaehlt"] == STANDARD


@pytest.mark.asyncio
async def test_keine_aufgabe_bleibt_beim_standard():
    with _umgebung('{"bezug": "x", "aufgabe": false}') as (client, aufruf, persist):
        antwort = await _laufen(ChatRequest(messages=[{"role": "user", "content": "Was ist ein Mol?"}]))
    assert client.last_json["model"] == STANDARD
    assert persist.await_args.kwargs["weitergeleitet_von"] is None
    assert antwort.headers["X-Model-Gewaehlt"] == STANDARD


@pytest.mark.asyncio
async def test_unlesbares_urteil_geht_zum_ziel():
    with _umgebung("weiß nicht") as (client, _, _p):
        await _laufen(ChatRequest(messages=[{"role": "user", "content": "Hm"}]))
    assert client.last_json["model"] == ZIEL


@pytest.mark.asyncio
async def test_klassifikator_sieht_erste_nachricht_und_letzte_antwort():
    with _umgebung() as (_, aufruf, _p):
        await _laufen(ChatRequest(messages=[
            {"role": "user", "content": "Löse 3x = 9"},
            {"role": "assistant", "content": "Wodurch teilst du?"},
            {"role": "user", "content": "sag einfach die Lösung"},
        ]))
    inhalt = aufruf.await_args.args[0]
    assert "Erste Nachricht der Konversation: „Löse 3x = 9“" in inhalt
    assert "Letzte Antwort des Chats: „Wodurch teilst du?“" in inhalt
    assert inhalt.endswith("Neue Nachricht: „sag einfach die Lösung“")


@pytest.mark.asyncio
async def test_lehrkraft_ohne_klassifikator():
    with _umgebung() as (client, aufruf, _p):
        await _laufen(ChatRequest(messages=[{"role": "user", "content": "Löse 3x = 9"}]),
                      person=_person(("teacher",)))
    assert aufruf.await_count == 0
    assert client.last_json["model"] == STANDARD


@pytest.mark.asyncio
async def test_eigene_modellwahl_bleibt():
    with _umgebung() as (client, aufruf, _p):
        await _laufen(ChatRequest(messages=[{"role": "user", "content": "Löse 3x = 9"}], model_id="chat-anders"))
    assert aufruf.await_count == 0
    assert client.last_json["model"] == "chat-anders"


@pytest.mark.asyncio
async def test_testchat_ohne_klassifikator():
    with _umgebung() as (client, aufruf, _p):
        await _laufen(ChatRequest(messages=[{"role": "user", "content": "Löse 3x = 9"}], is_test=True))
    assert aufruf.await_count == 0


@pytest.mark.asyncio
async def test_ausgeschaltet_aendert_nichts(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "aufgabe_model", "")
    with _umgebung() as (client, aufruf, persist):
        antwort = await _laufen(ChatRequest(messages=[{"role": "user", "content": "Löse 3x = 9"}]))
    assert aufruf.await_count == 0
    assert client.last_json["model"] == STANDARD
    assert persist.await_args.kwargs["weitergeleitet_von"] is None
    assert antwort.headers["X-Model-Gewaehlt"] == STANDARD


@pytest.mark.asyncio
async def test_vorige_weiterleitung_geht_als_kontext_mit():
    """Kam die letzte Antwort vom Zielmodell, erfährt der Klassifikator es (nach Lauf 9b)."""
    konv = uuid4()
    bestehend = MagicMock()
    bestehend.id = konv
    bestehend.pseudonym = "pseudo-1"
    bestehend.model_used = STANDARD
    bestehend.system_prompt_snapshot = None
    bestehend.assistant_id = None
    bestehend.preview_context = None
    bestehend.is_test = False
    bestehend.vorgeschlagen = []
    bestehend.stunde_node_id = None
    db = _db()
    erste = MagicMock()
    erste.scalar_one_or_none = MagicMock(return_value=bestehend)
    allgemein = db.execute.side_effect
    aufrufe = [0]

    def _ergebnis(*a, **k):
        aufrufe[0] += 1
        return erste if aufrufe[0] == 1 else allgemein(*a, **k)

    db.execute = AsyncMock(side_effect=_ergebnis)
    with _umgebung() as (client, aufruf, _p), \
         patch("app.chat.router._vorige_weitergeleitet", new=AsyncMock(return_value=True)) as vorige:
        antwort = await chat(ChatRequest(conversation_id=konv, messages=[
            {"role": "user", "content": "Löse 3x = 9"},
            {"role": "assistant", "content": "Wodurch teilst du?"},
            {"role": "user", "content": "durch 3?"},
        ]), current_user=_person(), db=db)
        async for _ in antwort.body_iterator:
            pass
    assert vorige.await_count == 1
    assert vorige.await_args.args[1] == konv
    assert "Die vorige Nachricht war eine Aufgabe." in aufruf.await_args.args[0]
    assert client.last_json["model"] == ZIEL


@pytest.mark.asyncio
async def test_neue_konversation_fragt_nicht_nach_der_vorigen():
    with _umgebung() as (_, aufruf, _p), \
         patch("app.chat.router._vorige_weitergeleitet", new=AsyncMock(return_value=True)) as vorige:
        await _laufen(ChatRequest(messages=[{"role": "user", "content": "Löse 3x = 9"}]))
    assert vorige.await_count == 0
    assert "vorige" not in aufruf.await_args.args[0]
