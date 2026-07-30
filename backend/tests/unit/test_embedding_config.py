"""Unit-Tests: Embedding-Modell und -Dimension sind konfigurierbar (kein Literal im Code).

Deckt den Payload an den LiteLLM-Proxy (Modellname, optionaler `dimensions`-Parameter,
Input-Cap) und die Dimensionsprüfung der Antwort ab.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.context.embedding import EmbeddingDimensionError, generate_embedding


def _mock_client(embedding):
    """Async-Context-Manager-Mock für httpx.AsyncClient; sammelt den POST-Payload.

    Gibt (client_cm, captured) zurück — `captured["json"]` enthält den gesendeten Payload.
    """
    captured = {}

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value={"data": [{"embedding": embedding}]})

    async def _post(url, headers=None, json=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return response

    inner = MagicMock()
    inner.post = _post

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=inner)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, captured


@pytest.fixture
def embed(monkeypatch):
    """Ruft generate_embedding mit gepatchtem HTTP-Client auf und liefert den Payload."""

    async def _run(text="Testinhalt", *, returned_dims=None, **settings_overrides):
        for key, value in settings_overrides.items():
            monkeypatch.setattr(settings, key, value)
        dims = returned_dims if returned_dims is not None else settings.embedding_dimensions
        cm, captured = _mock_client([0.1] * dims)
        with patch("app.context.embedding.httpx.AsyncClient", return_value=cm):
            result = await generate_embedding(text)
        return result, captured

    return _run


async def test_uses_configured_model_name(embed):
    """Der Modellname stammt aus den Settings, nicht aus einem Literal."""
    _, captured = await embed(embedding_model="embedding-standard")
    assert captured["json"]["model"] == "embedding-standard"


async def test_model_name_change_needs_no_code_change(embed):
    """Zweiter Name, gleicher Codepfad — der Kern der Wechselbarkeit."""
    _, captured = await embed(embedding_model="ionos-bge-m3")
    assert captured["json"]["model"] == "ionos-bge-m3"


async def test_dimensions_param_omitted_by_default(embed):
    """Ohne EMBEDDING_SEND_DIMENSIONS darf `dimensions` NICHT im Payload stehen.

    BGE-M3 und die meisten offenen Modelle quittieren den unbekannten Parameter mit 400.
    """
    _, captured = await embed(embedding_send_dimensions=False)
    assert "dimensions" not in captured["json"]


async def test_dimensions_param_sent_when_enabled(embed):
    """Mit EMBEDDING_SEND_DIMENSIONS wird die konfigurierte Breite mitgeschickt."""
    _, captured = await embed(embedding_send_dimensions=True, embedding_dimensions=1024)
    assert captured["json"]["dimensions"] == 1024


async def test_input_is_capped_at_configured_length(embed):
    """Sehr langer Input wird auf EMBEDDING_MAX_CHARS gekürzt (Token-Limit des Modells)."""
    _, captured = await embed("x" * 5000, embedding_max_chars=100)
    assert captured["json"]["input"] == ["x" * 100]


async def test_matching_dimension_is_returned(embed):
    """Passt die Breite, kommt der Vektor unverändert zurück."""
    result, _ = await embed(embedding_dimensions=1024, returned_dims=1024)
    assert len(result) == 1024


async def test_wrong_dimension_raises_with_actionable_message(embed):
    """Falsche Breite → eigener Fehlertyp mit Handlungsanweisung.

    Ohne diese Prüfung scheitert erst der DB-Insert mit einer pgvector-Meldung, die die
    Ursache (falsch konfiguriertes Modell) nicht nennt.
    """
    with pytest.raises(EmbeddingDimensionError) as exc:
        await embed(
            embedding_model="falsches-modell",
            embedding_dimensions=1024,
            returned_dims=1536,
        )
    message = str(exc.value)
    assert "1536" in message and "1024" in message
    assert "falsches-modell" in message
    assert "EMBEDDING_DIMENSIONS" in message


async def test_proxy_url_and_master_key_from_settings(embed):
    """Der Call geht an den Proxy — nie direkt an einen Anbieter (Projekt-Invariante)."""
    _, captured = await embed(
        litellm_proxy_url="http://proxy:4000", litellm_master_key="sk-test"
    )
    assert captured["url"] == "http://proxy:4000/embeddings"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
