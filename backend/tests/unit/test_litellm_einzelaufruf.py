"""Einzelaufruf außerhalb des Chats (0.18) — gegen einen nachgebildeten Proxy."""
import json

import httpx
import pytest

from app.litellm.einzelaufruf import einzelaufruf

NACHRICHTEN = [{"role": "user", "content": "Welche Begriffe?"}]
BUDGET_400 = {"error": {"message": "Budget has been exceeded!", "type": "budget_exceeded", "code": "400"}}


def _antwort(inhalt='{"begriffe": []}', kosten="0.00021", ende="stop"):
    return httpx.Response(200, json={"choices": [{"message": {"content": inhalt}, "finish_reason": ende}]},
                          headers={"x-litellm-response-cost": kosten})


class _Proxy:
    """Nimmt Anfragen entgegen und antwortet der Reihe nach."""

    def __init__(self, *antworten):
        self.antworten = list(antworten)
        self.anfragen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.anfragen.append(request)
        antwort = self.antworten.pop(0)
        if isinstance(antwort, Exception):
            raise antwort
        return antwort

    def rumpf(self, i=0) -> dict:
        return json.loads(self.anfragen[i].content)


async def _rufe(proxy, **kw):
    return await einzelaufruf("sk-lehrkraft", "pseudo-1", "system-begriffe", NACHRICHTEN,
                              transport=httpx.MockTransport(proxy), **kw)


@pytest.mark.asyncio
async def test_erfolg_ueber_den_schluessel_der_person():
    proxy = _Proxy(_antwort())
    a = await _rufe(proxy, json_antwort=True, max_tokens=500)

    assert a.ok and a.inhalt == '{"begriffe": []}' and a.kosten_usd == pytest.approx(0.00021)
    assert a.json_modus and a.ende == "stop"
    anfrage = proxy.anfragen[0]
    assert anfrage.headers["authorization"] == "Bearer sk-lehrkraft"
    rumpf = proxy.rumpf()
    assert rumpf["user"] == "pseudo-1" and rumpf["stream"] is False and rumpf["temperature"] == 0
    assert rumpf["response_format"] == {"type": "json_object"} and rumpf["max_tokens"] == 500


@pytest.mark.asyncio
async def test_ohne_json_modus_kein_response_format():
    proxy = _Proxy(_antwort("Text"))
    await _rufe(proxy)

    assert "response_format" not in proxy.rumpf()


@pytest.mark.asyncio
async def test_json_modus_abgelehnt_dann_ohne():
    proxy = _Proxy(httpx.Response(400, json={"error": {"message": "response_format not supported"}}), _antwort())
    a = await _rufe(proxy, json_antwort=True)

    assert a.ok and a.json_modus is False
    assert len(proxy.anfragen) == 2 and "response_format" not in proxy.rumpf(1)


@pytest.mark.asyncio
async def test_budget_als_400_ohne_zweiten_versuch():
    """LiteLLM 1.83.7 meldet ein leeres Budget mit 400 — das ist kein unbekannter JSON-Modus."""
    proxy = _Proxy(httpx.Response(400, json=BUDGET_400))
    a = await _rufe(proxy, json_antwort=True)

    assert a.fehler == "budget"
    assert len(proxy.anfragen) == 1


@pytest.mark.asyncio
async def test_budget_als_429():
    proxy = _Proxy(httpx.Response(429, json=BUDGET_400))
    assert (await _rufe(proxy)).fehler == "budget"


@pytest.mark.asyncio
async def test_drossel_429_ist_kein_budget():
    proxy = _Proxy(httpx.Response(429, json={"error": {"message": "rate limit", "type": "rate_limit"}}))
    assert (await _rufe(proxy)).fehler == "abgelehnt"


@pytest.mark.asyncio
async def test_zeitlimit():
    proxy = _Proxy(httpx.ReadTimeout("zu langsam"))
    assert (await _rufe(proxy)).fehler == "zeit"


@pytest.mark.asyncio
async def test_verbindung_weg():
    proxy = _Proxy(httpx.ConnectError("aus"))
    assert (await _rufe(proxy)).fehler == "abgelehnt"


@pytest.mark.asyncio
async def test_unlesbare_antwort():
    proxy = _Proxy(httpx.Response(200, text="<html>Proxy-Fehlerseite</html>"))
    assert (await _rufe(proxy)).fehler == "abgelehnt"


@pytest.mark.asyncio
async def test_leerer_inhalt_ist_kein_fehler():
    """Ein Modell mit Denkphase liefert bei zu kleinem max_tokens leeren Inhalt (0.17 § 29) —
    der Aufrufer sieht es an `ende`."""
    a = await _rufe(_Proxy(_antwort(inhalt=None, ende="length")))
    assert a.ok and a.inhalt == "" and a.ende == "length"


@pytest.mark.asyncio
async def test_ohne_schluessel_und_ohne_modell_kein_aufruf():
    proxy = _Proxy()
    ohne_schluessel = await einzelaufruf(None, "p", "system-begriffe", NACHRICHTEN,
                                         transport=httpx.MockTransport(proxy))
    ohne_modell = await einzelaufruf("sk", "p", "", NACHRICHTEN, transport=httpx.MockTransport(proxy))

    assert ohne_schluessel.fehler == "kein_schluessel" and ohne_modell.fehler == "kein_modell"
    assert proxy.anfragen == []
