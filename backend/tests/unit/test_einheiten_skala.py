"""Die Kosten-Einheit und ihre Skala (Paket 2 von 0.12, AP4).

1 Einheit = 1/10 000 € — ein Hundertstelcent. Der Euro ist für den Gegenstand zu grob:
Gemessen am 29.09.2026 fielen **97,7 % aller erfassten Nachrichten** unter einen Cent und
zeigten damit denselben Text („< 0,01 €").

Hier zwei Dinge: dass der Faktor aus der Konfiguration kommt (und unbrauchbare Werte
nicht durchschlagen), und dass die Prüfung meldet, wenn die Skala zu grob geworden ist.
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")

from app.budget import tiers
from app.litellm.config_check import (
    REFERENZ_NACHRICHT,
    WARNING,
    _pruefe_einheitenskala,
)


@pytest.fixture(autouse=True)
def _frischer_cache():
    tiers.invalidate_budget_tiers_cache()
    yield
    tiers.invalidate_budget_tiers_cache()


class TestFaktorAusDerKonfiguration:
    def test_vorgabe_ist_zehntausend(self, monkeypatch):
        monkeypatch.setattr(tiers, "_load_budget_tiers", lambda: {})
        assert tiers.einheiten_je_euro() == 10_000

    def test_eigener_wert_gilt(self, monkeypatch):
        monkeypatch.setattr(tiers, "_load_budget_tiers", lambda: {"einheiten_je_euro": 1000})
        assert tiers.einheiten_je_euro() == 1000

    @pytest.mark.parametrize("murks", ["viel", None, 0, -5, [1]])
    def test_unbrauchbarer_wert_faellt_auf_die_vorgabe_zurueck(self, murks, monkeypatch):
        """Ein Tippfehler in der YAML darf die Anzeige nicht auf 0 oder ins Negative
        drehen — das wäre schlimmer als der grobe Euro."""
        monkeypatch.setattr(tiers, "_load_budget_tiers", lambda: {"einheiten_je_euro": murks})
        assert tiers.einheiten_je_euro() == 10_000


def _eintraege(**preise):
    """name → Eintrag wie aus `GET /model/info`."""
    return {
        name: {"model_info": {"input_cost_per_token": ein, "output_cost_per_token": aus}}
        for name, (ein, aus) in preise.items()
    }


_SETTINGS = SimpleNamespace(exchange_rate_fallback=1.1705)


class TestSkalenpruefung:
    def test_heutige_preise_sind_unauffaellig(self, monkeypatch):
        """`mistral-winzig`, das günstigste Modell im Bestand: rund 3 Einheiten."""
        monkeypatch.setattr(tiers, "_load_budget_tiers", lambda: {})
        eintraege = _eintraege(**{
            "mistral-winzig": (4e-08, 1.2e-07),
            "chat-standard": (1.7e-07, 7.1e-07),
        })
        assert _pruefe_einheitenskala(eintraege, _SETTINGS) == []

    def test_meldet_wenn_das_guenstigste_modell_unter_eine_einheit_faellt(self, monkeypatch):
        monkeypatch.setattr(tiers, "_load_budget_tiers", lambda: {})
        # Zehnmal billiger als heute → rund 0,3 Einheiten.
        eintraege = _eintraege(**{"spottbillig": (4e-09, 1.2e-08)})
        funde = _pruefe_einheitenskala(eintraege, _SETTINGS)
        assert len(funde) == 1
        assert funde[0].level == WARNING
        assert "spottbillig" in funde[0].message
        assert "einheiten_je_euro" in funde[0].message

    def test_der_faktor_entscheidet_mit(self, monkeypatch):
        """Dieselben Preise, kleinerer Faktor → dieselbe Lage wie beim Euro."""
        eintraege = _eintraege(**{"chat-standard": (1.7e-07, 7.1e-07)})
        monkeypatch.setattr(tiers, "_load_budget_tiers", lambda: {"einheiten_je_euro": 1000})
        assert _pruefe_einheitenskala(eintraege, _SETTINGS), "0,75 Einheiten müssten auffallen"
        monkeypatch.setattr(tiers, "_load_budget_tiers", lambda: {"einheiten_je_euro": 10_000})
        assert _pruefe_einheitenskala(eintraege, _SETTINGS) == []

    def test_embedding_modelle_zaehlen_nicht_mit(self, monkeypatch):
        """Sie sind um Größenordnungen billiger und werden nie je Nachricht angezeigt —
        als „günstigstes Modell" würden sie die Prüfung dauerhaft auslösen."""
        monkeypatch.setattr(tiers, "_load_budget_tiers", lambda: {})
        eintraege = _eintraege(**{"chat-standard": (1.7e-07, 7.1e-07)})
        eintraege["oai-embed"] = {
            "model_info": {"input_cost_per_token": 2e-08, "output_cost_per_token": 0.0,
                           "mode": "embedding"}
        }
        assert _pruefe_einheitenskala(eintraege, _SETTINGS) == []

    def test_ohne_preise_keine_aussage(self, monkeypatch):
        """Fehlende Preise meldet Prüfung 2 — hier wäre es eine zweite, falsche Meldung."""
        monkeypatch.setattr(tiers, "_load_budget_tiers", lambda: {})
        eintraege = {"ohne-preis": {"model_info": {}}}
        assert _pruefe_einheitenskala(eintraege, _SETTINGS) == []

    def test_referenznachricht_ist_dokumentiert(self):
        """Die Prüfung rechnet mit einer gemessenen Größe, nicht mit einer geratenen."""
        ein, aus = REFERENZ_NACHRICHT
        assert ein > aus > 0


class TestVerdrahtung:
    """Die Prüfung muss in `check_config` hängen — sonst läuft sie nie."""

    def test_check_config_fuehrt_die_skalenpruefung_mit(self, monkeypatch):
        from app.litellm.config_check import check_config

        monkeypatch.setattr(tiers, "_load_budget_tiers", lambda: {})
        settings = SimpleNamespace(
            chat_default_model="chat-standard",
            title_model=None,
            embedding_model="embedding-standard",
            image_default_model=None,
            model_picker_hidden_prefixes=[],
            exchange_rate_fallback=1.1705,
        )
        model_infos = [
            {"model_name": "chat-standard",
             "model_info": {"input_cost_per_token": 4e-09, "output_cost_per_token": 1.2e-08,
                            "mode": "chat", "supports_function_calling": True}},
            {"model_name": "embedding-standard",
             "model_info": {"input_cost_per_token": 2e-08, "output_cost_per_token": 0.0,
                            "mode": "embedding"}},
        ]
        funde = check_config(model_infos, settings, bildarten=[], image_prices={})
        assert any("Kosten-Einheit ist zu grob" in f.message for f in funde)


class TestNurSichtbareModelle:
    """Gezählt wird, was jemand als Kosten **je Nachricht** sieht.

    Aufgefallen beim Prüflauf: `system-titel` ist um Größenordnungen billiger als jedes
    Chat-Modell und hätte die Prüfung dauerhaft ausgelöst — an der Anzeige wäre nichts
    dran gewesen, denn Titelkosten erscheinen nirgends einzeln.
    """

    def test_versteckte_modelle_zaehlen_nicht_mit(self, monkeypatch):
        monkeypatch.setattr(tiers, "_load_budget_tiers", lambda: {})
        eintraege = _eintraege(**{
            "chat-standard": (1.7e-07, 7.1e-07),
            "system-titel": (1e-08, 2e-08),
        })
        settings = SimpleNamespace(
            exchange_rate_fallback=1.1705,
            model_picker_hidden_prefixes=["system-", "embedding-", "bild-"],
        )
        assert _pruefe_einheitenskala(eintraege, settings) == []

    def test_ohne_praefixliste_zaehlen_alle(self, monkeypatch):
        """Keine Liste heißt: nicht filtern — lieber eine Meldung zu viel als eine
        Prüfung, die stillschweigend nichts tut."""
        monkeypatch.setattr(tiers, "_load_budget_tiers", lambda: {})
        eintraege = _eintraege(**{"system-titel": (1e-08, 2e-08)})
        assert _pruefe_einheitenskala(eintraege, SimpleNamespace(exchange_rate_fallback=1.1705))
