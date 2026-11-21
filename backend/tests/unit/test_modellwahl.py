"""Regel der Modellwahl im Assistenten-Chat (0.51, AV Schritt 1)."""
import logging

from app.auth.jwt import JwtPayload
from types import SimpleNamespace

from app.chat.modellwahl import darf_im_assistenten_waehlen, fehlen_funktionen, wahl_im_assistenten


def _u(*rollen):
    return JwtPayload(sub="p", roles=list(rollen), role=rollen[0] if rollen else "student",
                      grade=None, exp=9999999999, iat=0, jti="j")


def test_lehrkraft_und_admin_duerfen_schuelerin_nicht():
    assert darf_im_assistenten_waehlen(_u("teacher"))
    assert darf_im_assistenten_waehlen(_u("teacher", "admin"))
    assert not darf_im_assistenten_waehlen(_u("student"))


def test_wahl_der_schuelerin_wird_verworfen_und_protokolliert(caplog):
    with caplog.at_level(logging.INFO, logger="app.chat.modellwahl"):
        assert wahl_im_assistenten("chat-komplex", _u("student"), 7) is None
    assert "verworfen" in caplog.text and "assistant_id=7" in caplog.text


def test_ohne_wahl_nichts_zu_verwerfen(caplog):
    with caplog.at_level(logging.INFO, logger="app.chat.modellwahl"):
        assert wahl_im_assistenten(None, _u("student")) is None
    assert caplog.text == ""


def test_lehrkraft_behaelt_ihre_wahl():
    assert wahl_im_assistenten("chat-komplex", _u("teacher")) == "chat-komplex"


F = {"chat-komplex": True, "chat-schnell": False, "neu": None}
PLANER = SimpleNamespace(tool_groups=["lesson_planning"])


def test_gewaehltes_modell_ohne_funktionen_fehlt():
    assert fehlen_funktionen(PLANER, "chat-schnell", "chat-komplex", F)


def test_eigenes_modell_des_assistenten_bleibt_wie_bisher():
    # Auch wenn es keine Funktionen kann: kein Bruch für Assistenten, die so eingerichtet sind.
    assert not fehlen_funktionen(PLANER, "chat-schnell", "chat-schnell", F)


def test_unbekannt_und_ohne_faehigkeiten_sperren_nicht():
    assert not fehlen_funktionen(PLANER, "neu", "chat-komplex", F)
    assert not fehlen_funktionen(SimpleNamespace(tool_groups=[]), "chat-schnell", "chat-komplex", F)
    assert not fehlen_funktionen(None, "chat-schnell", "chat-komplex", F)


# ── Schritt 3: bevorzugte Modelle ────────────────────────────────────────────

import pytest
from unittest.mock import AsyncMock, patch

from app.chat.modellwahl import BEVORZUGT_FREI, BEVORZUGT_PLANUNG, pruefe_bevorzugtes_modell
from app.litellm.modell_eigenschaften import Eigenschaften

EIGENSCHAFTEN = {"chat-komplex": Eigenschaften(funktionsaufrufe=True),
                 "chat-schnell": Eigenschaften(funktionsaufrufe=False)}


async def _pruefe(schluessel, wert, user, erlaubt=frozenset({"chat-komplex", "chat-schnell"})):
    with patch("app.litellm.team_models.erlaubte_modelle_fuer",
               AsyncMock(return_value=None if erlaubt is None else set(erlaubt))), \
         patch("app.litellm.modell_eigenschaften.alle_eigenschaften", AsyncMock(return_value=EIGENSCHAFTEN)):
        return await pruefe_bevorzugtes_modell(schluessel, wert, user)


@pytest.mark.asyncio
async def test_lehrkraft_speichert_freigegebenes_modell():
    assert await _pruefe(BEVORZUGT_FREI, " chat-schnell ", _u("teacher")) == "chat-schnell"
    assert await _pruefe(BEVORZUGT_PLANUNG, "chat-komplex", _u("teacher")) == "chat-komplex"


@pytest.mark.asyncio
async def test_leer_heisst_keine_vorliebe():
    assert await _pruefe(BEVORZUGT_FREI, "", _u("teacher")) is None
    assert await _pruefe(BEVORZUGT_PLANUNG, None, _u("teacher")) is None


@pytest.mark.asyncio
async def test_schuelerin_hat_keine_vorliebe():
    with pytest.raises(PermissionError):
        await _pruefe(BEVORZUGT_FREI, "chat-komplex", _u("student"))


@pytest.mark.asyncio
async def test_nicht_freigegeben_und_ohne_funktionen_fuer_planung():
    with pytest.raises(ValueError, match="nicht freigeschaltet"):
        await _pruefe(BEVORZUGT_FREI, "ant-opus", _u("teacher"))
    with pytest.raises(ValueError, match="Planungs-Assistenten brauchen"):
        await _pruefe(BEVORZUGT_PLANUNG, "chat-schnell", _u("teacher"))
    with pytest.raises(ValueError, match="kein Chat-Modell"):
        await _pruefe(BEVORZUGT_FREI, "system-titel", _u("teacher"), erlaubt={"system-titel"})


@pytest.mark.asyncio
async def test_freigaben_unbekannt_sperren_nicht():
    # Proxy nicht erreichbar: wie überall nicht sperren.
    assert await _pruefe(BEVORZUGT_FREI, "ant-opus", _u("teacher"), erlaubt=None) == "ant-opus"


# ── Schritt 12: Vorliebe beim Anlegen, alle Zweige ───────────────────────────

from types import SimpleNamespace

from app.chat.modellwahl import vorliebe_anwenden


async def _anwenden(user, assistant=None, vorlieben=None, erlaubt=frozenset({"chat-schnell", "chat-komplex", "ant-sonnet"}),
                    funktionsaufrufe=None, plant=False, vorgabe="chat-standard"):
    with patch("app.preferences.service.bevorzugte_modelle", AsyncMock(return_value=vorlieben or {})), \
         patch("app.litellm.team_models.erlaubte_modelle_fuer",
               AsyncMock(return_value=None if erlaubt is None else set(erlaubt))), \
         patch("app.assistants.sichtbarkeit.plant", lambda a: plant):
        return await vorliebe_anwenden(None, user, assistant, vorgabe, funktionsaufrufe or {})


ASSI = SimpleNamespace(id=7)


@pytest.mark.asyncio
async def test_vorliebe_nicht_mehr_freigeschaltet_faellt_zurueck_mit_hinweis():
    modell, hinweis = await _anwenden(_u("teacher"), vorlieben={"modell_frei": "ant-opus"})
    assert modell == "chat-standard"
    assert "nicht mehr freigeschaltet" in hinweis and "chat-standard" in hinweis


@pytest.mark.asyncio
async def test_freier_chat_braucht_keine_funktionen():
    # ⚙ gilt nur bei Assistenten — im freien Chat zählt die Vorliebe auch ohne Funktionen.
    modell, hinweis = await _anwenden(_u("teacher"), vorlieben={"modell_frei": "chat-schnell"},
                                      funktionsaufrufe={"chat-schnell": False})
    assert (modell, hinweis) == ("chat-schnell", None)


@pytest.mark.asyncio
async def test_planung_nimmt_modell_planung_nicht_modell_frei():
    vorlieben = {"modell_frei": "chat-schnell", "modell_planung": "ant-sonnet"}
    assert await _anwenden(_u("teacher"), ASSI, vorlieben, plant=True, vorgabe="chat-komplex") == ("ant-sonnet", None)
    # Planungs-Assistent ohne eigene Planungs-Vorliebe: kein Rückgriff auf die für freie Chats.
    assert await _anwenden(_u("teacher"), ASSI, {"modell_frei": "chat-schnell"}, plant=True,
                           vorgabe="chat-komplex") == ("chat-komplex", None)


@pytest.mark.asyncio
async def test_vorliebe_gleich_vorgabe_ohne_hinweis_und_unbekannte_freigabe_sperrt_nicht():
    assert await _anwenden(_u("teacher"), vorlieben={"modell_frei": "chat-standard"}, erlaubt=set()) == ("chat-standard", None)
    assert await _anwenden(_u("teacher"), vorlieben={"modell_frei": "ant-opus"}, erlaubt=None) == ("ant-opus", None)


@pytest.mark.asyncio
async def test_schuelerin_und_admin_bei_vorliebe():
    assert await _anwenden(_u("student"), vorlieben={"modell_frei": "chat-schnell"}) == ("chat-standard", None)
    assert await _anwenden(_u("teacher", "admin"), vorlieben={"modell_frei": "chat-schnell"}) == ("chat-schnell", None)
