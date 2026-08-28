"""Stapelverarbeitung beim Einbetten.

Ein Aufruf je Knoten macht aus dem Re-Embedding des Bildungsplans (~14.000 Knoten) einen
mehrstündigen Lauf. Im Stapel sind es Minuten — aber die Stapelverarbeitung bringt zwei
Fehlerarten mit, die **still** wären:

  1. Ein vertauschter Vektor. Die Antwort trägt `index`; verlässt man sich stattdessen auf
     die Listenreihenfolge, bekommt ein Knoten den Vektor eines anderen. Es wird nichts
     geworfen, die semantische Suche wird nur schlechter.
  2. Ein einziger unbrauchbarer Text, der den ganzen Stapel mitreißt — 31 gute Knoten
     bekämen einen `embedding_error`, obwohl nur einer schuld ist.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import settings
from app.context.embedding import (
    EmbeddingDimensionError,
    EmbeddingResponseError,
    _batch_timeout,
    generate_embedding,
    generate_embeddings,
)

DIM = settings.embedding_dimensions


def _vektor(fuell: float) -> list[float]:
    return [fuell] * DIM


def _antwort(eintraege: list[dict], status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.headers = {}
    r.json = MagicMock(return_value={"data": eintraege})
    r.raise_for_status = MagicMock()
    return r


def _client(response):
    cm = MagicMock()
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, client


@pytest.mark.asyncio
async def test_leere_liste_ohne_anfrage():
    """Kein Text → kein Aufruf. Ein leerer `input` wäre bei BGE-M3 ein 400."""
    with patch("httpx.AsyncClient") as ac:
        assert await generate_embeddings([]) == []
    ac.assert_not_called()


@pytest.mark.asyncio
async def test_alle_texte_in_einer_anfrage():
    cm, client = _client(_antwort([
        {"index": 0, "embedding": _vektor(0.1)},
        {"index": 1, "embedding": _vektor(0.2)},
        {"index": 2, "embedding": _vektor(0.3)},
    ]))
    with patch("httpx.AsyncClient", return_value=cm):
        vektoren = await generate_embeddings(["a", "b", "c"])

    assert client.post.await_count == 1, "drei Texte müssen EINE Anfrage sein"
    assert client.post.await_args.kwargs["json"]["input"] == ["a", "b", "c"]
    assert [v[0] for v in vektoren] == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_reihenfolge_folgt_index_nicht_der_liste():
    """Der eigentliche Prüfstein: vertauschte Antwort, richtige Zuordnung."""
    cm, _ = _client(_antwort([
        {"index": 2, "embedding": _vektor(0.3)},
        {"index": 0, "embedding": _vektor(0.1)},
        {"index": 1, "embedding": _vektor(0.2)},
    ]))
    with patch("httpx.AsyncClient", return_value=cm):
        vektoren = await generate_embeddings(["a", "b", "c"])

    assert [v[0] for v in vektoren] == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_unvollstaendige_antwort_wird_verworfen():
    """Zwei Vektoren für drei Texte: Ohne 1:1-Zuordnung darf NICHTS übernommen werden."""
    cm, _ = _client(_antwort([
        {"index": 0, "embedding": _vektor(0.1)},
        {"index": 1, "embedding": _vektor(0.2)},
    ]))
    with patch("httpx.AsyncClient", return_value=cm):
        with pytest.raises(EmbeddingResponseError, match="2 Vektoren"):
            await generate_embeddings(["a", "b", "c"])


@pytest.mark.asyncio
async def test_luecke_in_den_indizes_wird_verworfen():
    """Richtige Anzahl, aber Index 1 fehlt — die Zuordnung wäre geraten."""
    cm, _ = _client(_antwort([
        {"index": 0, "embedding": _vektor(0.1)},
        {"index": 2, "embedding": _vektor(0.2)},
        {"index": 3, "embedding": _vektor(0.3)},
    ]))
    with patch("httpx.AsyncClient", return_value=cm):
        with pytest.raises(EmbeddingResponseError, match="Indizes"):
            await generate_embeddings(["a", "b", "c"])


@pytest.mark.asyncio
async def test_ohne_index_gilt_die_listenreihenfolge():
    """Nicht jeder Anbieter schickt `index` — dann bleibt nur die Reihenfolge."""
    cm, _ = _client(_antwort([
        {"embedding": _vektor(0.1)},
        {"embedding": _vektor(0.2)},
    ]))
    with patch("httpx.AsyncClient", return_value=cm):
        vektoren = await generate_embeddings(["a", "b"])

    assert [v[0] for v in vektoren] == [0.1, 0.2]


@pytest.mark.asyncio
async def test_teils_indiziert_ist_ein_fehler():
    """Halb mit, halb ohne `index`: Hier lässt sich nicht entscheiden, was gilt."""
    cm, _ = _client(_antwort([
        {"index": 1, "embedding": _vektor(0.1)},
        {"embedding": _vektor(0.2)},
    ]))
    with patch("httpx.AsyncClient", return_value=cm):
        with pytest.raises(EmbeddingResponseError, match="unindizierte"):
            await generate_embeddings(["a", "b"])


@pytest.mark.asyncio
async def test_falsche_breite_faellt_auch_im_stapel_auf():
    """Die Dimensionsprüfung gilt für JEDEN Vektor, nicht nur den ersten."""
    cm, _ = _client(_antwort([
        {"index": 0, "embedding": _vektor(0.1)},
        {"index": 1, "embedding": [0.2] * (DIM - 8)},
    ]))
    with patch("httpx.AsyncClient", return_value=cm):
        with pytest.raises(EmbeddingDimensionError):
            await generate_embeddings(["a", "b"])


@pytest.mark.asyncio
async def test_einzelaufruf_nutzt_denselben_weg():
    cm, client = _client(_antwort([{"index": 0, "embedding": _vektor(0.5)}]))
    with patch("httpx.AsyncClient", return_value=cm):
        vektor = await generate_embedding("nur einer")

    assert vektor == _vektor(0.5)
    assert client.post.await_args.kwargs["json"]["input"] == ["nur einer"]


@pytest.mark.asyncio
async def test_texte_werden_je_einzeln_gekuerzt():
    """Der Zeichen-Cap gilt pro Text — nicht für den Stapel als Ganzes."""
    cm, client = _client(_antwort([
        {"index": 0, "embedding": _vektor(0.1)},
        {"index": 1, "embedding": _vektor(0.2)},
    ]))
    lang = "x" * (settings.embedding_max_chars + 500)
    with patch("httpx.AsyncClient", return_value=cm):
        await generate_embeddings([lang, "kurz"])

    gesendet = client.post.await_args.kwargs["json"]["input"]
    assert len(gesendet[0]) == settings.embedding_max_chars
    assert gesendet[1] == "kurz"


def test_zeitbudget_waechst_mit_der_stapelgroesse():
    """Ein Timeout mitten im Stapel verwirft die Arbeit für ALLE darin enthaltenen Texte."""
    assert _batch_timeout(1) == 30.0
    assert _batch_timeout(32) > _batch_timeout(1)
    assert _batch_timeout(10_000) == 300.0, "aber gedeckelt"


# ── Backfill: Isolierung des schuldigen Textes ──────────────────────────────────────


def _http_fehler(status: int) -> httpx.HTTPStatusError:
    antwort = httpx.Response(status, request=httpx.Request("POST", "http://x/embeddings"))
    return httpx.HTTPStatusError("fehler", request=antwort.request, response=antwort)


def test_inhaltsfehler_nur_bei_400():
    from app.crons.embedding_backfill_service import _ist_inhaltsfehler

    assert _ist_inhaltsfehler(_http_fehler(400)) is True
    # 401/429 treffen jeden Text gleich — einzeln nachfassen wäre reine Verschwendung.
    assert _ist_inhaltsfehler(_http_fehler(401)) is False
    assert _ist_inhaltsfehler(_http_fehler(429)) is False
    assert _ist_inhaltsfehler(httpx.ConnectError("weg")) is False
    assert _ist_inhaltsfehler(RuntimeError("irgendwas")) is False
