"""Löschsperre (F7, ADR-019) seit 0.64: Verweise zählen nur von **außerhalb** des Teilbaums.

Kapitel und Lernsequenzen hängen per `part_of` am Curriculum und gehören nach einem Import oft
einem anderen Eigentümer. Bis 0.63 sperrten sie als „fremde Verweise“ das Löschen des eigenen
Curriculums (Jan, 27.11.2026). Erfordert TEST_DATABASE_URL."""
import uuid

import httpx
import pytest
from fastapi import FastAPI

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.context.router import router
from app.db.models import ContextEdge, ContextNode
from app.db.session import get_db

pytestmark = pytest.mark.asyncio

ICH = JwtPayload(sub="lt-ich", roles=["admin", "teacher"], grade=None, jti="j", iat=0, exp=9999999999)


def _knoten(typ, titel, owner):
    return ContextNode(id=uuid.uuid4(), category="knowledge", content_type=typ, title=titel, status="active",
                       owner_pseudonym=owner, read_scope="school", write_scope="private", metadata_={})


async def _welt(db):
    cur = _knoten("curriculum", "Mein Curriculum", ICH.sub)
    kap = _knoten("kapitel", "Kapitel aus dem Import", "system")
    ls = _knoten("lernsequenz", "LS aus dem Import", "system")
    db.add_all([cur, kap, ls])
    await db.flush()
    db.add_all([ContextEdge(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"),
                ContextEdge(from_node_id=ls.id, to_node_id=kap.id, relation="part_of")])
    await db.flush()
    return cur, kap, ls


def _client(db):
    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: ICH
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_eigene_teile_anderer_eigentuemer_sperren_nicht(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    cur, kap, ls = await _welt(db_session)
    async with _client(db_session) as c:
        r = await c.delete(f"/context/nodes/{cur.id}")
    assert r.status_code == 204, r.text
    for n in (cur, kap, ls):
        assert await db_session.get(ContextNode, n.id) is None


async def test_fremder_verweis_auf_ein_kapitel_sperrt(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    cur, kap, _ = await _welt(db_session)
    fremd = _knoten("concept", "Fremder Baustein", "jemand-anders")
    db_session.add(fremd)
    await db_session.flush()
    db_session.add(ContextEdge(from_node_id=fremd.id, to_node_id=kap.id, relation="references"))
    await db_session.flush()
    async with _client(db_session) as c:
        r = await c.delete(f"/context/nodes/{cur.id}")
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert [x["title"] for x in d["referenzen"]] == ["Fremder Baustein"]
    assert d["nachricht"].startswith("1 aktive Bausteine")
    assert (await db_session.get(ContextNode, cur.id)) is not None
