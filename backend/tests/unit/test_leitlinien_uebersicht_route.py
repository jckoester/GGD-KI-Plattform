"""Route der Leitlinien-Übersicht (0.53, Päckchen AU Schritt 2): wer sie sieht (F2)."""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.auth.vorschau import Vorschau
from app.context.router import router
from app.db.session import get_db

ZIEL = "app.context.leitlinien_uebersicht.leitlinien_uebersicht"


def _user(rollen, preview=None):
    return JwtPayload(sub="p", roles=rollen, grade=None, jti="j", iat=0, exp=9999999999, preview=preview)


def _client(user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: MagicMock()
    return TestClient(app)


def test_lehrkraft_und_admin_sehen_die_uebersicht():
    for rollen in (["teacher"], ["admin"]):
        with patch(ZIEL, AsyncMock(return_value={"art": "leitlinie"})) as f:
            r = _client(_user(rollen)).get(f"/context/leitlinien/{uuid4()}/uebersicht?nur_veroeffentlicht=true")
        assert r.status_code == 200, rollen
        assert r.json() == {"art": "leitlinie"}
        assert f.await_args.kwargs == {"nur_veroeffentlicht": True}


def test_schuelerin_und_vorschau_gesperrt():
    vorschau = _user(["student"], Vorschau(echte_rollen=["teacher"], gruppe_id=1, beginn=0, sitzung_ablauf=2**31))
    for user in (_user(["student"]), vorschau):
        with patch(ZIEL, AsyncMock()) as f:
            r = _client(user).get(f"/context/leitlinien/{uuid4()}/uebersicht")
        assert r.status_code == 403
        f.assert_not_awaited()


def test_unbekannt_404():
    with patch(ZIEL, AsyncMock(return_value=None)):
        r = _client(_user(["teacher"])).get(f"/context/leitlinien/{uuid4()}/uebersicht")
    assert r.status_code == 404
