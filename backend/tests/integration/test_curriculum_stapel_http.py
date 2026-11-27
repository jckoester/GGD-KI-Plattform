"""Curriculum-Vorlagen gesammelt einspielen über HTTP (0.62, Päckchen BH): Vorschau ohne Spuren,
je Datei ein Entwurf, Datum im Titel bei vorhandenem Entwurf, Fehler je Datei, nur Admins,
Grenzen, Drossel. Erfordert TEST_DATABASE_URL."""
import uuid

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
import yaml
from fastapi import FastAPI

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.context.curriculum_yaml import zu_entwurf
from app.context.router import router
from app.context.service import import_curriculum_from_draft
from app.db.models import ContextNode
from app.db.session import get_db

pytestmark = pytest.mark.asyncio

BP_ID = "BP2016BW_ALLG_GYM_CH_BHSTAPEL"
BP_VERSION = "2016.BHS"
ADMIN = JwtPayload(sub="bh-admin", roles=["admin", "teacher"], grade=None, jti="j", iat=0, exp=9999999999)
LEHRKRAFT = JwtPayload(sub="bh-lehrkraft", roles=["teacher"], grade=None, jti="j", iat=0, exp=9999999999)
STAPEL = "/context/curricula/import/stapel"


def _datei(stufe="8", *kapitel, **abw):
    kapitel = kapitel or ("Stoffe",)
    return {"schule": "", "fach_code": "CH", "fach": "Chemie", "schulart": "Gymnasium", "jahrgangsstufe": stufe,
            "bp_id": BP_ID, "bp_version": BP_VERSION,
            "kapitel": [{"titel": t, "reihenfolge": i, "std": 4, "lernsequenzen": [
                {"bp_titel": f"LS {t}", "reihenfolge": 1, "eintraege": [{"konkretisierung": "x"}]}]}
                for i, t in enumerate(kapitel, 1)], **abw}


def _text(d):
    return yaml.safe_dump(d, allow_unicode=True)


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


@pytest.fixture(autouse=True)
def _drossel_frei():
    from app.ratelimit import store

    store.reset()
    yield
    store.reset()


def _client(db, user):
    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _entwuerfe(db):
    return (await db.execute(sa.select(ContextNode).where(
        ContextNode.content_type == "curriculum", ContextNode.status == "draft",
        ContextNode.metadata_["bp_version"].astext == BP_VERSION).order_by(ContextNode.created_at))).scalars().all()


async def test_vorschau_hinterlaesst_nichts_anlegen_je_datei_ein_entwurf(db):
    original_id, _ = await import_curriculum_from_draft(db, zu_entwurf(_datei("9")).entwurf, "system")
    dateien = [{"name": "ch7.yaml", "yaml": _text(_datei("7"))},
               {"name": "ch9.yaml", "yaml": _text(_datei("9", "Stoffe", "Neu"))},
               {"name": "kaputt.yaml", "yaml": "a: &x 1\nb: *x\n"},
               {"name": "ch7-nochmal.yaml", "yaml": _text(_datei("7"))}]
    async with _client(db, ADMIN) as c:
        r = await c.post(f"{STAPEL}/pruefen", json={"dateien": dateien})
        assert r.status_code == 200, r.text
        v = r.json()
        assert [(d["datei"], d["ok"], d["art"]) for d in v["dateien"]] == [
            ("ch7.yaml", True, "neu"), ("ch9.yaml", True, "ersetzt"), ("kaputt.yaml", False, None),
            ("ch7-nochmal.yaml", True, "zusaetzlich")]
        assert v["zahlen"] == {"ok": 3, "fehler": 1}
        assert v["dateien"][1]["ersetzen"] == str(original_id)
        assert v["dateien"][1]["ersetzt_titel"] == "Chemie Kl. 9"
        assert [k["ersetzt_kapitel"] for k in v["dateien"][1]["kapitel"]] == [True, False]
        assert "Anker" in v["dateien"][2]["fehler"][0]
        assert v["dateien"][3]["curriculum"]["titel"].startswith("Chemie Kl. 7 (Import ")
        assert all("id" not in d for d in v["dateien"])
        assert await _entwuerfe(db) == []

        r = await c.post(STAPEL, json={"dateien": dateien})
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["zahlen"] == {"ok": 3, "fehler": 1}
        ids = [d.get("id") for d in v["dateien"]]
        assert ids[2] is None and all(ids[i] for i in (0, 1, 3))
    entwuerfe = await _entwuerfe(db)
    assert len(entwuerfe) == 3 and {e.owner_pseudonym for e in entwuerfe} == {ADMIN.sub}
    ersatz = next(e for e in entwuerfe if e.id == uuid.UUID(ids[1]))
    assert ersatz.metadata_["kopie_von"] == str(original_id) and ersatz.title == "Chemie Kl. 9"
    assert ersatz.metadata_["vorlage"] == {"datei": "ch9.yaml", "importiert_am": ersatz.metadata_["vorlage"]["importiert_am"]}
    assert len(ersatz.metadata_["vorlage"]["importiert_am"]) == 10
    zweiter = next(e for e in entwuerfe if e.id == uuid.UUID(ids[3]))
    assert "kopie_von" not in zweiter.metadata_ and zweiter.title.startswith("Chemie Kl. 7 (Import ")
    assert (await db.get(ContextNode, original_id)).status == "active"


async def test_vorhandener_entwurf_datum_im_titel_kein_ersatz(db):
    original_id, _ = await import_curriculum_from_draft(db, zu_entwurf(_datei("8")).entwurf, "system")
    async with _client(db, ADMIN) as c:
        erst = await c.post(STAPEL, json={"dateien": [{"name": "a.yaml", "yaml": _text(_datei("8"))}]})
        assert erst.json()["dateien"][0]["art"] == "ersetzt"
        zweit = await c.post(STAPEL, json={"dateien": [{"name": "b.yaml", "yaml": _text(_datei("8"))}]})
        d = zweit.json()["dateien"][0]
        assert (d["ok"], d["art"], d["ersetzen"]) == (True, "zusaetzlich", None)
        assert "(Import " in d["curriculum"]["titel"]
    assert len(await _entwuerfe(db)) == 2


async def test_nur_admins_und_grenzen(db):
    eine = [{"name": "a.yaml", "yaml": _text(_datei("8"))}]
    async with _client(db, LEHRKRAFT) as c:
        for pfad in (f"{STAPEL}/pruefen", STAPEL):
            assert (await c.post(pfad, json={"dateien": eine})).status_code == 403
    async with _client(db, ADMIN) as c:
        assert (await c.post(f"{STAPEL}/pruefen", json={"dateien": []})).status_code == 422
        assert (await c.post(f"{STAPEL}/pruefen", json={"dateien": eine * 61})).status_code == 422
        # 60 Dateien knapp unter der Einzelgrenze gehen durch (und scheitern einzeln am Inhalt)
        voll = [{"name": f"{i}.yaml", "yaml": "x" * 199_000} for i in range(60)]
        r = await c.post(f"{STAPEL}/pruefen", json={"dateien": voll})
        assert r.status_code == 200 and r.json()["zahlen"] == {"ok": 0, "fehler": 60}
    assert await _entwuerfe(db) == []


async def test_gesamtgroesse_begrenzt():
    from pydantic import ValidationError

    from app.context.router import CurriculumStapelEingabe

    with pytest.raises(ValidationError, match="12 MB"):
        CurriculumStapelEingabe(dateien=[{"name": f"{i}", "yaml": "ä" * 100_001} for i in range(60)])


async def test_gedrosselt(db, monkeypatch):
    from app.ratelimit import config as drossel_config

    monkeypatch.setattr(drossel_config, "resolve",
                        lambda b, r: (1, 60.0) if b == "curriculum_stapel" else (999, 60.0))
    eine = [{"name": "a.yaml", "yaml": "x: 1"}]
    async with _client(db, ADMIN) as c:
        codes = [(await c.post(f"{STAPEL}/pruefen", json={"dateien": eine})).status_code for _ in range(2)]
        # Der Einzelimport hat seinen eigenen Eimer
        einzel = await c.post("/context/curricula/import/pruefen", json={"yaml": "x: 1"})
    assert codes == [200, 429] and einzel.status_code == 200


async def test_quelle_bleibt_im_export_kopie_ohne_vorlage(db):
    """`quelle` wandert mit Export und Kopie; die Kennzeichnung als Vorlage gilt nur dem Import."""
    from app.context.curriculum_export import build_curriculum_export_dict
    from app.context.relink import duplicate_curriculum
    from app.context.service import load_curriculum_tree

    quelle = "Beispielcurriculum Chemie (ZSL, Fassung V3.0)"
    async with _client(db, ADMIN) as c:
        v = (await c.post(STAPEL, json={"dateien": [{"name": "q.yaml", "yaml": _text(_datei("8", quelle=quelle))}]})).json()
    d = v["dateien"][0]
    assert d["ok"] and d["curriculum"]["quelle"] == quelle
    entwurf = await db.get(ContextNode, uuid.UUID(d["id"]))
    assert entwurf.metadata_["quelle"] == quelle and entwurf.metadata_["vorlage"]["datei"] == "q.yaml"
    export = await build_curriculum_export_dict(db, await load_curriculum_tree(db, entwurf.id))
    assert export["quelle"] == quelle
    kopie_id, _ = await duplicate_curriculum(db, entwurf.id, owner=ADMIN.sub, titel="Kopie")
    kopie = await db.get(ContextNode, kopie_id)
    assert kopie.metadata_["quelle"] == quelle and "vorlage" not in kopie.metadata_
