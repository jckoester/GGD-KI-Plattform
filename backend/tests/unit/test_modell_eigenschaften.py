"""Was der Modellwähler über ein Modell weiß (Paket 2 von 0.12, AP5).

Bis 0.12 las das Backend aus `/model/info` genau **ein** Feld, obwohl dieselbe Antwort
Preise, Kontextfenster und weitere Fähigkeiten trägt. Hier wird vor allem geprüft, dass
**Unbekanntes unbekannt bleibt** — die Oberfläche soll nichts erfinden.
"""
import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")

from app.litellm.modell_eigenschaften import (
    REFERENZ_NACHRICHT,
    Eigenschaften,
    _aus_eintrag,
    alle_eigenschaften,
    invalidate_eigenschaften_cache,
)


@pytest.fixture(autouse=True)
def _frischer_cache():
    invalidate_eigenschaften_cache()
    yield
    invalidate_eigenschaften_cache()


def _eintrag(name, **info):
    return {"model_name": name, "model_info": info}


class TestAbbildung:
    def test_liest_alle_felder(self):
        e = _aus_eintrag(_eintrag(
            "chat-standard",
            supports_function_calling=True, supports_reasoning=False,
            supports_vision=True, max_input_tokens=128000,
            input_cost_per_token=1.7e-07, output_cost_per_token=7.1e-07,
        ))
        assert e == Eigenschaften(
            funktionsaufrufe=True, denkt=False, bilder=True, kontextfenster=128000,
            preis_ein_usd=1.7e-07, preis_aus_usd=7.1e-07,
        )

    def test_fehlende_angaben_bleiben_none(self):
        """⚠️ `None` heißt **unbekannt**, nicht „nein" — bei IONOS ist das der Regelfall
        fürs Kontextfenster (17 von 31 Deployments melden eins)."""
        e = _aus_eintrag(_eintrag("ionos-gpt-oss-120b", input_cost_per_token=1.7e-07))
        assert e.kontextfenster is None
        assert e.funktionsaufrufe is None
        assert e.bilder is None


class TestKostenSchaetzung:
    def test_rechnet_mit_der_referenznachricht(self):
        ein, aus = REFERENZ_NACHRICHT
        e = Eigenschaften(preis_ein_usd=1.7e-07, preis_aus_usd=7.1e-07)
        assert e.usd_je_nachricht == pytest.approx(ein * 1.7e-07 + aus * 7.1e-07)

    def test_ohne_eingabepreis_keine_schaetzung(self):
        """Eine Null hieße „kostenlos". Fehlende Preise meldet check_litellm_config.py
        als Fehler — die Oberfläche soll schweigen, nicht raten."""
        assert Eigenschaften().usd_je_nachricht is None
        assert Eigenschaften(preis_aus_usd=1e-06).usd_je_nachricht is None

    def test_ohne_ausgabepreis_zaehlt_die_eingabe(self):
        e = Eigenschaften(preis_ein_usd=1e-07)
        assert e.usd_je_nachricht == pytest.approx(REFERENZ_NACHRICHT[0] * 1e-07)


class TestAbruf:
    async def test_baut_die_zuordnung(self):
        eintraege = [
            _eintrag("chat-standard", input_cost_per_token=1.7e-07),
            _eintrag("chat-schnell", input_cost_per_token=1.1e-07),
        ]
        with patch("app.litellm.modell_eigenschaften.LiteLLMClient") as cls:
            cls.return_value.get_model_deployments = AsyncMock(return_value=eintraege)
            cls.return_value.close = AsyncMock()
            daten = await alle_eigenschaften()
        assert set(daten) == {"chat-standard", "chat-schnell"}

    async def test_erster_treffer_gewinnt_bei_mehreren_deployments(self):
        """Zeigt ein Alias auf mehrere Deployments, ist die Angabe mehrdeutig — ein
        Mittelwert wäre erfundene Genauigkeit."""
        eintraege = [
            _eintrag("chat-standard", input_cost_per_token=1e-07),
            _eintrag("chat-standard", input_cost_per_token=9e-07),
        ]
        with patch("app.litellm.modell_eigenschaften.LiteLLMClient") as cls:
            cls.return_value.get_model_deployments = AsyncMock(return_value=eintraege)
            cls.return_value.close = AsyncMock()
            daten = await alle_eigenschaften()
        assert daten["chat-standard"].preis_ein_usd == 1e-07

    async def test_stoerung_leert_die_angaben_statt_zu_scheitern(self):
        """Ein unerreichbarer Proxy darf den Modellwähler nicht leeren — er zeigt dann
        Namen ohne Zusatzangaben, so wie vor 0.12."""
        with patch("app.litellm.modell_eigenschaften.LiteLLMClient") as cls:
            cls.return_value.get_model_deployments = AsyncMock(side_effect=RuntimeError("weg"))
            cls.return_value.close = AsyncMock()
            assert await alle_eigenschaften() == {}

    async def test_zweiter_abruf_kommt_aus_dem_cache(self):
        eintraege = [_eintrag("chat-standard", input_cost_per_token=1.7e-07)]
        with patch("app.litellm.modell_eigenschaften.LiteLLMClient") as cls:
            holen = AsyncMock(return_value=eintraege)
            cls.return_value.get_model_deployments = holen
            cls.return_value.close = AsyncMock()
            await alle_eigenschaften()
            await alle_eigenschaften()
            assert holen.await_count == 1


class TestEintragFuerDieOberflaeche:
    def test_ohne_eigenschaften_nur_der_name(self):
        """Der Wähler funktioniert weiter, wenn der Proxy schweigt."""
        from app.chat.router import _modell_eintrag

        item = _modell_eintrag("chat-standard", None)
        assert item.id == "chat-standard"
        assert item.usd_je_nachricht is None
        assert item.kontextfenster is None

    def test_reicht_die_angaben_durch(self):
        from app.chat.router import _modell_eintrag

        item = _modell_eintrag("chat-standard", Eigenschaften(
            funktionsaufrufe=True, kontextfenster=128000, preis_ein_usd=1.7e-07,
            preis_aus_usd=7.1e-07, denkt=True, bilder=False,
        ))
        assert item.supports_function_calling is True
        assert item.kontextfenster == 128000
        assert item.denkt is True
        assert item.bilder is False
        assert item.usd_je_nachricht > 0
