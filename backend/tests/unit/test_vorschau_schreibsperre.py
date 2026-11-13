"""Schreibsperre der Vorschau (0.29, Schritt 3) — als Wächter über alle Routen.

Die Sperre sitzt in `get_current_user` (`app.auth.vorschau.pruefe_schreibsperre`). Sie
erreicht deshalb jeden Weg, der eine Anmeldung verlangt — und nur diese. Der Wächter prüft
beides: dass jede Erlaubnis einen echten Weg meint, und dass kein schreibender Weg ohne
Anmeldung auskommt, außer den hier begründeten.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.auth import vorschau
from app.auth.jwt import JwtPayload
from app.main import app

#: Schreibende Wege ohne `get_current_user` — sie liegen vor oder neben der Anmeldung.
OHNE_ANMELDUNG = {
    "app.auth.router.login_direct": "Anmeldung",
    "app.auth.vorschau_router.vorschau_verlassen": "Rückweg aus der Vorschau, liest das Token selbst",
}


def _routen(routes=None):
    for r in app.routes if routes is None else routes:
        if isinstance(r, APIRoute):
            yield r
        else:
            inner = getattr(r, "router", None) or getattr(r, "original_router", None)
            if inner is not None:
                yield from _routen(inner.routes)


def _haengt_an_anmeldung(route: APIRoute) -> bool:
    namen = []

    def sammle(d):
        for s in d.dependencies:
            namen.append(getattr(s.call, "__qualname__", ""))
            sammle(s)

    sammle(route.dependant)
    return any("get_current_user" in n for n in namen)


def _name(route):
    return vorschau.endpunkt_name(route.endpoint)


def test_jede_erlaubnis_meint_einen_schreibenden_weg():
    schreibend = {_name(r) for r in _routen() if r.methods & vorschau.SCHREIBEND}
    tot = set(vorschau.ERLAUBT) - schreibend
    assert not tot, f"Erlaubnis ohne Weg (umbenannt?): {sorted(tot)}"


def test_jede_lesesperre_meint_einen_weg():
    alle = {_name(r) for r in _routen()}
    assert set(vorschau.AUCH_LESEND_GESPERRT) <= alle


def test_kein_schreibender_weg_ohne_anmeldung():
    """Was ohne `get_current_user` schreibt, erreicht die Sperre nicht."""
    ohne = sorted(
        _name(r) for r in _routen()
        if r.methods & vorschau.SCHREIBEND and not _haengt_an_anmeldung(r)
        and _name(r) not in OHNE_ANMELDUNG
    )
    assert not ohne, (
        "Schreibender Weg ohne Anmeldung — die Vorschau-Sperre erreicht ihn nicht. "
        f"Anmeldung verlangen oder hier begründen: {ohne}"
    )


def test_die_ausnahmen_gibt_es_noch():
    alle = {_name(r) for r in _routen()}
    assert set(OHNE_ANMELDUNG) <= alle


def _user(vorschau_an: bool) -> JwtPayload:
    merkmal = vorschau.Vorschau(echte_rollen=["teacher"], beginn=0, sitzung_ablauf=2**31)
    return JwtPayload(sub="lk", roles=["student"], grade="9", jti="j", iat=0, exp=2**31,
                      preview=merkmal if vorschau_an else None)


def _scope(name):
    modul, _, funktion = name.rpartition(".")
    return {"endpoint": SimpleNamespace(__module__=modul, __qualname__=funktion)}


@pytest.mark.parametrize("methode,name,gesperrt", [
    ("PATCH", "app.preferences.router.update_preferences", True),
    ("POST", "app.api.tokens.create_token", True),
    ("GET", "app.preferences.router.read_preferences", False),
    ("POST", "app.chat.router.chat", False),
    ("POST", "app.feedback.router.create_feedback", False),
    # Werkstatt bleibt in der Vorschau unverändert; die GeoGebra-Datei aus dem Chat rechnet nur.
    ("POST", "app.artifacts.router.create_document", True),
    ("POST", "app.artifacts.router.save_image_to_library", True),
    ("POST", "app.artifacts.router.ggb_from_source", False),
    ("GET", "app.auth.router.step_up_challenge", True),
])
def test_regel(methode, name, gesperrt):
    if gesperrt:
        with pytest.raises(HTTPException) as fehler:
            vorschau.pruefe_schreibsperre(_scope(name), methode, _user(True))
        assert fehler.value.status_code == 403
    else:
        vorschau.pruefe_schreibsperre(_scope(name), methode, _user(True))
    # Ohne Vorschau gilt die Sperre nie.
    vorschau.pruefe_schreibsperre(_scope(name), methode, _user(False))
