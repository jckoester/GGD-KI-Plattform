import os
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.chat.router import chat, router as chat_router
from app.chat.schemas import ChatRequest
from app.litellm.client import LiteLLMClient
import app.chat.router as _chat_router_mod


@pytest.fixture(autouse=True)
def _reset_model_info_cache():
    _chat_router_mod._model_info_cache = None
    yield
    _chat_router_mod._model_info_cache = None


_FAKE_LITELLM_KEY = "sk-test-key"


def _make_execute_mock(*specific_results):
    """Returns an AsyncMock for db.execute that returns specific_results in order,
    then falls back to a generic MagicMock that includes a fake litellm key."""
    call_count = [0]

    def _side_effect(*args, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(specific_results):
            return specific_results[idx]
        generic = MagicMock()
        generic.scalars.return_value.all.return_value = []
        generic.scalars.return_value.first.return_value = None
        generic.scalar_one_or_none.return_value = _FAKE_LITELLM_KEY
        generic.fetchone.return_value = None
        return generic

    return AsyncMock(side_effect=_side_effect)


def _fake_payload() -> JwtPayload:
    return JwtPayload(
        sub="pseudo-1",
        roles=["student"],
        grade="10",
        jti="jti-1",
        iat=1,
        exp=9999999999,
    )


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(chat_router)

    async def fake_current_user():
        return _fake_payload()

    app.dependency_overrides[get_current_user] = fake_current_user
    return app


def test_chat_request_model_id_is_normalized():
    request = ChatRequest(
        messages=[{"role": "user", "content": "Hallo"}],
        model_id="  openai/gpt-4o-mini  ",
    )
    assert request.model_id == "openai/gpt-4o-mini"

    empty_model = ChatRequest(
        messages=[{"role": "user", "content": "Hallo"}],
        model_id="   ",
    )
    assert empty_model.model_id is None


@pytest.mark.asyncio
async def test_litellm_list_models_parses_and_deduplicates():
    litellm_client = LiteLLMClient()
    http_client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "data": [
            {"id": "openai/gpt-4o-mini"},
            {"model_name": "openai/gpt-4.1-mini"},
            {"id": "openai/gpt-4o-mini"},
        ]
    }
    http_client.get = AsyncMock(return_value=response)

    with patch.object(litellm_client, "_get_client", new=AsyncMock(return_value=http_client)):
        models = await litellm_client.list_models()

    assert models == ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"]


def test_get_models_success():
    app = _make_app()

    with patch("app.chat.router.LiteLLMClient") as client_cls:
        client = AsyncMock()
        client.list_models.return_value = ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"]
        client.get_team_info.return_value = {"models": ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"]}
        client.get_model_info.return_value = {}
        client.close.return_value = None
        client_cls.return_value = client

        test_client = TestClient(app)
        response = test_client.get("/models")

    assert response.status_code == 200
    model_ids = [m["id"] for m in response.json()["models"]]
    assert model_ids == ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"]
    assert "default_model" in response.json()


def test_get_models_returns_502_when_litellm_fails():
    app = _make_app()

    with patch("app.chat.router.LiteLLMClient") as client_cls:
        client = AsyncMock()
        client.list_models.side_effect = RuntimeError("boom")
        client.close.return_value = None
        client_cls.return_value = client

        test_client = TestClient(app)
        response = test_client.get("/models")

    assert response.status_code == 502
    assert response.json()["detail"] == "LiteLLM Proxy nicht erreichbar"


class _FakeStreamResponse:
    status_code = 200
    # Wie die echte httpx.Response: Der Router liest `x-litellm-model-id` daraus
    # (Modell-Transparenz). Leer = Kennung unbekannt, dann greift der Alias-Rückfall.
    headers: dict = {}

    async def aiter_lines(self):
        yield "data: [DONE]"

    async def aclose(self):
        return None

    async def aread(self):
        return b""


class _FakeHttpClient:
    def __init__(self):
        self.last_json = None

    def build_request(self, method, url, headers=None, json=None):
        self.last_json = json
        return {"method": method, "url": url}

    async def send(self, request, stream=False):
        return _FakeStreamResponse()

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_post_chat_new_conversation_uses_requested_model_id():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    db.commit = AsyncMock()
    db.execute = _make_execute_mock()

    fake_http_client = _FakeHttpClient()
    request = ChatRequest(
        messages=[{"role": "user", "content": "Hallo"}],
        model_id="openai/gpt-4.1-mini",
    )

    with patch("app.chat.router.httpx.AsyncClient", return_value=fake_http_client), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "openai/gpt-4o-mini"
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3

        await chat(request, current_user=_fake_payload(), db=db)

    assert fake_http_client.last_json["model"] == "openai/gpt-4.1-mini"


@pytest.mark.asyncio
async def test_post_chat_new_conversation_without_model_uses_default():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = _make_execute_mock()
    db.flush = AsyncMock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    db.commit = AsyncMock()

    fake_http_client = _FakeHttpClient()
    request = ChatRequest(
        messages=[{"role": "user", "content": "Hallo"}],
        model_id=None,
    )

    with patch("app.chat.router.httpx.AsyncClient", return_value=fake_http_client), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "openai/gpt-4o-mini"
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3

        await chat(request, current_user=_fake_payload(), db=db)

    assert fake_http_client.last_json["model"] == "openai/gpt-4o-mini"


@pytest.mark.asyncio
async def test_post_chat_existing_conversation_without_model_uses_stored_model():
    """Wenn kein model_id übergeben, wird das gespeicherte Modell der Konversation verwendet."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()

    conversation_id = uuid4()
    existing_conv = MagicMock()
    existing_conv.id = conversation_id
    existing_conv.pseudonym = "pseudo-1"
    existing_conv.model_used = "openai/gpt-4o-mini"
    existing_conv.system_prompt_snapshot = None
    existing_conv.assistant_id = None

    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=existing_conv)

    # First call: Conversation lookup; subsequent calls use generic fallback (incl. key)
    db.execute = _make_execute_mock(result)
    db.add = MagicMock()

    fake_http_client = _FakeHttpClient()
    request = ChatRequest(
        messages=[{"role": "user", "content": "Weiter"}],
        conversation_id=conversation_id,
        model_id=None,
    )

    with patch("app.chat.router.httpx.AsyncClient", return_value=fake_http_client), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "openai/gpt-4o-mini"
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3

        await chat(request, current_user=_fake_payload(), db=db)

    assert fake_http_client.last_json["model"] == "openai/gpt-4o-mini"


# ── Der Stream muss auch WIRKLICH durchlaufen ─────────────────────────────────
#
# Die Tests oben rufen `chat(...)` auf, verbrauchen den Stream aber nie — `generate()`
# läuft darin also gar nicht. Genau dadurch blieb ein UnboundLocalError beim Persistieren
# unbemerkt: Der Chat sah normal aus, es wurde nur nichts mehr gespeichert (der Fehler
# landet bewusst nur im Log, damit eine Speicherstörung nicht die Antwort zerreißt).
#
# Dieser Test verbraucht den Stream und prüft das beobachtbare Ergebnis: die
# Nachrichten-ID kurz vor [DONE].

async def _stream_text(response) -> str:
    teile: list[str] = []
    async for teil in response.body_iterator:
        teile.append(teil.decode() if isinstance(teil, (bytes, bytearray)) else teil)
    return "".join(teile)


@pytest.mark.asyncio
async def test_stream_meldet_die_nachrichten_id_vor_done():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = _make_execute_mock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    nachricht_id = uuid4()
    request = ChatRequest(messages=[{"role": "user", "content": "Hallo"}], model_id=None)

    with patch("app.chat.router.httpx.AsyncClient", return_value=_FakeHttpClient()), \
         patch("app.chat.router._persist", new=AsyncMock(return_value=nachricht_id)) as persist, \
         patch("app.chat.router.anbietermodell", new=AsyncMock(return_value="openai/openai/gpt-oss-120b")), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "chat-standard"
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3

        response = await chat(request, current_user=_fake_payload(), db=db)
        ausgabe = await _stream_text(response)

    assert "event: message" in ausgabe, "ohne die ID kann das Frontend keine Herkunft belegen"
    assert str(nachricht_id) in ausgabe
    assert ausgabe.index("event: message") < ausgabe.index("[DONE]")
    # Das aufgelöste Anbietermodell muss beim Schreiben ankommen.
    assert persist.await_args.kwargs["provider_model"] == "openai/openai/gpt-oss-120b"


@pytest.mark.asyncio
async def test_stream_bleibt_heil_wenn_das_speichern_scheitert():
    """Eine Speicherstörung darf die Antwort nicht zerreißen — nur die ID entfällt."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = _make_execute_mock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    request = ChatRequest(messages=[{"role": "user", "content": "Hallo"}], model_id=None)

    with patch("app.chat.router.httpx.AsyncClient", return_value=_FakeHttpClient()), \
         patch("app.chat.router._persist", new=AsyncMock(side_effect=RuntimeError("DB weg"))), \
         patch("app.chat.router.anbietermodell", new=AsyncMock(return_value=None)), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "chat-standard"
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3

        response = await chat(request, current_user=_fake_payload(), db=db)
        ausgabe = await _stream_text(response)

    assert "[DONE]" in ausgabe
    assert "event: message" not in ausgabe


# ── Kontext unter der Antwort (0.14, Schritt 3) ────────────────────────────────
#
# Der Stream schickt die Liste, die die Datenbank **nach** dem Speichern liefert — dieselbe
# Abfrage wie beim Neuladen (`kontext_der_nachrichten`). Die Abfrage selbst prüft
# `tests/integration/test_kontext_unter_der_antwort.py`.

async def _chat_mit_bausteinen(bausteine, lader):
    from app.context.bausteine import Kontext

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = _make_execute_mock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    request = ChatRequest(messages=[{"role": "user", "content": "Hallo"}], model_id=None)

    with patch("app.chat.router.httpx.AsyncClient", return_value=_FakeHttpClient()), \
         patch("app.chat.router._persist", new=AsyncMock(return_value=_NACHRICHT)), \
         patch("app.chat.router.anbietermodell", new=AsyncMock(return_value=None)), \
         patch("app.chat.router.kontext_fuer_frage",
               new=AsyncMock(return_value=Kontext(text="", bausteine=bausteine))), \
         patch("app.chat.router.kontext_der_nachrichten", new=lader), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "chat-standard"
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3

        response = await chat(request, current_user=_fake_payload(), db=db)
        return await _stream_text(response)


_NACHRICHT = uuid4()


def _vorab_baustein():
    from app.context.bausteine import VORAB, Baustein
    return Baustein(str(uuid4()), "Oxidation", "begriff", "Chemie", VORAB, 0.751)


@pytest.mark.asyncio
async def test_stream_schickt_die_gespeicherte_liste_vor_der_nachrichten_id():
    import json as _json
    from app.context.bausteine import KontextBaustein

    gespeichert = KontextBaustein(node_id=uuid4(), title="Oxidation", content_type="begriff",
                                  fach="Chemie", herkunft="vorab", aehnlichkeit=0.751)
    lader = AsyncMock(return_value={_NACHRICHT: [gespeichert]})
    ausgabe = await _chat_mit_bausteinen([_vorab_baustein()], lader)

    assert "event: kontext" in ausgabe
    assert ausgabe.index("event: kontext") < ausgabe.index("event: message")
    # Gelesen für genau diese Nachricht und mit den Rechten der Person.
    assert lader.await_args.args[1:] == ([_NACHRICHT], "pseudo-1", ["student"])
    zeile = ausgabe.split("event: kontext\ndata: ", 1)[1].split("\n", 1)[0]
    assert _json.loads(zeile) == {"bausteine": [gespeichert.model_dump(mode="json")]}


@pytest.mark.asyncio
async def test_ohne_bausteine_kein_ereignis_und_keine_abfrage():
    lader = AsyncMock(return_value={})
    ausgabe = await _chat_mit_bausteinen([], lader)
    assert "event: kontext" not in ausgabe
    lader.assert_not_awaited()


@pytest.mark.asyncio
async def test_leere_gespeicherte_liste_gibt_kein_ereignis():
    """Alle Bausteine inzwischen gelöscht oder unlesbar — dann keine leere Zeile."""
    ausgabe = await _chat_mit_bausteinen([_vorab_baustein()], AsyncMock(return_value={}))
    assert "event: kontext" not in ausgabe
    assert "event: message" in ausgabe


@pytest.mark.asyncio
async def test_fehler_beim_lesen_der_liste_zerreisst_den_stream_nicht():
    lader = AsyncMock(side_effect=RuntimeError("DB weg"))
    ausgabe = await _chat_mit_bausteinen([_vorab_baustein()], lader)
    assert "event: kontext" not in ausgabe
    assert "event: message" in ausgabe and "[DONE]" in ausgabe


# ── Erschöpftes Budget im Chat ──────────────────────────────────────────────────────
#
# LiteLLM 1.83.7 meldet es als HTTP **400** mit `type: budget_exceeded` (gemessen
# 29.08.2026). Der Router prüfte auf 429; die Ablehnung fiel deshalb in den allgemeinen
# Zweig und die Nutzerin bekam den rohen Fehlerkörper als Fehlermeldung zu sehen —
# englisch, mit Beträgen in wissenschaftlicher Notation.

_BUDGET_KOERPER = (
    b'{"error":{"message":"Budget has been exceeded! Current cost: '
    b'2.6269999999999998e-05, Max budget: 2e-05","type":"budget_exceeded",'
    b'"param":null,"code":"400"}}'
)


class _AblehnungsResponse:
    """Antwort des Proxys mit frei wählbarem Status und Körper."""

    headers: dict = {}

    def __init__(self, status_code, koerper):
        self.status_code = status_code
        self._koerper = koerper

    async def aiter_lines(self):
        yield "data: [DONE]"

    async def aclose(self):
        return None

    async def aread(self):
        return self._koerper


class _AblehnendeHttpClient(_FakeHttpClient):
    def __init__(self, status_code, koerper):
        super().__init__()
        self._antwort = _AblehnungsResponse(status_code, koerper)

    async def send(self, request, stream=False):
        return self._antwort


async def _chat_mit_ablehnung(status_code, koerper):
    from fastapi import HTTPException

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = _make_execute_mock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    request = ChatRequest(messages=[{"role": "user", "content": "Hallo"}], model_id=None)

    with patch("app.chat.router.httpx.AsyncClient",
               return_value=_AblehnendeHttpClient(status_code, koerper)), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "chat-standard"
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3

        with pytest.raises(HTTPException) as exc:
            await chat(request, current_user=_fake_payload(), db=db)
    return exc.value


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 429])
async def test_erschoepftes_budget_wird_verstaendlich_gemeldet(status):
    """Beide Status, dieselbe Auskunft — entscheidend ist der Fehlertyp im Körper."""
    fehler = await _chat_mit_ablehnung(status, _BUDGET_KOERPER)

    assert fehler.status_code == 429
    assert "aufgebraucht" in fehler.detail
    assert "nächsten Abrechnungszeitraum" in fehler.detail


@pytest.mark.asyncio
async def test_der_rohe_fehlerkoerper_erreicht_die_oberflaeche_nicht():
    """Kein Englisch, keine Beträge, kein JSON — das gehört ins Log."""
    fehler = await _chat_mit_ablehnung(400, _BUDGET_KOERPER)

    assert "Budget has been exceeded" not in fehler.detail
    assert "2e-05" not in fehler.detail
    assert "{" not in fehler.detail


@pytest.mark.asyncio
async def test_drosselung_wird_nicht_als_budget_ausgegeben():
    """Der Gegenfall: 429 ohne Budget-Typ darf keine Budgetmeldung erzeugen."""
    koerper = (
        b'{"error":{"message":"Rate limit reached","type":"rate_limit_error",'
        b'"code":"429"}}'
    )
    fehler = await _chat_mit_ablehnung(429, koerper)

    assert "aufgebraucht" not in fehler.detail


# ── Der Stream wartet nicht mehr auf die Kosten ───────────────────────────────

@pytest.mark.asyncio
async def test_stream_haelt_nicht_fuer_die_kostenermittlung_an(monkeypatch):
    """Der eigentliche Punkt von AP2: `[DONE]` kommt, wenn der Text steht.

    Bis 09/2026 lief `_kosten_des_zuges` **im** Generator und hielt ihn gestaffelt
    bis zu 15 s auf, nachdem das letzte Zeichen der Antwort da war. Hier wird eine
    Wartezeit gesetzt, die deutlich über allem liegt, was ein Test dulden würde —
    kommt `[DONE]` trotzdem sofort, wird sie nicht mehr abgewartet.
    """
    import asyncio
    import time

    from app.chat import kosten_nachtrag

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = _make_execute_mock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    request = ChatRequest(messages=[{"role": "user", "content": "Hallo"}], model_id=None)

    # ⚠️ Ohne eine Chunk-Id sammelt der Router keine `_request_ids`, und der ganze
    # Kostenpfad wird übersprungen — der Test liefe dann grün, ohne je durch die
    # geprüfte Stelle zu kommen. (Genau so gebaut und von der Gegenprobe
    # widerlegt, 09.09.2026.)
    class _MitRequestId(_FakeStreamResponse):
        async def aiter_lines(self):
            yield 'data: {"id": "req-1", "choices": [{"delta": {"content": "Hi"}, ' \
                  '"finish_reason": "stop"}]}'
            yield "data: [DONE]"

    class _ClientMitRequestId(_FakeHttpClient):
        async def send(self, *a, **kw):
            return _MitRequestId()

    gestartet: list = []
    monkeypatch.setattr(
        kosten_nachtrag, "nachtragen",
        lambda *a, **kw: gestartet.append(kw) or MagicMock(),
    )
    # 60 s je Stufe: Würde noch gewartet, liefe der Test in seinen Timeout.
    monkeypatch.setattr("app.chat.router._SPEND_LOG_WARTEZEITEN", (60.0, 60.0))

    with patch("app.chat.router.httpx.AsyncClient", return_value=_ClientMitRequestId()), \
         patch("app.chat.router._persist", new=AsyncMock(return_value=uuid4())), \
         patch("app.chat.router.anbietermodell", new=AsyncMock(return_value=None)), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "chat-standard"
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3

        response = await chat(request, current_user=_fake_payload(), db=db)
        start = time.monotonic()
        # Frist statt bloßer Messung: Bei einer Rückkehr der Staffel liefe der Test
        # sonst 120 s und **hinge**, statt zu scheitern. Ein hängender Test ist
        # schlechter als ein fallender — er sieht nach Infrastruktur aus.
        try:
            ausgabe = await asyncio.wait_for(_stream_text(response), timeout=5.0)
        except asyncio.TimeoutError:
            pytest.fail(
                "Der Stream war nach 5 s nicht fertig — die Kostenstaffel wird "
                "wieder im Generator abgewartet."
            )
        dauer = time.monotonic() - start

    assert "[DONE]" in ausgabe
    assert dauer < 5.0, f"Der Stream hat {dauer:.1f}s gewartet — die Staffel läuft noch mit"
    # Und das alte Kosten-Ereignis ist weg: Der Betrag steht beim Streamende nicht fest.
    assert "event: cost" not in ausgabe
    # Der Nachtrag wurde beauftragt — sonst käme der Betrag nie an.
    assert gestartet, "kein Kosten-Nachtrag gestartet"
    assert gestartet[0]["request_ids"] == ["req-1"]


# ── Rundenlimit und abgerissener Strom (0.15) ─────────────────────────────────
#
# Rundenlimit: Die Anfrage nach dem letzten erlaubten Werkzeugaufruf geht ohne Werkzeuge
# hinaus. Vorher endete ein Zug, in dem das Modell noch ein Werkzeug wollte, ohne Antwort.
# Abriss: Stockt der Strom, greift der Lese-Timeout; der Zug wird gespeichert und endet mit
# einer lesbaren Meldung statt eines abgerissenen Stroms.

import httpx as _httpx  # noqa: E402

from app.chat.tools import ChatTool  # noqa: E402


def _zeile(delta: dict, finish: str | None = None, rid: str = "req-1") -> str:
    import json as _json
    return "data: " + _json.dumps(
        {"id": rid, "choices": [{"delta": delta, "finish_reason": finish}]}
    )


class _Strom(_FakeStreamResponse):
    """Feste Zeilen; ``fehler`` fällt danach, wie ein Abriss mitten im Strom."""

    def __init__(self, zeilen, fehler=None):
        self._zeilen = zeilen
        self._fehler = fehler

    async def aiter_lines(self):
        for z in self._zeilen:
            yield z
        if self._fehler is not None:
            raise self._fehler
        yield "data: [DONE]"


def _werkzeugaufruf(name: str = "probe") -> _Strom:
    return _Strom([_zeile(
        {"tool_calls": [{"id": "call-1", "function": {"name": name, "arguments": "{}"}}]},
        "tool_calls",
    )])


def _text(text: str) -> _Strom:
    return _Strom([_zeile({"content": text}, "stop")])


class _Modell(_FakeHttpClient):
    """Merkt sich jede Nutzlast; ``antwort`` entscheidet je Anfrage, was zurückkommt."""

    def __init__(self, antwort):
        super().__init__()
        self.nutzlasten: list[dict] = []
        self._antwort = antwort

    def build_request(self, method, url, headers=None, json=None):
        self.nutzlasten.append(json)
        return json

    async def send(self, request, stream=False):
        return self._antwort(request, len(self.nutzlasten))


async def _chat_mit_werkzeug(modell, ergebnis=None):
    """Ein Chat mit genau einem Werkzeug `probe`; liefert Ausgabe, Aufrufe und `_persist`."""
    aufrufe: list = []

    async def _probe(args, ctx):
        aufrufe.append(args)
        return ergebnis if ergebnis is not None else {"ok": True}

    probe = ChatTool(
        name="probe", groups=frozenset({"planning"}), handler=_probe,
        definition={"type": "function", "function": {
            "name": "probe", "parameters": {"type": "object", "properties": {}}}},
    )
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = _make_execute_mock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    persist = AsyncMock(return_value=uuid4())
    request = ChatRequest(messages=[{"role": "user", "content": "Hallo"}], model_id=None)

    with patch("app.chat.router.httpx.AsyncClient", return_value=modell), \
         patch("app.chat.router.tools_for", return_value=[probe]), \
         patch("app.chat.router._get_model_info", new=AsyncMock(return_value={})), \
         patch("app.chat.router._persist", new=persist), \
         patch("app.chat.router.anbietermodell", new=AsyncMock(return_value=None)), \
         patch("app.chat.router.kosten_nachtrag.nachtragen"), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "chat-standard"
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3

        response = await chat(request, current_user=_fake_payload(), db=db)
        ausgabe = await _stream_text(response)
    return ausgabe, aufrufe, persist


def _ist_hinweis(nachricht: dict) -> bool:
    from app.chat.router import _RUNDENLIMIT_HINWEIS
    return nachricht == {"role": "user", "content": _RUNDENLIMIT_HINWEIS}


@pytest.mark.asyncio
async def test_am_rundenlimit_antwortet_das_modell():
    """Das Modell will ein Werkzeug, solange es nicht ausdrücklich zum Antworten
    aufgefordert wird — wie gpt-oss, das `tool_choice: "none"` übergeht."""
    from app.chat.router import _MAX_TOOL_ROUNDS

    modell = _Modell(
        lambda req, n: _text("Fertig.") if _ist_hinweis(req["messages"][-1]) else _werkzeugaufruf()
    )
    ausgabe, aufrufe, persist = await _chat_mit_werkzeug(modell)

    assert len(aufrufe) == _MAX_TOOL_ROUNDS
    assert "Fertig." in ausgabe
    assert persist.await_args.args[4] == "Fertig."
    *vorher, letzte = modell.nutzlasten
    assert all(n.get("tool_choice") == "auto" for n in vorher)
    # `tools` bleibt: Anthropic lehnt einen Verlauf mit Werkzeugaufrufen ohne sie ab.
    assert "tools" in letzte and letzte["tool_choice"] == "none"
    # Der Hinweis ist eine eigene Nachricht hinter dem letzten Werkzeugergebnis — im
    # Ergebnis selbst übergeht ihn gpt-oss.
    assert letzte["messages"][-2]["role"] == "tool"
    assert not any(_ist_hinweis(m) for n in vorher for m in n["messages"])


@pytest.mark.asyncio
async def test_am_rundenlimit_wird_einmal_wiederholt():
    """gpt-oss ruft in rund einem von acht Fällen trotz `tool_choice: "none"` und Hinweis
    ein Werkzeug. Dann wird nichts ausgeführt, dieselbe Anfrage geht einmal neu hinaus."""
    from app.chat.router import _MAX_TOOL_ROUNDS

    versuche = []

    def _antwort(req, n):
        if not _ist_hinweis(req["messages"][-1]):
            return _werkzeugaufruf()
        versuche.append(req)
        return _werkzeugaufruf() if len(versuche) == 1 else _text("Fertig.")

    ausgabe, aufrufe, persist = await _chat_mit_werkzeug(_Modell(_antwort))

    assert len(aufrufe) == _MAX_TOOL_ROUNDS, "der Aufruf in der letzten Anfrage läuft nicht"
    assert len(versuche) == 2 and versuche[0] == versuche[1]
    assert "Fertig." in ausgabe and persist.await_args.args[4] == "Fertig."


@pytest.mark.asyncio
async def test_am_rundenlimit_hoechstens_eine_wiederholung():
    from app.chat.router import _MAX_TOOL_ROUNDS

    modell = _Modell(lambda req, n: _werkzeugaufruf())
    ausgabe, aufrufe, _ = await _chat_mit_werkzeug(modell)

    assert len(aufrufe) == _MAX_TOOL_ROUNDS
    # Erste Anfrage, eine je Werkzeugaufruf, eine Wiederholung — dann ist Schluss.
    assert len(modell.nutzlasten) == _MAX_TOOL_ROUNDS + 2
    assert "[DONE]" in ausgabe


@pytest.mark.asyncio
async def test_unter_dem_rundenlimit_bleiben_die_werkzeuge():
    modell = _Modell(lambda req, n: _werkzeugaufruf() if n <= 2 else _text("Fertig."))
    ausgabe, aufrufe, _ = await _chat_mit_werkzeug(modell)

    assert len(aufrufe) == 2 and "Fertig." in ausgabe
    assert all("tools" in n for n in modell.nutzlasten)
    assert not any(_ist_hinweis(m) for n in modell.nutzlasten for m in n["messages"])


def _fehlerereignis(ausgabe: str) -> str:
    import json as _json
    zeile = ausgabe.split("event: fehler\ndata: ", 1)[1].split("\n", 1)[0]
    return _json.loads(zeile)["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("fehler, meldung", [
    (_httpx.ReadTimeout("timed out"), "_ABBRUCH_ZEIT"),
    (_httpx.RemoteProtocolError("peer closed connection"), "_ABBRUCH_VERBINDUNG"),
])
async def test_abriss_im_strom_wird_gespeichert_und_gemeldet(fehler, meldung):
    import app.chat.router as r

    modell = _Modell(lambda req, n: _Strom([_zeile({"content": "Ein Teil"})], fehler=fehler))
    ausgabe, _, persist = await _chat_mit_werkzeug(modell)

    assert "Ein Teil" in ausgabe
    assert _fehlerereignis(ausgabe) == getattr(r, meldung)
    # Nach der Nachrichten-ID, vor [DONE]: Die Oberfläche bricht beim Fehler ab.
    assert ausgabe.index("event: message") < ausgabe.index("event: fehler") < ausgabe.index("[DONE]")
    assert persist.await_args.args[4] == "Ein Teil"
    # Auch die abgerissene Runde wird zur Abrechnung angemeldet.
    assert persist.await_args.kwargs["cost_status"] == "ausstehend"


@pytest.mark.asyncio
async def test_abriss_beim_start_der_naechsten_runde():
    """Der Timeout kann auch beim Warten auf die nächste Werkzeugrunde fallen."""
    import app.chat.router as r

    class _Abreissend(_Modell):
        async def send(self, request, stream=False):
            if len(self.nutzlasten) > 1:
                raise _httpx.ReadTimeout("timed out")
            return _werkzeugaufruf()

    ausgabe, aufrufe, persist = await _chat_mit_werkzeug(_Abreissend(None))

    assert len(aufrufe) == 1
    assert _fehlerereignis(ausgabe) == r._ABBRUCH_ZEIT
    assert persist.await_count == 1


@pytest.mark.asyncio
async def test_ohne_abriss_kein_fehlerereignis():
    ausgabe, _, _ = await _chat_mit_werkzeug(_Modell(lambda req, n: _text("Fertig.")))
    assert "event: fehler" not in ausgabe


@pytest.mark.asyncio
async def test_timeout_vor_dem_strom_wird_lesbar_gemeldet():
    import app.chat.router as r

    class _Stumm(_FakeHttpClient):
        async def send(self, request, stream=False):
            raise _httpx.ReadTimeout("timed out")

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = _make_execute_mock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    request = ChatRequest(messages=[{"role": "user", "content": "Hallo"}], model_id=None)

    from fastapi import HTTPException
    with patch("app.chat.router.httpx.AsyncClient", return_value=_Stumm()), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "chat-standard"
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3

        with pytest.raises(HTTPException) as exc:
            await chat(request, current_user=_fake_payload(), db=db)

    assert exc.value.status_code == 504
    assert exc.value.detail == r._ABBRUCH_ZEIT


def test_der_strom_hat_einen_lese_timeout():
    """`read=None` hieß: Stockt LiteLLM, hängt die Anfrage unbegrenzt (Messung 3 zu 0.15)."""
    from app.chat.router import _LITELLM_TIMEOUT

    assert _LITELLM_TIMEOUT.read is not None and 0 < _LITELLM_TIMEOUT.read <= 300


# ── Erfundener Werkzeugname (0.15) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_erfundenes_werkzeug_bekommt_die_verfuegbaren_namen():
    """chat-standard rief `find_stunde` statt `finde_stunde` — bis 10/2026 endete der Zug
    dann ohne Antwort. Jetzt erfährt das Modell die richtigen Namen und kann weitermachen."""
    def _antwort(req, n):
        letzte = req["messages"][-1]
        if letzte.get("role") == "tool" and "find_probe" in letzte["content"]:
            assert "gibt es nicht" in letzte["content"] and "probe" in letzte["content"]
            return _werkzeugaufruf("probe")
        if letzte.get("role") == "tool":
            return _text("Fertig.")
        return _werkzeugaufruf("find_probe")

    ausgabe, aufrufe, persist = await _chat_mit_werkzeug(_Modell(_antwort))

    assert len(aufrufe) == 1, "das richtige Werkzeug lief genau einmal, das erfundene nie"
    assert "Fertig." in ausgabe
    assert persist.await_args.args[4] == "Fertig."


@pytest.mark.asyncio
async def test_nicht_serialisierbares_ergebnis_reisst_den_strom_nicht_ab():
    """`get_plan_balance` lieferte eine UUID; `json.dumps` scheiterte nach dem `try` um den
    Aufruf, und der Strom brach ohne Meldung ab (11.10.2026). Jetzt erfährt das Modell den
    Fehler und antwortet."""
    gesehen = []

    def _antwort(req, n):
        letzte = req["messages"][-1]
        if letzte.get("role") == "tool":
            gesehen.append(letzte["content"])
            return _text("Fertig.")
        return _werkzeugaufruf("probe")

    ausgabe, aufrufe, persist = await _chat_mit_werkzeug(_Modell(_antwort), ergebnis={"id": uuid4()})

    assert len(aufrufe) == 1
    assert gesehen and "fehlgeschlagen" in gesehen[0]
    assert "Fertig." in ausgabe
    assert persist.await_args.args[4] == "Fertig."


def test_ohne_werkzeuge_sagt_der_ersatz_das():
    import asyncio
    from app.chat.router import _unbekanntes_werkzeug

    ergebnis = asyncio.run(_unbekanntes_werkzeug("probe", []).handler({}, None))
    assert "keine Werkzeuge" in ergebnis["error"]


# ── Abgelehnte Folgeanfrage (0.15) ──────────────────────────────────────────────
#
# Nur die erste Anfrage eines Zuges prüfte den Status. Lehnte LiteLLM eine spätere Runde
# ab, las die Schleife den Fehlerkörper als Strom: leere Antwort, keine Meldung.

@pytest.mark.asyncio
@pytest.mark.parametrize("status, koerper, meldung", [
    (400, _BUDGET_KOERPER, "BUDGET_MELDUNG"),
    (500, b'{"error":{"message":"Internal Server Error","code":"500"}}', "_ABBRUCH_ABGELEHNT"),
])
async def test_abgelehnte_folgeanfrage_wird_gemeldet(status, koerper, meldung):
    import app.chat.router as r

    modell = _Modell(lambda req, n: _werkzeugaufruf() if n == 1 else _AblehnungsResponse(status, koerper))
    ausgabe, aufrufe, persist = await _chat_mit_werkzeug(modell)

    assert len(aufrufe) == 1
    assert _fehlerereignis(ausgabe) == getattr(r, meldung)
    # Der Fehlerkörper gehört ins Log, nicht in den Strom.
    assert "Internal Server Error" not in ausgabe and "Budget has been exceeded" not in ausgabe
    assert persist.await_count == 1
    assert ausgabe.index("event: fehler") < ausgabe.index("[DONE]")


# ── Text aus mehreren Runden (0.15) ─────────────────────────────────────────────
#
# Schreibt ein Modell vor einem Werkzeugaufruf schon Text (Anthropic tut das), hing der Text
# der nächsten Runde ohne Trenner daran: „…13.10.2026.Ich habe die Stunde gefunden".

def _tokens(ausgabe: str) -> str:
    """Der Antworttext, wie ihn die Oberfläche zusammensetzt — nur Blöcke ohne `event:`."""
    import json as _json
    text = []
    for block in ausgabe.split("\n\n"):
        if block.startswith("data: ") and block != "data: [DONE]":
            try:
                text.append(_json.loads(block[6:])["choices"][0]["delta"].get("content") or "")
            except (ValueError, KeyError, IndexError):
                pass
    return "".join(text)


def _text_und_aufruf(text: str) -> _Strom:
    return _Strom([
        _zeile({"content": text}),
        _zeile({"tool_calls": [{"id": "call-1", "function": {"name": "probe", "arguments": "{}"}}]},
               "tool_calls"),
    ])


@pytest.mark.asyncio
@pytest.mark.parametrize("vorher, erwartet", [
    ("Ich suche.", "Ich suche.\n\nGefunden."),
    ("Ich suche.\n", "Ich suche.\n\nGefunden."),
    ("Ich suche.\n\n", "Ich suche.\n\nGefunden."),
])
async def test_text_der_naechsten_runde_beginnt_als_absatz(vorher, erwartet):
    modell = _Modell(lambda req, n: _text_und_aufruf(vorher) if n == 1 else _text("Gefunden."))
    ausgabe, _, persist = await _chat_mit_werkzeug(modell)

    assert _tokens(ausgabe) == erwartet
    # Gespeichert wie gestreamt — sonst sähe die Antwort nach dem Neuladen anders aus.
    assert persist.await_args.args[4] == erwartet


@pytest.mark.asyncio
async def test_ohne_text_vor_dem_aufruf_kein_trenner():
    modell = _Modell(lambda req, n: _werkzeugaufruf() if n == 1 else _text("Gefunden."))
    ausgabe, _, persist = await _chat_mit_werkzeug(modell)

    assert _tokens(ausgabe) == "Gefunden."
    assert persist.await_args.args[4] == "Gefunden."


# ── Messkanal der Vorab-Suche (0.16, Schritt 3b) ──────────────────────────────
#
# Angebot, Werkzeugergebnis und Suchanfrage desselben Zuges — nur außerhalb der Produktion.
# Die Form des Ereignisses prüft `test_vorab_angebot.py`; hier die Verdrahtung im Strom.

async def _chat_mit_angebot(umgebung: str):
    from app.context.bausteine import WERKZEUG, Angebot, Kontext, aus_treffern

    angebot = [Angebot("n-1", "Elektronegativität", "Chemie", "nennung"),
               Angebot("n-2", "Gruppenpuzzle", None, "distanz")]

    async def _suche(args, ctx):
        ctx.bausteine.extend(aus_treffern([{"node_id": "n-1", "title": "Elektronegativität"}],
                                          WERKZEUG))
        return {"exakte_namenstraeger": []}

    suche = ChatTool(
        name="search_context_nodes", groups=frozenset({"context_search"}), handler=_suche,
        definition={"type": "function", "function": {
            "name": "search_context_nodes", "parameters": {"type": "object", "properties": {}}}},
    )
    aufruf = _Strom([_zeile({"tool_calls": [{"id": "call-1", "function": {
        "name": "search_context_nodes", "arguments": '{"query": "Elektronegativität"}'}}]},
        "tool_calls")])
    modell = _Modell(lambda req, n: aufruf if n == 1 else _text("Fertig."))
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = _make_execute_mock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    request = ChatRequest(messages=[{"role": "user", "content": "Hallo"}], model_id=None)

    with patch("app.chat.router.httpx.AsyncClient", return_value=modell), \
         patch("app.chat.router.tools_for", return_value=[suche]), \
         patch("app.chat.router._get_model_info", new=AsyncMock(return_value={})), \
         patch("app.chat.router.kontext_fuer_frage",
               new=AsyncMock(return_value=Kontext(text="", angebot=angebot))), \
         patch("app.chat.router.kontext_der_nachrichten", new=AsyncMock(return_value={})), \
         patch("app.chat.router._persist", new=AsyncMock(return_value=uuid4())), \
         patch("app.chat.router.anbietermodell", new=AsyncMock(return_value=None)), \
         patch("app.chat.router.kosten_nachtrag.nachtragen"), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "chat-standard"
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3
        mock_settings.environment = umgebung

        response = await chat(request, current_user=_fake_payload(), db=db)
        return await _stream_text(response)


@pytest.mark.asyncio
async def test_messkanal_traegt_angebot_ergebnis_und_suchanfrage():
    import json as _json

    ausgabe = await _chat_mit_angebot("development")
    zeile = ausgabe.split("event: vorab_debug\ndata: ", 1)[1].split("\n", 1)[0]
    daten = _json.loads(zeile)
    assert [a["node_id"] for a in daten["angebot"]] == ["n-1", "n-2"]
    assert daten["nachgeschlagen"] == ["n-1"]
    assert daten["suchanfragen"] == ["Elektronegativität"]
    assert ausgabe.index("event: vorab_debug") < ausgabe.index("event: message")


@pytest.mark.asyncio
async def test_messkanal_nie_in_der_produktion_auch_nicht_im_strom():
    ausgabe = await _chat_mit_angebot("production")
    assert "vorab_debug" not in ausgabe
    assert "Fertig." in ausgabe


# ── Vorab-Statistik (0.16, Schritt 3c) ────────────────────────────────────────

async def _chat_zaehlt(is_test: bool):
    from app.context.bausteine import Angebot, Kontext

    kontext = Kontext(text="", angebot=[Angebot("n-1", "Ion", "Chemie", "distanz")], subject_id=7)
    zaehlen = AsyncMock()
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = _make_execute_mock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    request = ChatRequest(messages=[{"role": "user", "content": "Hallo"}], model_id=None,
                          is_test=is_test)
    with patch("app.chat.router.httpx.AsyncClient", return_value=_FakeHttpClient()), \
         patch("app.chat.router._persist", new=AsyncMock(return_value=_NACHRICHT)), \
         patch("app.chat.router.anbietermodell", new=AsyncMock(return_value=None)), \
         patch("app.chat.router.kontext_fuer_frage", new=AsyncMock(return_value=kontext)), \
         patch("app.chat.router.kontext_der_nachrichten", new=AsyncMock(return_value={})), \
         patch("app.chat.router.vorab_zaehlen", new=zaehlen), \
         patch("app.chat.router.settings") as mock_settings:
        mock_settings.chat_default_model = "chat-standard"
        mock_settings.litellm_verify_ssl = True
        mock_settings.title_model = ""
        mock_settings.litellm_proxy_url = "http://litellm:4000"
        mock_settings.litellm_master_key = "test-key"
        mock_settings.upload_max_files = 3
        mock_settings.environment = "development"

        response = await chat(request, current_user=_fake_payload(), db=db)
        ausgabe = await _stream_text(response)
    return zaehlen, kontext, ausgabe


@pytest.mark.asyncio
async def test_antwort_wird_gezaehlt():
    zaehlen, kontext, ausgabe = await _chat_zaehlt(is_test=False)
    zaehlen.assert_awaited_once()
    kw = zaehlen.await_args.kwargs
    assert kw["kontext"] is kontext and kw["gesucht"] is False and kw["modell"] == "chat-standard"
    assert "[DONE]" in ausgabe


@pytest.mark.asyncio
async def test_vorschau_zaehlt_nicht():
    """ADR-016: Der Vorschaumodus des Editors ist kein Betrieb."""
    zaehlen, _, ausgabe = await _chat_zaehlt(is_test=True)
    zaehlen.assert_not_awaited()
    assert "[DONE]" in ausgabe


# ── Parallele Werkzeugaufrufe (27.10.2026) ────────────────────────────────────
#
# Claude ruft in einer Runde zwei Werkzeuge zugleich auf; die Teile kommen verschachtelt,
# unterschieden nur durch `index`. Bis 10/2026 verschmolz der Router sie zu einem Aufruf
# (`{…}{…}`) — das Werkzeug scheiterte, der Anbieter wies die Folgeanfrage ab.


def _zwei_parallele_aufrufe() -> _Strom:
    return _Strom([
        _zeile({"tool_calls": [{"index": 0, "id": "call-a",
                                "function": {"name": "probe", "arguments": '{"x":'}}]}),
        _zeile({"tool_calls": [{"index": 1, "id": "call-b",
                                "function": {"name": "probe", "arguments": '{"y": 2}'}}]}),
        _zeile({"tool_calls": [{"index": 0, "function": {"arguments": " 1}"}}]}, "tool_calls"),
    ])


async def test_parallele_werkzeugaufrufe_werden_getrennt_ausgefuehrt():
    modell = _Modell(lambda req, n: _zwei_parallele_aufrufe() if n == 1 else _text("Fertig."))
    ausgabe, aufrufe, _ = await _chat_mit_werkzeug(modell)

    assert aufrufe == [{"x": 1}, {"y": 2}]
    folge = modell.nutzlasten[1]["messages"]
    assistent = [m for m in folge if m.get("role") == "assistant" and m.get("tool_calls")]
    assert len(assistent) == 1
    assert [c["id"] for c in assistent[0]["tool_calls"]] == ["call-a", "call-b"]
    assert [c["function"]["arguments"] for c in assistent[0]["tool_calls"]] == ['{"x": 1}', '{"y": 2}']
    antworten = [m for m in folge if m.get("role") == "tool"]
    assert [m["tool_call_id"] for m in antworten] == ["call-a", "call-b"]
    assert "Fertig." in ausgabe


async def test_aufruf_ohne_index_wie_bisher():
    """Manche Anbieter senden kein `index` — dann bleibt es bei einem Aufruf."""
    modell = _Modell(lambda req, n: _werkzeugaufruf() if n == 1 else _text("Ok."))
    _, aufrufe, _ = await _chat_mit_werkzeug(modell)
    assert aufrufe == [{}]
    folge = modell.nutzlasten[1]["messages"]
    assert [m["tool_call_id"] for m in folge if m.get("role") == "tool"] == ["call-1"]
