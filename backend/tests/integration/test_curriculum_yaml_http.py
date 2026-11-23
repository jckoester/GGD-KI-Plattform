"""Curriculum aus YAML über HTTP (0.56, Päckchen BA Schritt 3): Vorschau ohne Spuren, Anlegen
als Entwurf, Rechte, Ersatz eines vorhandenen Curriculums, Drossel. Erfordert TEST_DATABASE_URL."""
import uuid

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
import yaml
from fastapi import FastAPI

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.context.router import router
from app.context.service import import_curriculum_from_draft
from app.context.curriculum_yaml import zu_entwurf
from app.db.models import ContextNode
from app.db.session import get_db

pytestmark = pytest.mark.asyncio

BP_ID = "BP2016BW_ALLG_GYM_CH_BAHTTP"
BP_VERSION = "2016.BH"
ADMIN = JwtPayload(sub="ba-admin", roles=["admin", "teacher"], grade=None, jti="j", iat=0, exp=9999999999)
LEHRKRAFT = JwtPayload(sub="ba-ohne-fachschaft", roles=["teacher"], grade=None, jti="j", iat=0, exp=9999999999)


def _datei(*kapitel, **abw):
    return {"schule": "", "fach_code": "CH", "fach": "Chemie", "schulart": "Gymnasium", "jahrgangsstufe": "8",
            "bp_id": BP_ID, "bp_version": BP_VERSION,
            "kapitel": [{"titel": t, "reihenfolge": i, "std": 4, "lernsequenzen": [
                {"bp_titel": f"LS {t}", "reihenfolge": 1, "eintraege": [{"konkretisierung": "x"}]}]}
                for i, t in enumerate(kapitel, 1)], **abw}


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    subject_id = (await db_session.execute(sa.text(
        "INSERT INTO subjects (slug, name, fach_code) VALUES ('chemie', 'Chemie', 'CH') "
        "ON CONFLICT (slug) DO UPDATE SET fach_code = EXCLUDED.fach_code RETURNING id"))).scalar_one()
    db_session.add(ContextNode(
        id=uuid.uuid4(), category="knowledge", content_type="fachplan", title="Gymnasium - Chemie",
        status="active", owner_pseudonym="system", read_scope="global", write_scope="school",
        subject_id=subject_id, metadata_={"bp_id": BP_ID, "bp_version": BP_VERSION}))
    await db_session.flush()
    return db_session


def _client(db, user):
    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _yaml_curricula(db):
    return (await db.execute(sa.select(sa.func.count()).where(
        ContextNode.content_type == "curriculum",
        ContextNode.metadata_["import_key"].astext.like("yaml_%")))).scalar_one()


async def test_vorschau_hinterlaesst_nichts_anlegen_ergibt_entwurf(db):
    text = yaml.safe_dump(_datei("Stoffe", "Reaktionen"), allow_unicode=True)
    async with _client(db, ADMIN) as c:
        r = await c.post("/context/curricula/import/pruefen", json={"yaml": text})
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["ok"] and v["fehler"] == []
        assert [k["titel"] for k in v["kapitel"]] == ["Stoffe", "Reaktionen"]
        assert v["summen"] == {"kapitel": 2, "lernsequenzen": 2, "eintraege": 2, "stunden": 8.0}
        assert (v["curriculum"]["fach_code"], v["vorhanden"], v["ersetzen"]) == ("CH", [], None)
        assert "id" not in v
        assert await _yaml_curricula(db) == 0

        r = await c.post("/context/curricula/import", json={"yaml": text})
        assert r.status_code == 201, r.text
        neu = await db.get(ContextNode, uuid.UUID(r.json()["id"]))
        assert (neu.status, neu.owner_pseudonym) == ("draft", ADMIN.sub)
        assert await _yaml_curricula(db) == 1


async def test_fehler_in_der_vorschau_200_beim_anlegen_422(db):
    async with _client(db, ADMIN) as c:
        r = await c.post("/context/curricula/import/pruefen", json={"yaml": "a: &x 1\nb: *x\n"})
        assert r.status_code == 200 and not r.json()["ok"]
        assert "Anker" in r.json()["fehler"][0]
        unbekannt = yaml.safe_dump(_datei("K", fach_code="XX"))
        r = await c.post("/context/curricula/import", json={"yaml": unbekannt})
        assert r.status_code == 422
        assert "„XX“" in r.json()["detail"]["fehler"][0]
        falsche_edition = yaml.safe_dump(_datei("K", bp_version="1999", bp_id=None))
        r = await c.post("/context/curricula/import/pruefen", json={"yaml": falsche_edition})
        assert not r.json()["ok"] and "1999" in r.json()["fehler"][0]
        r = await c.post("/context/curricula/import/pruefen", json={"yaml": "x" * 200_001})
        assert r.status_code == 422
    assert await _yaml_curricula(db) == 0


async def test_ohne_fachschaft_403(db):
    async with _client(db, LEHRKRAFT) as c:
        for pfad in ("/context/curricula/import/pruefen", "/context/curricula/import"):
            r = await c.post(pfad, json={"yaml": yaml.safe_dump(_datei("K"))})
            assert r.status_code == 403, r.text


async def test_ersatz_eines_vorhandenen_curriculums(db):
    original_id, _ = await import_curriculum_from_draft(db, zu_entwurf(_datei("Stoffe")).entwurf, "system")
    text = yaml.safe_dump(_datei("Stoffe", "Neu"))
    async with _client(db, ADMIN) as c:
        v = (await c.post("/context/curricula/import/pruefen", json={"yaml": text})).json()
        assert [x["id"] for x in v["vorhanden"]] == [str(original_id)]
        assert v["vorhanden"][0]["offener_entwurf"] is None

        v = (await c.post("/context/curricula/import/pruefen",
                          json={"yaml": text, "ersetzen": str(original_id)})).json()
        assert v["ok"] and v["ersetzen"] == str(original_id)
        assert [k["ersetzt_kapitel"] for k in v["kapitel"]] == [True, False]

        r = await c.post("/context/curricula/import", json={"yaml": text, "ersetzen": str(original_id)})
        assert r.status_code == 201, r.text
        entwurf = await db.get(ContextNode, uuid.UUID(r.json()["id"]))
        assert entwurf.metadata_["kopie_von"] == str(original_id)

        # Höchstens ein offener Entwurf je Curriculum
        v = (await c.post("/context/curricula/import/pruefen", json={"yaml": text})).json()
        assert v["vorhanden"][0]["offener_entwurf"] == str(entwurf.id)
        r = await c.post("/context/curricula/import", json={"yaml": text, "ersetzen": str(original_id)})
        assert r.status_code == 422 and "schon einen Entwurf" in r.json()["detail"]["fehler"][0]
        # Ein fremdes Curriculum als Ziel
        r = await c.post("/context/curricula/import", json={"yaml": text, "ersetzen": str(uuid.uuid4())})
        assert r.status_code == 422 and "passt nicht" in r.json()["detail"]["fehler"][0]
    assert (await db.get(ContextNode, original_id)).status == "active"


async def test_gedrosselt(db, monkeypatch):
    from app.ratelimit import config as drossel_config, store

    store.reset()
    monkeypatch.setattr(drossel_config, "resolve",
                        lambda b, r: (1, 60.0) if b == "curriculum_import" else (999, 60.0))
    async with _client(db, ADMIN) as c:
        codes = [(await c.post("/context/curricula/import/pruefen", json={"yaml": "x: 1"})).status_code
                 for _ in range(2)]
    store.reset()
    assert codes == [200, 429]
