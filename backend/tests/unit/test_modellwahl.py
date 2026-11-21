"""Regel der Modellwahl im Assistenten-Chat (0.51, AV Schritt 1)."""
import logging

from app.auth.jwt import JwtPayload
from app.chat.modellwahl import darf_im_assistenten_waehlen, wahl_im_assistenten


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
