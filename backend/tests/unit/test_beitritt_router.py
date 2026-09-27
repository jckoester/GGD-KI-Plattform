"""AP4: Der Beitritts-Router — wer darf was, und wo sitzt die Drossel."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.session import get_db
from app.groups.router import router as beitritt_router

_SCHUELERIN = JwtPayload(sub="s-pseudo", roles=["student"], grade="9",
                         jti="j", iat=1_000_000, exp=9_999_999_999)
_LEHRKRAFT = JwtPayload(sub="l-pseudo", roles=["teacher"], grade=None,
                        jti="j", iat=1_000_000, exp=9_999_999_999)


def _client(user):
    app = FastAPI()
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: user
    app.include_router(beitritt_router)
    return TestClient(app)


# ── Wer darf einlösen ────────────────────────────────────────────────────────


def test_lehrkraft_kann_nicht_per_code_beitreten(monkeypatch):
    """⚠️ **Entscheidung F3.** Der Code macht `role_in_group='student'`.

    Kooperativ unterrichtende Kolleg:innen sind ein eigener Fall (eigenes Paket) und
    kommen nicht über einen Schüler-Beitrittsweg in die Gruppe — sonst stünde eine
    Lehrkraft als Schülerin in ihrer eigenen Gruppe.
    """
    antwort = _client(_LEHRKRAFT).post("/groups/join", json={"code": "ABCD-EFGH"})
    assert antwort.status_code == 403
    assert "Schüler" in antwort.json()["detail"]


def test_unbekannter_code_verraet_nichts(monkeypatch):
    """Weder „gibt es nicht" noch „gehört einer anderen Gruppe" — nur: gilt nicht."""
    monkeypatch.setattr(
        "app.groups.router.loese_ein",
        AsyncMock(return_value=(None, SimpleNamespace(gueltig=False, grund="unbekannt"))),
    )
    antwort = _client(_SCHUELERIN).post("/groups/join", json={"code": "ZZZZ-ZZZZ"})
    assert antwort.status_code == 404
    text = antwort.json()["detail"].lower()
    assert "gruppe" not in text, "Die Antwort darf keine fremde Gruppe andeuten"


def test_abgelaufener_code_wird_benannt(monkeypatch):
    """Anders als „unbekannt": Diesen Code hatte die Person in der Hand."""
    monkeypatch.setattr(
        "app.groups.router.loese_ein",
        AsyncMock(return_value=(None, SimpleNamespace(gueltig=False, grund="abgelaufen"))),
    )
    antwort = _client(_SCHUELERIN).post("/groups/join", json={"code": "ABCD-EFGH"})
    assert antwort.status_code == 410
    assert "abgelaufen" in antwort.json()["detail"].lower()


# ── Wo die Drossel sitzt ─────────────────────────────────────────────────────


def _hat_drossel(pfad: str, methode: str) -> bool:
    """Ob eine Route über die `rate_limit`-Fabrik geschützt ist.

    Erkannt am Namen der inneren Funktion (`_dep` aus `app.ratelimit.dependency`) —
    die Fabrik gibt einen Closure zurück, der sonst nicht unterscheidbar wäre.
    """
    for route in beitritt_router.routes:
        if route.path == pfad and methode in route.methods:
            return any(
                d.call.__module__ == "app.ratelimit.dependency"
                for d in route.dependant.dependencies
                if d.call is not None
            )
    raise AssertionError(f"Route {methode} {pfad} nicht gefunden")


def test_einloesen_ist_gedrosselt():
    assert _hat_drossel("/groups/join", "POST")


def test_lesen_des_codes_ist_nicht_gedrosselt():
    """⚠️ **Die Falle aus dem Feedback-Kanal, hier vermieden.**

    Dort saß `rate_limit` zunächst auch auf dem Lesepfad und hätte Nutzer:innen aus
    ihrer eigenen Liste ausgesperrt. Die Code-Ansicht wird beim normalen Arbeiten
    mehrfach geladen — eine Drossel darauf sperrte die Lehrkraft aus ihrer eigenen
    Gruppe aus.
    """
    assert not _hat_drossel("/groups/{group_id}/join-code", "GET")
