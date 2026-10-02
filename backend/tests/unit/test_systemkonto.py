"""Das Systemkonto (0.12, Paket 2, AP3): eigener Schlüssel, Rückfall, Betrag.

Die Abnahme verlangt beide Richtungen: **Schlüssel gesetzt → er wird benutzt;
Schlüssel leer → Master-Key und Warnung.** Dazu der Betrag aus dem Antwortkopf — und
dass dessen Verbuchung nie eine Suche scheitern lässt.
"""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import settings
from app.context.embedding import EmbeddingResponseError, generate_embeddings
from app.litellm import systemkonto

DIM = settings.embedding_dimensions
MASTER = "sk-master-" + "m" * 20
SYSTEM = "sk-system-" + "s" * 20


@pytest.fixture
def schluessel(monkeypatch):
    """Setzt Master- und Systemschlüssel; ``schluessel(system="")`` für den Rückfall."""
    def _setzen(*, system: str = SYSTEM):
        monkeypatch.setattr(settings, "litellm_master_key", MASTER)
        monkeypatch.setattr(settings, "litellm_system_key", system)
    return _setzen


def _antwort(*, status: int = 200, kosten: str | None = "1e-07", anzahl: int = 1):
    r = MagicMock()
    r.status_code = status
    r.headers = {systemkonto.KOSTENKOPF: kosten} if kosten is not None else {}
    r.json = MagicMock(return_value={
        "data": [{"index": i, "embedding": [0.1] * DIM} for i in range(anzahl)],
    })

    def _raise():
        if status >= 400:
            raise httpx.HTTPStatusError(f"HTTP {status}", request=MagicMock(), response=r)

    r.raise_for_status = MagicMock(side_effect=_raise)
    return r


def _client(response):
    cm = MagicMock()
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, client


def _gesendeter_schluessel(client) -> str:
    return client.post.await_args.kwargs["headers"]["Authorization"].removeprefix("Bearer ")


# ── Der Schlüssel ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gesetzter_systemschluessel_wird_benutzt(schluessel):
    schluessel()
    cm, client = _client(_antwort())
    with patch("httpx.AsyncClient", return_value=cm), \
         patch.object(systemkonto, "verbuche", AsyncMock()):
        await generate_embeddings(["Suche"])
    assert _gesendeter_schluessel(client) == SYSTEM


@pytest.mark.asyncio
async def test_leerer_systemschluessel_faellt_auf_den_master_key_zurueck(schluessel):
    schluessel(system="")
    cm, client = _client(_antwort())
    with patch("httpx.AsyncClient", return_value=cm), \
         patch.object(systemkonto, "verbuche", AsyncMock()):
        await generate_embeddings(["Suche"])
    assert _gesendeter_schluessel(client) == MASTER


def test_rueckfall_meldet_sich_beim_start(schluessel, caplog):
    schluessel(system="")
    with caplog.at_level(logging.WARNING, logger="app.litellm.systemkonto"):
        assert systemkonto.pruefe_beim_start() is False
    assert "LITELLM_SYSTEM_KEY" in caplog.text


def test_mit_systemschluessel_bleibt_der_start_still(schluessel, caplog):
    schluessel()
    with caplog.at_level(logging.WARNING, logger="app.litellm.systemkonto"):
        assert systemkonto.pruefe_beim_start() is True
    assert caplog.text == ""


@pytest.mark.asyncio
async def test_abgewiesener_systemschluessel_wird_beim_namen_genannt(schluessel, caplog):
    """Ein falscher Schlüssel legt die Suche still — das Log muss sagen, welcher."""
    schluessel()
    cm, _ = _client(_antwort(status=401, kosten=None))
    with patch("httpx.AsyncClient", return_value=cm), \
         caplog.at_level(logging.ERROR, logger="app.context.embedding"), \
         pytest.raises(httpx.HTTPStatusError):
        await generate_embeddings(["Suche"])
    assert "LITELLM_SYSTEM_KEY" in caplog.text


# ── Der Betrag ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("kopf,erwartet", [
    ("1e-07", 1e-07),
    ("0.0", 0.0),
    (None, None),          # Kopf fehlt
    ("abc", None),
    ("nan", None),
    ("-0.5", None),
])
def test_betrag_aus_dem_antwortkopf(kopf, erwartet):
    antwort = MagicMock()
    antwort.headers = {systemkonto.KOSTENKOPF: kopf} if kopf is not None else {}
    assert systemkonto.kosten_aus_antwort(antwort) == erwartet


def test_kein_str_kein_betrag():
    """Ein Kopfwert, der keine Zeichenkette ist, kommt nicht vom Proxy.

    Ohne diese Prüfung wäre jede ``MagicMock``-Antwort in anderen Tests ein Betrag von
    1,0 — ``float(MagicMock())`` ist 1.0 — und schriebe in die Datenbank.
    """
    antwort = MagicMock()  # headers.get(...) liefert dann ein MagicMock
    assert systemkonto.kosten_aus_antwort(antwort) is None


@pytest.mark.asyncio
async def test_jede_antwort_wird_verbucht(schluessel):
    schluessel()
    antwort = _antwort()
    cm, _ = _client(antwort)
    with patch("httpx.AsyncClient", return_value=cm), \
         patch.object(systemkonto, "verbuche", AsyncMock()) as verbuche:
        await generate_embeddings(["Suche"])
    verbuche.assert_awaited_once_with(antwort)


@pytest.mark.asyncio
async def test_auch_eine_unbrauchbare_antwort_ist_bezahlt(schluessel):
    """Zwei Texte, ein Vektor: verworfen — der Proxy hat trotzdem abgerechnet."""
    schluessel()
    cm, _ = _client(_antwort(anzahl=1))
    with patch("httpx.AsyncClient", return_value=cm), \
         patch.object(systemkonto, "verbuche", AsyncMock()) as verbuche, \
         pytest.raises(EmbeddingResponseError):
        await generate_embeddings(["a", "b"])
    verbuche.assert_awaited_once()


@pytest.mark.asyncio
async def test_verbuchen_wirft_nie(caplog):
    """Eine Suche darf nicht an ihrer eigenen Abrechnung scheitern."""
    def kaputt():
        raise RuntimeError("Datenbank weg")

    with caplog.at_level(logging.ERROR, logger="app.litellm.systemkonto"):
        await systemkonto.verbuche(_antwort(), sitzungen=kaputt)
    assert "nicht verbucht" in caplog.text


@pytest.mark.asyncio
async def test_ohne_kostenkopf_keine_sitzung():
    """Kein Betrag → keine Buchung, auch keine gezählte Anfrage."""
    sitzungen = MagicMock()
    await systemkonto.verbuche(_antwort(kosten=None), sitzungen=sitzungen)
    sitzungen.assert_not_called()
