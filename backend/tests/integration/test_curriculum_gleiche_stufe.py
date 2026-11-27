"""Ein gültiges Curriculum je Fach, Stufe und Fassung (0.64, Jan 27.11.2026): Veröffentlichen ohne
Ersatz neben einem vorhandenen → 409; mit `ersetzen` wird der Entwurf zum Ersatz. Verschiedene
Bänder und Fassungen sind ausgenommen; das Admin-Skript legt kein zweites an.
Erfordert TEST_DATABASE_URL."""
import uuid

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.context.curriculum_yaml import zu_entwurf
from app.context.router import router
from app.context.service import import_curriculum_from_draft
from app.db.models import ContextEdge, ContextNode
from app.db.session import get_db

pytestmark = pytest.mark.asyncio

BP_ID = "BP2016BW_ALLG_GYM_CH_GLSTUFE"
ADMIN = JwtPayload(sub="gs-admin", roles=["admin", "teacher"], grade=None, jti="j", iat=0, exp=9999999999)


def _datei(*kapitel, stufe="8", fassung="2016.GS"):
    return {"schule": "", "fach_code": "CH", "fach": "Chemie", "schulart": "Gymnasium", "jahrgangsstufe": stufe,
            "bp_id": BP_ID if fassung == "2016.GS" else None, "bp_version": fassung,
            "kapitel": [{"titel": t, "reihenfolge": i, "std": 4, "lernsequenzen": [
                {"bp_titel": f"LS {t}", "reihenfolge": 1, "eintraege": [{"konkretisierung": "x"}]}]}
                for i, t in enumerate(kapitel or ("Stoffe",), 1)]}


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    subject_id = (await db_session.execute(sa.text(
        "INSERT INTO subjects (slug, name, fach_code) VALUES ('chemie', 'Chemie', 'CH') "
        "ON CONFLICT (slug) DO UPDATE SET fach_code = EXCLUDED.fach_code RETURNING id"))).scalar_one()
    for bp_id, fassung in ((BP_ID, "2016.GS"), (BP_ID + ".V9", "2016.GS9")):
        db_session.add(ContextNode(
            id=uuid.uuid4(), category="knowledge", content_type="fachplan", title="Gymnasium - Chemie",
            status="active", owner_pseudonym="system", read_scope="global", write_scope="school",
            subject_id=subject_id, metadata_={"bp_id": bp_id, "bp_version": fassung}))
    await db_session.flush()
    return db_session


def _client(db):
    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: ADMIN
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _entwurf(db, d):
    cid, _ = await import_curriculum_from_draft(db, zu_entwurf(d).entwurf, ADMIN.sub, als_entwurf=True)
    return cid


async def test_zweites_ohne_ersatz_409_mit_ersatz_ersetzt(db):
    alt_id, _ = await import_curriculum_from_draft(db, zu_entwurf(_datei("Stoffe", "Reaktionen")).entwurf, "system")
    neu_id = await _entwurf(db, _datei("Stoffe", "Neu"))
    async with _client(db) as c:
        u = (await c.get(f"/context/curricula/{neu_id}/publish")).json()
        assert [x["id"] for x in u["gleiche_stufe"]] == [str(alt_id)] and u["vorgaenger"] is None
        r = await c.post(f"/context/curricula/{neu_id}/publish")
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["grund"] == "gleiche_stufe" and "nur ein Curriculum" in r.json()["detail"]["nachricht"]
        assert (await db.get(ContextNode, neu_id)).status == "draft"

        u = (await c.get(f"/context/curricula/{neu_id}/publish", params={"ersetzen": str(alt_id)})).json()
        assert u["vorgaenger"]["id"] == str(alt_id)
        r = await c.post(f"/context/curricula/{neu_id}/publish", params={"ersetzen": str(alt_id)})
        assert r.status_code == 200, r.text
        assert r.json()["vorgaenger"]["id"] == str(alt_id)
    assert (await db.get(ContextNode, alt_id)).status == "archived"
    neu = await db.get(ContextNode, neu_id)
    assert (neu.status, neu.metadata_["kopie_von"]) == ("active", str(alt_id))
    kapitel = (await db.execute(sa.select(ContextNode).join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
                                .where(ContextEdge.to_node_id == neu_id, ContextNode.content_type == "kapitel"))).scalars().all()
    stoffe = next(k for k in kapitel if k.title == "Stoffe")
    assert stoffe.metadata_.get("kopie_von")       # gleichnamiges Kapitel des Originals
    assert not next(k for k in kapitel if k.title == "Neu").metadata_.get("kopie_von")


async def test_ausnahmen_band_und_fassung_und_ohne_konflikt(db):
    await import_curriculum_from_draft(db, zu_entwurf(_datei()).entwurf, "system")
    andere_fassung = await _entwurf(db, _datei(fassung="2016.GS9"))
    andere_stufe = await _entwurf(db, _datei(stufe="9"))
    async with _client(db) as c:
        for cid in (andere_fassung, andere_stufe):
            assert (await c.get(f"/context/curricula/{cid}/publish")).json()["gleiche_stufe"] == []
            assert (await c.post(f"/context/curricula/{cid}/publish")).status_code == 200
    # Verschiedene Bänder: beide tragen ein Band, und sie unterscheiden sich
    band_a = await _entwurf(db, _datei())
    alt = (await db.execute(sa.select(ContextNode).where(
        ContextNode.content_type == "curriculum", ContextNode.status == "active",
        ContextNode.metadata_["bp_version"].astext == "2016.GS",
        ContextNode.metadata_["jahrgangsstufe"].astext == "8"))).scalar_one()
    alt.metadata_ = {**alt.metadata_, "band": "Basis"}
    a = await db.get(ContextNode, band_a)
    a.metadata_ = {**a.metadata_, "band": "Leistung"}
    await db.flush()
    async with _client(db) as c:
        assert (await c.post(f"/context/curricula/{band_a}/publish")).status_code == 200


async def test_admin_skript_legt_kein_zweites_an(db):
    await _entwurf(db, _datei())
    entwurf = (await db.execute(sa.select(ContextNode).where(
        ContextNode.content_type == "curriculum", ContextNode.metadata_["bp_version"].astext == "2016.GS"))).scalar_one()
    entwurf.status = "active"
    await db.flush()
    with pytest.raises(ValueError, match="Je Stufe und Fassung gilt nur eines"):
        await import_curriculum_from_draft(db, zu_entwurf(_datei()).entwurf, "system")
    # Derselbe Schlüssel aktualisiert weiter (Wiederimport des Skripts)
    erst, _ = await import_curriculum_from_draft(db, zu_entwurf(_datei(stufe="9")).entwurf, "system")
    zweit, _ = await import_curriculum_from_draft(db, zu_entwurf(_datei("Stoffe", "Mehr", stufe="9")).entwurf, "system")
    assert erst == zweit
