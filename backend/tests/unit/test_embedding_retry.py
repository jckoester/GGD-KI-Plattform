"""Unit-Tests: Rate-Limits beim Embedding sind vorübergehend, nicht endgültig.

Ohne Wiederholung wird aus einem 429 ein dauerhafter `embedding_error` am Knoten — der
Knoten bleibt bis zum nächsten Backfill-Lauf ohne Vektor und fehlt so lange in der
semantischen Suche. Der Massenfall ist ein Bildungsplan-Import: Danach stehen Tausende
Knoten ohne Embedding an, und der Backfill arbeitet sie in einem Zug ab.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import settings
from app.context.embedding import generate_embedding

# Breite aus der Konfiguration, nicht fest verdrahtet: `generate_embedding` prüft die
# gelieferte Dimension gegen EMBEDDING_DIMENSIONS. Eine feste 1536 hier ließe jeden dieser
# Tests scheitern, sobald ein anderes Modell konfiguriert ist (BGE-M3: 1024) — und zwar mit
# einem EmbeddingDimensionError, der nichts mit der geprüften Wiederholungslogik zu tun hat.
VEKTOR = [0.1] * settings.embedding_dimensions


def _antwort(status: int, *, retry_after: str | None = None):
    """httpx-Antwort-Attrappe; wirft bei >=400 wie `raise_for_status`."""
    r = MagicMock()
    r.status_code = status
    r.headers = {"retry-after": retry_after} if retry_after else {}
    r.json = MagicMock(return_value={"data": [{"embedding": VEKTOR}]})

    def _raise():
        if status >= 400:
            raise httpx.HTTPStatusError(f"HTTP {status}", request=MagicMock(), response=r)

    r.raise_for_status = MagicMock(side_effect=_raise)
    return r


def _client(antworten):
    """Async-Context-Manager-Mock, der `antworten` der Reihe nach liefert."""
    folge = list(antworten)
    versuche = []

    async def _post(url, headers=None, json=None):
        versuche.append(url)
        return folge.pop(0) if len(folge) > 1 else folge[0]

    inner = MagicMock()
    inner.post = _post
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=inner)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, versuche


@pytest.fixture
def schlaf():
    """Ersetzt das Warten; sammelt die Wartezeiten, damit Tests sofort laufen."""
    zeiten = []

    async def _sleep(s):
        zeiten.append(s)

    with patch("app.context.embedding.asyncio.sleep", new=_sleep):
        yield zeiten


@pytest.fixture(autouse=True)
def standardwerte():
    """Feste Retry-Einstellungen, unabhängig von der lokalen .env."""
    alt = (settings.embedding_max_retries, settings.embedding_retry_max_wait_s)
    settings.embedding_max_retries = 3
    settings.embedding_retry_max_wait_s = 5.0
    yield
    settings.embedding_max_retries, settings.embedding_retry_max_wait_s = alt


@pytest.mark.asyncio
async def test_429_wird_wiederholt_und_gelingt(schlaf):
    """Der Kern: Ein Rate-Limit darf den Knoten nicht dauerhaft ohne Vektor lassen."""
    cm, versuche = _client([_antwort(429), _antwort(200)])
    with patch("httpx.AsyncClient", return_value=cm):
        assert await generate_embedding("Text") == VEKTOR
    assert len(versuche) == 2
    assert len(schlaf) == 1


@pytest.mark.asyncio
async def test_retry_after_schlaegt_die_schaetzung(schlaf):
    cm, _ = _client([_antwort(429, retry_after="2"), _antwort(200)])
    with patch("httpx.AsyncClient", return_value=cm):
        await generate_embedding("Text")
    assert schlaf == [2.0]


@pytest.mark.asyncio
async def test_grosses_retry_after_wird_gedeckelt(schlaf):
    """`enqueue_embedding_job` läuft inline im Request — 300s Warten ginge nicht."""
    cm, _ = _client([_antwort(429, retry_after="300"), _antwort(200)])
    with patch("httpx.AsyncClient", return_value=cm):
        await generate_embedding("Text")
    assert schlaf == [settings.embedding_retry_max_wait_s]


@pytest.mark.asyncio
async def test_http_datum_im_retry_after_faellt_auf_die_schaetzung_zurueck(schlaf):
    """Manche Anbieter schicken ein HTTP-Datum statt Sekunden."""
    cm, _ = _client([_antwort(429, retry_after="Wed, 26 Aug 2026 04:22:41 GMT"),
                     _antwort(200)])
    with patch("httpx.AsyncClient", return_value=cm):
        await generate_embedding("Text")
    assert schlaf == [1.0]


@pytest.mark.asyncio
async def test_wartezeit_waechst_exponentiell(schlaf):
    cm, _ = _client([_antwort(429), _antwort(429), _antwort(429), _antwort(200)])
    with patch("httpx.AsyncClient", return_value=cm):
        await generate_embedding("Text")
    assert schlaf == [1.0, 2.0, 4.0]


@pytest.mark.asyncio
async def test_gibt_nach_den_versuchen_auf(schlaf):
    """Endlos wiederholen wäre schlimmer: Der Backfill käme nie zum nächsten Knoten."""
    cm, versuche = _client([_antwort(429)])
    with patch("httpx.AsyncClient", return_value=cm):
        with pytest.raises(httpx.HTTPStatusError):
            await generate_embedding("Text")
    assert len(versuche) == settings.embedding_max_retries + 1


@pytest.mark.asyncio
async def test_400_wird_nicht_wiederholt(schlaf):
    """Ein falscher Parameter wiederholt sich sinnlos — sofort durchreichen."""
    cm, versuche = _client([_antwort(400)])
    with patch("httpx.AsyncClient", return_value=cm):
        with pytest.raises(httpx.HTTPStatusError):
            await generate_embedding("Text")
    assert len(versuche) == 1
    assert schlaf == []


@pytest.mark.asyncio
async def test_503_gilt_ebenfalls_als_voruebergehend(schlaf):
    cm, versuche = _client([_antwort(503), _antwort(200)])
    with patch("httpx.AsyncClient", return_value=cm):
        await generate_embedding("Text")
    assert len(versuche) == 2


@pytest.mark.asyncio
async def test_abschaltbar(schlaf):
    """`EMBEDDING_MAX_RETRIES=0` stellt das alte Verhalten wieder her."""
    settings.embedding_max_retries = 0
    cm, versuche = _client([_antwort(429)])
    with patch("httpx.AsyncClient", return_value=cm):
        with pytest.raises(httpx.HTTPStatusError):
            await generate_embedding("Text")
    assert len(versuche) == 1
    assert schlaf == []
