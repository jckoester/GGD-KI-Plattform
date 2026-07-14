"""Unit-Tests für die Step-up-Endpunkte + require_fresh_stepup (Phase 12, Schritt 5).

Direct-Pfad (Passwort-Re-Entry) ist voll testbar; der Redirect-Pfad wird über die
Adapter-Primitiven (test_oauth_adapter.py) und die State-/Token-Funktionen
(test_stepup.py) abgedeckt.
"""

import os

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.auth.base import NormalizedIdentity
from app.auth.dependencies import (
    get_auth_adapter,
    get_current_user,
    require_fresh_stepup_for,
)
from app.auth.jwt import JwtPayload
from app.auth.pseudonym import pseudonymize
from app.auth.router import router
from app.auth.stepup import issue_stepup_token
from app.config import settings
from app.db.session import get_db

SUB = pseudonymize("sozial01", settings.school_secret)
RID = str(uuid4())  # eine feste Ressourcen-/Antrags-ID für die Step-up-Bindung


def _user(sub=SUB) -> JwtPayload:
    return JwtPayload(sub=sub, roles=["review"], grade=None, jti="j", iat=1, exp=9999999999)


class _DirectAdapter:
    mode = "direct"

    def __init__(self, identity):
        self._identity = identity

    async def authenticate_direct(self, username, password):
        return self._identity


class _RedirectAdapter:
    mode = "redirect"

    async def get_stepup_challenge(self, state):
        from app.auth.base import LoginChallenge
        return LoginChallenge(type="redirect", redirect_url=f"https://idp/auth?prompt=login&state={state}")


def _make_app(adapter, user=None):
    app = FastAPI()
    app.include_router(router)

    async def fake_user():
        return user or _user()

    async def fake_db():
        yield None

    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[get_auth_adapter] = lambda: adapter
    app.dependency_overrides[get_db] = fake_db
    return app


# ---------- GET /step-up ----------

def test_get_stepup_direct_mode():
    app = _make_app(_DirectAdapter(None))
    r = TestClient(app).get(f"/step-up?action=approve&resource_id={RID}")
    assert r.status_code == 200
    assert r.json() == {"mode": "direct"}


def test_get_stepup_redirect_mode():
    app = _make_app(_RedirectAdapter())
    r = TestClient(app).get(f"/step-up?action=approve&resource_id={RID}")
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "redirect"
    assert "prompt=login" in data["redirect_url"]


def test_get_stepup_missing_action_400():
    app = _make_app(_DirectAdapter(None))
    assert TestClient(app).get(f"/step-up?resource_id={RID}").status_code == 400
    assert TestClient(app).get("/step-up?action=approve").status_code == 400  # kein resource_id
    assert TestClient(app).get(f"/step-up?action=bogus&resource_id={RID}").status_code == 400


# ---------- POST /step-up (direct) ----------

def test_post_stepup_success_sets_cookie():
    identity = NormalizedIdentity(external_id="sozial01", roles=["review"])
    app = _make_app(_DirectAdapter(identity))
    r = TestClient(app).post(
        "/step-up",
        json={"username": "sozial01", "password": "review.pw", "action": "approve", "resource_id": RID},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert r.cookies.get("stepup")


def test_post_stepup_missing_action_400():
    identity = NormalizedIdentity(external_id="sozial01", roles=["review"])
    app = _make_app(_DirectAdapter(identity))
    r = TestClient(app).post("/step-up", json={"username": "sozial01", "password": "review.pw"})
    assert r.status_code == 400


def test_post_stepup_wrong_credentials_401():
    app = _make_app(_DirectAdapter(None))  # authenticate_direct → None
    r = TestClient(app).post(
        "/step-up",
        json={"username": "sozial01", "password": "wrong", "action": "approve", "resource_id": RID},
    )
    assert r.status_code == 401
    assert r.cookies.get("stepup") is None


def test_post_stepup_pseudonym_mismatch_401():
    # Re-Auth als anderer Nutzer (external_id pseudonymisiert nicht auf die Session)
    identity = NormalizedIdentity(external_id="jemand_anderes", roles=["review"])
    app = _make_app(_DirectAdapter(identity))
    r = TestClient(app).post(
        "/step-up",
        json={"username": "jemand_anderes", "password": "x", "action": "approve", "resource_id": RID},
    )
    assert r.status_code == 401


def test_post_stepup_missing_fields_400():
    identity = NormalizedIdentity(external_id="sozial01", roles=["review"])
    app = _make_app(_DirectAdapter(identity))
    r = TestClient(app).post("/step-up", json={"username": "sozial01"})
    assert r.status_code == 400


def test_post_stepup_wrong_mode_405():
    app = _make_app(_RedirectAdapter())
    r = TestClient(app).post("/step-up", json={"username": "x", "password": "y"})
    assert r.status_code == 405


# ---------- require_fresh_stepup_for (Aktion+Ressource+Einmalverwendung, Audit #3) ----------

def _consume_db(rowcount=1):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(rowcount=rowcount))
    db.commit = AsyncMock()
    return db


def _protected_app(user=None, db=None):
    app = FastAPI()

    @app.get("/protected/{request_id}")
    async def _protected(request_id, u: JwtPayload = Depends(require_fresh_stepup_for("read"))):
        return {"sub": u.sub}

    async def fake_user():
        return user or _user()

    async def fake_db():
        yield db if db is not None else _consume_db()

    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[get_db] = fake_db
    return app


def _bound_token(sub=SUB, action="read", rid=RID):
    return issue_stepup_token(settings.jwt_secret, sub, action, rid)


def test_stepup_for_allows_matching_cookie():
    client = TestClient(_protected_app())
    client.cookies.set("stepup", _bound_token())
    r = client.get(f"/protected/{RID}")
    assert r.status_code == 200
    assert r.json()["sub"] == SUB


def test_stepup_for_missing_cookie_401():
    r = TestClient(_protected_app()).get(f"/protected/{RID}")
    assert r.status_code == 401
    assert r.headers.get("X-Stepup-Required") == "1"


def test_stepup_for_wrong_sub_401():
    client = TestClient(_protected_app())
    client.cookies.set("stepup", _bound_token(sub="anderer-sub"))
    assert client.get(f"/protected/{RID}").status_code == 401


def test_stepup_for_wrong_action_401():
    # Token für "approve", Route verlangt "read"
    client = TestClient(_protected_app())
    client.cookies.set("stepup", _bound_token(action="approve"))
    assert client.get(f"/protected/{RID}").status_code == 401


def test_stepup_for_wrong_resource_401():
    client = TestClient(_protected_app())
    client.cookies.set("stepup", _bound_token(rid=str(uuid4())))
    assert client.get(f"/protected/{RID}").status_code == 401


def test_stepup_for_replay_rejected():
    # Nonce bereits verbraucht (rowcount=0) → Replay abgelehnt
    client = TestClient(_protected_app(db=_consume_db(rowcount=0)))
    client.cookies.set("stepup", _bound_token())
    assert client.get(f"/protected/{RID}").status_code == 401
