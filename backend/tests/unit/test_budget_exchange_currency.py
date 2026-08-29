"""Preiswährung: der Umrechnungsfaktor und der Prüfpunkt dazu.

Das Kursrisiko entsteht **erst durch die Umrechnung**. Rechnet der Anbieter in Euro ab und
stehen die Preise in Euro, gibt es keinen Faktor und damit nichts, was auseinanderlaufen
kann. IONOS listet ausschließlich Euro-Preise (geprüft 29.08.2026).
"""
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.budget.exchange import get_current_rate, preise_in_euro
from app.litellm.config_check import WARNING, check_config


# ── Umrechnungsfaktor ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_euro_preise_brauchen_keinen_kurs():
    """Kein Faktor, keine Datenbank, kein Risiko."""
    db = AsyncMock()
    with patch("app.budget.exchange.settings", SimpleNamespace(litellm_price_currency="EUR")):
        assert await get_current_rate(db) == 1.0
    db.execute.assert_not_awaited(), "kein Kurs-Lookup nötig"


@pytest.mark.asyncio
@pytest.mark.parametrize("wert", ["eur", " EUR ", "Eur"])
async def test_schreibweise_ist_egal(wert):
    with patch("app.budget.exchange.settings", SimpleNamespace(litellm_price_currency=wert)):
        assert preise_in_euro()


@pytest.mark.asyncio
async def test_usd_bleibt_der_vorgabewert():
    """Bestehende Installationen dürfen sich durch die Erweiterung nicht ändern."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(fetchone=lambda: None))
    with patch("app.budget.exchange.settings",
               SimpleNamespace(litellm_price_currency="USD", exchange_rate_fallback=1.10)):
        assert await get_current_rate(db) == 1.10


# ── Prüfpunkt ───────────────────────────────────────────────────────────────────────


def _eintrag(name, *, api_base=None, provider="openai"):
    return {
        "model_name": name,
        "litellm_params": {"model": f"{provider}/x", **({"api_base": api_base} if api_base else {})},
        "model_info": {
            "litellm_provider": provider,
            "supports_function_calling": True,
            "input_cost_per_token": 1e-7,
            "output_cost_per_token": 2e-7,
        },
    }


def _settings(waehrung):
    return SimpleNamespace(
        chat_default_model="chat-standard", title_model="system-titel",
        embedding_model="embedding-standard", image_default_model="bild-standard",
        model_picker_hidden_prefixes=[], litellm_price_currency=waehrung,
    )


def _waehrungsfunde(entries, waehrung):
    funde = check_config(entries, _settings(waehrung), bildarten=[], image_prices={})
    return [f for f in funde if "PRICE_CURRENCY" in f.message]


def test_eingebaute_preistabelle_wird_bei_euro_gemeldet():
    """Der Fall, der still danebenläge: Mistral & Co. sind in LiteLLM in Dollar geführt."""
    entries = [
        _eintrag("chat-standard", api_base="https://ionos…"),   # eigener Preis
        _eintrag("mistral-large", provider="mistral"),           # eingebaut, USD
    ]
    funde = _waehrungsfunde(entries, "EUR")

    assert len(funde) == 1 and funde[0].level == WARNING
    assert "mistral-large" in funde[0].message
    assert "chat-standard" not in funde[0].message, "eigene api_base = eigener Preis"


def test_bei_usd_wird_nicht_gemeldet():
    entries = [_eintrag("mistral-large", provider="mistral")]
    assert not _waehrungsfunde(entries, "USD")


def test_reiner_euro_betrieb_ist_still():
    entries = [_eintrag("chat-standard", api_base="https://ionos…")]
    assert not _waehrungsfunde(entries, "EUR")


def test_lokale_modelle_loesen_keine_warnung_aus():
    """Ollama kostet nichts — die Währung ist dort gegenstandslos."""
    entries = [
        _eintrag("chat-standard", api_base="https://ionos…"),
        _eintrag("lokal", provider="ollama"),
    ]
    assert not _waehrungsfunde(entries, "EUR")
