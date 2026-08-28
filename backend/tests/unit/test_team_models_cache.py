"""Unit-Tests für app.litellm.team_models (Mehrmodell-Plan, Schritt 5).

Der Cache spart einen Proxy-Roundtrip je Chat-Anfrage. Entscheidend ist aber nicht die
Ersparnis, sondern die Unterscheidung **unbekannt (None)** gegen **nichts erlaubt (leere
Menge)**: Wird eine Störung als „nichts erlaubt" gelesen, verschwinden alle Bildarten aus
dem Werkzeug — aus einem Anzeigeproblem würde ein Totalausfall.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.litellm import team_models


@pytest.fixture(autouse=True)
def _leerer_cache():
    team_models.invalidate_team_models_cache()
    yield
    team_models.invalidate_team_models_cache()


def _info(models):
    return {"models": models}


async def test_liefert_die_freigeschalteten_modelle():
    with patch.object(
        team_models._client, "get_team_info",
        new=AsyncMock(return_value=_info(["bild-standard", "chat-standard"])),
    ):
        assert await team_models.erlaubte_modelle("lehrkraefte") == {
            "bild-standard", "chat-standard",
        }


async def test_no_default_models_ist_eine_leere_menge():
    """LiteLLMs Platzhalter ist keine Modell-ID — und heißt sehr wohl „nichts erlaubt"."""
    with patch.object(
        team_models._client, "get_team_info",
        new=AsyncMock(return_value=_info(["no-default-models"])),
    ):
        assert await team_models.erlaubte_modelle("jahrgang-5") == set()


async def test_zweiter_aufruf_kommt_aus_dem_cache():
    abruf = AsyncMock(return_value=_info(["bild-standard"]))
    with patch.object(team_models._client, "get_team_info", new=abruf):
        await team_models.erlaubte_modelle("lehrkraefte")
        await team_models.erlaubte_modelle("lehrkraefte")

    abruf.assert_awaited_once()


async def test_abgelaufener_eintrag_wird_neu_geholt(monkeypatch):
    monkeypatch.setattr(team_models, "TTL_SEKUNDEN", -1.0)  # sofort veraltet
    abruf = AsyncMock(return_value=_info(["bild-standard"]))
    with patch.object(team_models._client, "get_team_info", new=abruf):
        await team_models.erlaubte_modelle("lehrkraefte")
        await team_models.erlaubte_modelle("lehrkraefte")

    assert abruf.await_count == 2


async def test_verschiedene_teams_werden_getrennt_gehalten():
    async def je_team(team_id):
        return _info(["bild-standard"] if team_id == "lehrkraefte" else [])

    with patch.object(team_models._client, "get_team_info", new=AsyncMock(side_effect=je_team)):
        assert await team_models.erlaubte_modelle("lehrkraefte") == {"bild-standard"}
        assert await team_models.erlaubte_modelle("jahrgang-5") == set()


# ── Störungen sind „unbekannt", nicht „nichts erlaubt" ──────────────────────────────


async def test_proxy_fehler_liefert_none():
    with patch.object(
        team_models._client, "get_team_info",
        new=AsyncMock(side_effect=RuntimeError("Proxy weg")),
    ):
        assert await team_models.erlaubte_modelle("lehrkraefte") is None


async def test_unbekanntes_team_liefert_none():
    """404 heißt „Team gibt es nicht" — kein Grund, alles zu verbergen."""
    with patch.object(
        team_models._client, "get_team_info", new=AsyncMock(return_value=None)
    ):
        assert await team_models.erlaubte_modelle("jahrgang-13") is None


async def test_fehler_wird_nicht_zwischengespeichert():
    """Sonst bliebe eine Sekunde Störung fünf Minuten lang wirksam."""
    ergebnisse = [RuntimeError("kurz weg"), _info(["bild-standard"])]

    async def wechselnd(team_id):
        wert = ergebnisse.pop(0)
        if isinstance(wert, Exception):
            raise wert
        return wert

    with patch.object(team_models._client, "get_team_info", new=AsyncMock(side_effect=wechselnd)):
        assert await team_models.erlaubte_modelle("lehrkraefte") is None
        assert await team_models.erlaubte_modelle("lehrkraefte") == {"bild-standard"}


# ── Ableitung aus Rolle und Jahrgang ────────────────────────────────────────────────


async def test_lehrkraft_landet_im_lehrkraefte_team():
    gesehen = []

    async def merken(team_id):
        gesehen.append(team_id)
        return _info(["bild-standard"])

    with patch.object(team_models._client, "get_team_info", new=AsyncMock(side_effect=merken)):
        await team_models.erlaubte_modelle_fuer(["teacher"], None)

    assert gesehen == ["lehrkraefte"]


async def test_schuelerin_landet_im_jahrgangsteam():
    gesehen = []

    async def merken(team_id):
        gesehen.append(team_id)
        return _info([])

    with patch.object(team_models._client, "get_team_info", new=AsyncMock(side_effect=merken)):
        await team_models.erlaubte_modelle_fuer(["student"], 9)

    assert gesehen == ["jahrgang-9"]


@pytest.mark.parametrize("roles, grade", [(["student"], None), ([], None), (["student"], 99)])
async def test_ohne_ableitbares_team_wird_nicht_gefiltert(roles, grade):
    """Kein Team heißt „unbekannt" — nicht, dass diese Person nichts darf."""
    with patch.object(team_models._client, "get_team_info", new=AsyncMock()) as abruf:
        assert await team_models.erlaubte_modelle_fuer(roles, grade) is None
        abruf.assert_not_awaited()
