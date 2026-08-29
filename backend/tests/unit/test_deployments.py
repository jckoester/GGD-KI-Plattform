"""Unit-Tests für app.litellm.deployments (Modell-Transparenz, Schritt 1).

Gespeichert wird sonst nur der Aliasname (`chat-standard`) — für eine Quellenangabe
wertlos. Diese Auflösung macht daraus das Anbietermodell.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.litellm import deployments


def _eintrag(alias, ziel, kennung=None):
    return {
        "model_name": alias,
        "litellm_params": {"model": ziel},
        "model_info": {"id": kennung} if kennung else {},
    }


KATALOG = [
    _eintrag("chat-standard", "openai/openai/gpt-oss-120b", "hash-gptoss"),
    _eintrag("mistral-small", "mistral/mistral-small-latest", "hash-mistral"),
    _eintrag("ant-sonnet", "anthropic/claude-sonnet-5", "hash-claude"),
]


@pytest.fixture(autouse=True)
def _leerer_cache():
    deployments.invalidate_deployment_cache()
    yield
    deployments.invalidate_deployment_cache()


async def test_kennung_wird_aufgeloest():
    with patch.object(deployments._client, "get_model_deployments",
                      new=AsyncMock(return_value=KATALOG)):
        assert await deployments.anbietermodell("hash-gptoss") == "openai/openai/gpt-oss-120b"
        assert await deployments.anbietermodell("hash-claude") == "anthropic/claude-sonnet-5"


async def test_alias_als_rueckfall():
    """Ältere LiteLLM-Versionen liefern den Header nicht."""
    with patch.object(deployments._client, "get_model_deployments",
                      new=AsyncMock(return_value=KATALOG)):
        assert await deployments.anbietermodell(None, "mistral-small") == "mistral/mistral-small-latest"


async def test_kennung_schlaegt_alias():
    """Zeigt ein Alias auf mehrere Deployments, benennt nur die Kennung das befragte."""
    katalog = KATALOG + [_eintrag("chat-standard", "mistral/mistral-large-latest", "hash-zweit")]
    with patch.object(deployments._client, "get_model_deployments",
                      new=AsyncMock(return_value=katalog)):
        assert await deployments.anbietermodell("hash-zweit", "chat-standard") == "mistral/mistral-large-latest"


async def test_unbekannte_kennung_laedt_einmal_neu():
    """Ein gerade hinzugefügtes Modell wäre sonst bis zum TTL-Ablauf nicht auflösbar."""
    abruf = AsyncMock(side_effect=[KATALOG, KATALOG + [_eintrag("neu", "x/neu", "hash-neu")]])
    with patch.object(deployments._client, "get_model_deployments", new=abruf):
        assert await deployments.anbietermodell("hash-gptoss")   # füllt den Cache
        assert await deployments.anbietermodell("hash-neu") == "x/neu"

    assert abruf.await_count == 2


async def test_unbekanntes_bleibt_unbekannt():
    with patch.object(deployments._client, "get_model_deployments",
                      new=AsyncMock(return_value=KATALOG)):
        assert await deployments.anbietermodell("gibt-es-nicht", "auch-nicht") is None


async def test_ohne_angaben_kein_abruf():
    with patch.object(deployments._client, "get_model_deployments", new=AsyncMock()) as abruf:
        assert await deployments.anbietermodell(None, None) is None
        abruf.assert_not_awaited()


async def test_proxy_fehler_liefert_none():
    """Unbekannt ist nicht dasselbe wie „kein Modell" — der Aufrufer speichert dann nur den Alias."""
    with patch.object(deployments._client, "get_model_deployments",
                      new=AsyncMock(side_effect=RuntimeError("Proxy weg"))):
        assert await deployments.anbietermodell("hash-gptoss", "chat-standard") is None


async def test_zweiter_aufruf_kommt_aus_dem_cache():
    abruf = AsyncMock(return_value=KATALOG)
    with patch.object(deployments._client, "get_model_deployments", new=abruf):
        await deployments.anbietermodell("hash-gptoss")
        await deployments.anbietermodell("hash-mistral")

    abruf.assert_awaited_once()


async def test_eintrag_ohne_ziel_wird_uebergangen():
    with patch.object(deployments._client, "get_model_deployments",
                      new=AsyncMock(return_value=[_eintrag("kaputt", "", "hash-leer")] + KATALOG)):
        assert await deployments.anbietermodell("hash-leer") is None
        assert await deployments.anbietermodell("hash-gptoss") == "openai/openai/gpt-oss-120b"


# ── Zitiername ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "voll, erwartet",
    [
        ("openai/openai/gpt-oss-120b", "gpt-oss-120b"),   # IONOS: Provider + Herausgeber
        ("mistral/mistral-small-latest", "mistral-small-latest"),
        ("anthropic/claude-sonnet-5", "claude-sonnet-5"),
        ("gpt-4o-mini", "gpt-4o-mini"),                   # OpenAI ohne Präfix
        ("openai/BAAI/bge-m3", "bge-m3"),
        (None, None),
        ("", None),
    ],
)
def test_zitiername_streift_die_praefixe(voll, erwartet):
    """Das Provider-Präfix ist LiteLLM-Syntax und gehört nicht in eine Quellenangabe."""
    assert deployments.zitiername(voll) == erwartet
