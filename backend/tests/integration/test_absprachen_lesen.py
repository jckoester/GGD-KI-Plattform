"""Absprachen in beide Richtungen (0.63, AY Teil 2, Schritt 2). Erfordert TEST_DATABASE_URL."""
import uuid

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.context.absprachen import absprachen_des_curriculums
from app.db.models import ContextEdge, ContextNode
from app.db.session import get_db

pytestmark = pytest.mark.asyncio

LEHRKRAFT = JwtPayload(sub="ay2-lk", roles=["teacher"], grade=None, jti="j", iat=0, exp=9999999999)
SCHUELER = JwtPayload(sub="ay2-s", roles=["student"], grade="8", jti="j", iat=0, exp=9999999999)


async def _fach(db, slug, code):
    return (await db.execute(sa.text(
        "INSERT INTO subjects (slug, name, fach_code) VALUES (:s, :n, :c) "
        "ON CONFLICT (slug) DO UPDATE SET fach_code = EXCLUDED.fach_code, name = EXCLUDED.name RETURNING id"),
        {"s": slug, "n": slug.split("-")[0].title(), "c": code})).scalar_one()


class Welt:
    def __init__(self, db):
        self.db = db

    async def curriculum(self, fach, titel, stufen=(8, 8), status="active", scope="school", kopie_von=None):
        c = ContextNode(id=uuid.uuid4(), category="knowledge", content_type="curriculum", title=titel,
                        status=status, owner_pseudonym="system", read_scope=scope,
                        write_scope="private" if scope == "private" else "school",
                        subject_id=fach, min_grade=stufen[0], max_grade=stufen[1],
                        metadata_={"kopie_von": str(kopie_von)} if kopie_von else {})
        self.db.add(c)
        await self.db.flush()
        return c

    async def kapitel(self, cur, titel, absprachen=None, kopie_von=None, nr=1):
        meta = {"reihenfolge": nr}
        if absprachen is not None:
            meta["absprachen"] = absprachen
        if kopie_von:
            meta["kopie_von"] = str(kopie_von)
        k = ContextNode(id=uuid.uuid4(), category="knowledge", content_type="kapitel", title=titel,
                        status=cur.status, owner_pseudonym="system", read_scope=cur.read_scope,
                        write_scope=cur.write_scope, subject_id=cur.subject_id, metadata_=meta)
        self.db.add(k)
        await self.db.flush()
        self.db.add(ContextEdge(from_node_id=k.id, to_node_id=cur.id, relation="part_of", metadata_={}))
        await self.db.flush()
        return k


def _abspr(fach, kapitel=None, art="vorher", text="", aid=None):
    return {"id": aid or str(uuid.uuid4()), "fach_code": fach, "kapitel_id": str(kapitel.id) if kapitel else None,
            "kapitel_titel": kapitel.title if kapitel else None, "art": art, "text": text}


@pytest_asyncio.fixture
async def w(db_session):
    w = Welt(db_session)
    w.m = await _fach(db_session, "mathematik-ay2", "MAY")
    w.ph = await _fach(db_session, "physik-ay2", "PHAY")
    w.m8 = await w.curriculum(w.m, "Mathematik Kl. 8")
    w.brueche = await w.kapitel(w.m8, "Brüche")
    w.ph8 = await w.curriculum(w.ph, "Physik Kl. 8")
    w.vorher = _abspr("MAY", w.brueche, "vorher", "Bruchrechnung zuerst")
    w.dichte = await w.kapitel(w.ph8, "Dichte", [w.vorher, _abspr("MAY", art="abgestimmt", text="Einheiten gleich")])
    # Mathematik hält die Gegenabsprache fest
    w.brueche.metadata_ = {**w.brueche.metadata_, "absprachen": [_abspr("PHAY", w.dichte, "nachher")]}
    await db_session.flush()
    return w


async def test_beide_richtungen_beidseitig_und_fach(db_session, w):
    r = await absprachen_des_curriculums(db_session, w.m8, LEHRKRAFT)
    k = r["kapitel"][str(w.brueche.id)]
    [eigen] = k["eigene"]
    assert (eigen["fach_code"], eigen["art"], eigen["ziel"]["kapitel"], eigen["ziel"]["curriculum"]) == (
        "PHAY", "nachher", "Dichte", "Physik Kl. 8")
    [aussen] = k["von_aussen"]
    assert (aussen["fach_code"], aussen["art"], aussen["art_hier"], aussen["text"]) == (
        "PHAY", "vorher", "nachher", "Bruchrechnung zuerst")
    assert aussen["quelle"]["kapitel"] == "Dichte" and eigen["beidseitig"] and aussen["beidseitig"]
    assert eigen["text_gegenseite"] == "Bruchrechnung zuerst"
    [an_fach] = r["fach"]
    assert (an_fach["art"], an_fach["text"], an_fach["quelle"]["curriculum"]) == ("abgestimmt", "Einheiten gleich",
                                                                                  "Physik Kl. 8")
    # Von der Physik aus gesehen
    r = await absprachen_des_curriculums(db_session, w.ph8, LEHRKRAFT)
    k = r["kapitel"][str(w.dichte.id)]
    assert [e["art"] for e in k["eigene"]] == ["vorher", "abgestimmt"]
    assert k["eigene"][0]["beidseitig"] and not k["eigene"][1]["beidseitig"]
    assert k["eigene"][1]["ziel"] is None
    assert [a["quelle"]["kapitel"] for a in k["von_aussen"]] == ["Brüche"]


async def test_fach_absprache_nur_bei_ueberschneidenden_stufen(db_session, w):
    m5 = await w.curriculum(w.m, "Mathematik Kl. 5/6", (5, 6))
    await w.kapitel(m5, "Zahlen")
    assert (await absprachen_des_curriculums(db_session, m5, LEHRKRAFT))["fach"] == []


async def test_ersatz_auf_beiden_seiten(db_session, w):
    # Mathematik wird ersetzt: die Absprache der Physik zeigt auf das alte Kapitel
    m8neu = await w.curriculum(w.m, "Mathematik Kl. 8 neu", kopie_von=w.m8.id)
    brueche_neu = await w.kapitel(m8neu, "Brüche", kopie_von=w.brueche.id)
    # Physik wird ersetzt: Ziel der Mathematik-Absprache ist das archivierte Kapitel
    ph8neu = await w.curriculum(w.ph, "Physik Kl. 8 neu", kopie_von=w.ph8.id)
    dichte_neu = await w.kapitel(ph8neu, "Dichte", [w.vorher], kopie_von=w.dichte.id)
    brueche_neu.metadata_ = {**brueche_neu.metadata_, "absprachen": w.brueche.metadata_["absprachen"]}
    for n in (w.m8, w.brueche, w.ph8, w.dichte):
        n.status = "archived"
    await db_session.flush()

    r = await absprachen_des_curriculums(db_session, m8neu, LEHRKRAFT)
    k = r["kapitel"][str(brueche_neu.id)]
    assert k["eigene"][0]["ziel"]["kapitel_id"] == str(dichte_neu.id)
    assert [a["quelle"]["kapitel_id"] for a in k["von_aussen"]] == [str(dichte_neu.id)]
    assert k["eigene"][0]["beidseitig"]


async def test_entwurf_als_kopie_doppelt_nicht_schueler_sehen_keine_entwuerfe(db_session, w):
    entwurf = await w.curriculum(w.ph, "Physik Kl. 8 (Entwurf)", status="draft", kopie_von=w.ph8.id)
    neu = _abspr("MAY", w.brueche, "gleichzeitig", "nur im Entwurf")
    await w.kapitel(entwurf, "Dichte", [w.vorher, neu], kopie_von=w.dichte.id)
    r = await absprachen_des_curriculums(db_session, w.m8, LEHRKRAFT)
    aussen = r["kapitel"][str(w.brueche.id)]["von_aussen"]
    assert sorted((a["text"], a["quelle"]["status"]) for a in aussen) == [
        ("Bruchrechnung zuerst", "active"), ("nur im Entwurf", "draft")]
    r = await absprachen_des_curriculums(db_session, w.m8, SCHUELER)
    assert [a["text"] for a in r["kapitel"][str(w.brueche.id)]["von_aussen"]] == ["Bruchrechnung zuerst"]


async def test_private_quelle_bleibt_verborgen(db_session, w):
    privat = await w.curriculum(w.ph, "Physik privat", scope="private")
    await w.kapitel(privat, "Geheim", [_abspr("MAY", w.brueche, "vorher", "privat")])
    r = await absprachen_des_curriculums(db_session, w.m8, LEHRKRAFT)
    assert "privat" not in [a["text"] for a in r["kapitel"][str(w.brueche.id)]["von_aussen"]]


async def test_route(db_session, w):
    from app.context.router import router

    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: LEHRKRAFT
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/context/curricula/{w.m8.id}/absprachen")
        assert r.status_code == 200, r.text
        assert r.json()["kapitel"][str(w.brueche.id)]["eigene"][0]["fach_code"] == "PHAY"
        assert (await c.get(f"/context/curricula/{uuid.uuid4()}/absprachen")).status_code == 404


async def test_speichern_ueber_den_knoten(db_session, w, monkeypatch):
    from app.context.router import router

    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)

    admin = JwtPayload(sub="ay2-admin", roles=["admin", "teacher"], grade=None, jti="j", iat=0, exp=9999999999)
    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: admin
    meta = {**w.brueche.metadata_, "absprachen": [
        {"fach_code": "phay", "kapitel_id": str(w.dichte.id), "art": "gleichzeitig", "text": " zusammen "}]}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.patch(f"/context/nodes/{w.brueche.id}", json={"metadata": meta})
        assert r.status_code == 200, r.text
        [a] = r.json()["metadata"]["absprachen"]
        assert (a["fach_code"], a["text"], a["kapitel_titel"]) == ("PHAY", "zusammen", "Dichte")
        meta["absprachen"] = [{"fach_code": "PHAY", "art": "vorher"}]
        r = await c.patch(f"/context/nodes/{w.brueche.id}", json={"metadata": meta})
        assert r.status_code == 422 and "braucht ein Kapitel" in r.json()["detail"]


async def test_yaml_rundweg_aufloesen_und_warnungen(db_session, w):
    """Export schreibt Fach und Kapiteltitel; der Import löst sie wieder auf (Schritt 5)."""
    from app.context.absprachen import aus_yaml_aufloesen, export_zeilen, fuer_yaml
    from app.context.service import load_curriculum_tree

    w.m8.metadata_ = {"jahrgangsstufe": "8"}
    w.ph8.metadata_ = {"jahrgangsstufe": "8"}
    await db_session.flush()
    raus = await fuer_yaml(db_session, w.brueche.metadata_["absprachen"])
    assert raus == [{"fach_code": "PHAY", "kapitel": "Dichte", "jahrgangsstufe": "8", "art": "nachher"}]

    rein, warnungen = await aus_yaml_aufloesen(db_session, [
        {"fach_code": "PHAY", "kapitel_titel": "dichte ", "jahrgangsstufe": "8", "art": "nachher", "text": ""},
        {"fach_code": "PHAY", "kapitel_titel": "Gibt es nicht", "jahrgangsstufe": None, "art": "vorher", "text": ""},
        {"fach_code": "XXAY", "kapitel_titel": None, "jahrgangsstufe": None, "art": "abgestimmt", "text": "t"},
    ], "8")
    assert rein[0]["kapitel_id"] == str(w.dichte.id) and rein[0]["kapitel_titel"] == "Dichte"
    assert rein[1]["kapitel_id"] is None and rein[1]["kapitel_titel"] == "Gibt es nicht"
    assert len(rein) == 2
    assert any("nicht gefunden" in x for x in warnungen) and any("„XXAY“" in x for x in warnungen)

    # Gleicher Titel in zwei Curricula: die Stufe entscheidet, sonst Warnung
    ph9 = await w.curriculum(w.ph, "Physik Kl. 9", (9, 9))
    ph9.metadata_ = {"jahrgangsstufe": "9"}
    dichte9 = await w.kapitel(ph9, "Dichte")
    await db_session.flush()
    rein, warnungen = await aus_yaml_aufloesen(db_session, [
        {"fach_code": "PHAY", "kapitel_titel": "Dichte", "jahrgangsstufe": "9", "art": "vorher", "text": ""}])
    assert rein[0]["kapitel_id"] == str(dichte9.id) and warnungen == []
    rein, warnungen = await aus_yaml_aufloesen(db_session, [
        {"fach_code": "PHAY", "kapitel_titel": "Dichte", "jahrgangsstufe": None, "art": "vorher", "text": ""}])
    assert rein[0]["kapitel_id"] is None and "nicht eindeutig" in warnungen[0]

    # PDF/DOCX: kompakte Zeilen der eigenen Absprachen
    tree = await load_curriculum_tree(db_session, w.ph8.id)
    assert tree
    zeilen = await export_zeilen(db_session, tree)
    assert zeilen[str(w.dichte.id)] == ["Mathematik · Brüche — kommt vorher: Bruchrechnung zuerst",
                                        "Mathematik · ganzes Fach — abgestimmt: Einheiten gleich"]
