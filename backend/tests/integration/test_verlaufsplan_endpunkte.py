"""Endpunkte der Jahresverlaufspläne (Päckchen BD, Schritt 4). Erfordert TEST_DATABASE_URL.

Der Kalender kommt aus dem Test, nicht aus `config/`: „laufend“ ist hier 2025/26 mit den
Ferien der Schule, 2026/27 ist das kommende Jahr ohne Kalender, 2024/25 das Archiv.
"""
import uuid

import pytest
import pytest_asyncio

from app.context import verlaufsplan as vp
from app.db.models import ContextEdge, ContextNode, Group, GroupMembership, Subject

from tests.unit.test_verlaufsplan_zeit import KALENDER_2025_26

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]
MITGLIED = f"vp-fs-{TOKEN}"
FREMD = f"vp-fremd-{TOKEN}"


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    monkeypatch.setattr(vp, "aktuelles_schuljahr", lambda: "2025/26")
    monkeypatch.setattr(vp, "kalender_fuer", lambda sj: KALENDER_2025_26 if sj == "2025/26" else None)
    return db_session


@pytest_asyncio.fixture
async def welt(db):
    fach = Subject(slug=f"m-{TOKEN}", name=f"Mathe {TOKEN}", sort_order=0)
    db.add(fach)
    await db.flush()
    fs = Group(name=f"FS {TOKEN}", slug=f"fs-vp-{TOKEN}", type="subject_department", subject_id=fach.id)
    db.add(fs)
    await db.flush()
    db.add(GroupMembership(group_id=fs.id, pseudonym=MITGLIED, role_in_group="teacher"))
    cur = ContextNode(category="knowledge", content_type="curriculum", title=f"M Kl. 9 {TOKEN}",
                      status="active", subject_id=fach.id, min_grade=9, max_grade=9,
                      read_scope="school", write_scope="private", owner_pseudonym="x",
                      metadata_={"jahrgangsstufe": "9", "rahmen": {"wochenstunden": {"9": 4}}})
    db.add(cur)
    await db.flush()
    kap = []
    for i, (titel, std) in enumerate([("Ähnlichkeit", 12), ("Pythagoras", 20)]):
        k = ContextNode(category="knowledge", content_type="kapitel", title=titel, status="active",
                        subject_id=fach.id, read_scope="school", write_scope="private", owner_pseudonym="x",
                        metadata_={"std": std, "reihenfolge": i})
        db.add(k)
        await db.flush()
        db.add(ContextEdge(from_node_id=k.id, to_node_id=cur.id, relation="part_of"))
        kap.append(k)
    await db.flush()
    return {"fach": fach, "kapitel": kap}


def _person(sub, *rollen):
    from app.auth.jwt import JwtPayload

    return JwtPayload(sub=sub, roles=list(rollen), grade="9" if "student" in rollen else None,
                      jti="j", iat=0, exp=9999999999)


def _client(db, user):
    import httpx
    from fastapi import FastAPI

    from app.auth.dependencies import get_current_user
    from app.context.router import router as allgemein
    from app.context.verlaufsplan_router import router
    from app.db.session import get_db

    app = FastAPI()
    app.include_router(router)
    app.include_router(allgemein)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


FS = lambda: _person(MITGLIED, "teacher")  # noqa: E731
LK = lambda: _person(FREMD, "teacher")     # noqa: E731


async def _anlegen(db, welt, **kw):
    daten = {"subject_id": welt["fach"].id, "stufe": 9, "schuljahr": "2025/26",
             "abschnitte": [{"titel": "Ähnlichkeit", "wochen": 4, "kapitel_ids": [str(welt["kapitel"][0].id)]},
                            {"titel": "Pythagoras", "wochen": 6, "kapitel_ids": [str(welt["kapitel"][1].id)]}],
             "raster": 4, **kw}
    async with _client(db, FS()) as c:
        return await c.post("/context/verlaufsplaene", json=daten)


async def test_fachschaft_legt_entwurf_an_mit_lage_und_bilanz(db, welt):
    r = await _anlegen(db, welt)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "draft" and p["stufe"] == 9 and p["schuljahr"] == "2025/26"
    assert p["titel"] == f"Jahresverlaufsplan Mathe {TOKEN} Kl. 9 2025/26"
    assert p["darf_bearbeiten"] and p["darf_beschliessen"] and not p["kalender_fehlt"]
    assert all(a["id"] for a in p["abschnitte"])
    lage = p["lage"]
    assert [(a["von_woche"], a["bis_woche"]) for a in lage["abschnitte"]] == [(1, 4), (5, 10)]
    assert lage["abschnitte"][1]["ueber_ferien"] == ["Herbstferien"]
    assert (lage["belegt"], lage["frei"]) == (10, 27)
    bilanz = {k["titel"]: (k["soll"], k["geplant"]) for k in lage["kapitel"]}
    assert bilanz == {"Ähnlichkeit": (12, 16.0), "Pythagoras": (20, 24.0)}
    assert p["wochenstunden"] == 4
    # Kanten auf die Kapitel
    kanten = (await db.execute(
        ContextEdge.__table__.select().where(ContextEdge.from_node_id == uuid.UUID(p["id"])))).all()
    assert {k.to_node_id for k in kanten} == {k.id for k in welt["kapitel"]}


async def test_doppelt_gibt_409(db, welt):
    assert (await _anlegen(db, welt)).status_code == 201
    r = await _anlegen(db, welt)
    assert r.status_code == 409


async def test_rechte(db, welt):
    plan_id = (await _anlegen(db, welt)).json()["id"]
    async with _client(db, LK()) as c:
        assert (await c.post("/context/verlaufsplaene", json={
            "subject_id": welt["fach"].id, "stufe": 10, "schuljahr": "2025/26"})).status_code == 403
        r = await c.get(f"/context/verlaufsplaene/{plan_id}")
        assert r.status_code == 200 and not r.json()["darf_bearbeiten"]
        assert (await c.put(f"/context/verlaufsplaene/{plan_id}", json={"abschnitte": []})).status_code == 403
        assert (await c.post(f"/context/verlaufsplaene/{plan_id}/beschliessen")).status_code == 403
        assert (await c.delete(f"/context/verlaufsplaene/{plan_id}")).status_code == 403
    async with _client(db, _person("s", "student")) as c:
        assert (await c.get("/context/verlaufsplaene")).status_code == 403
        assert (await c.get(f"/context/verlaufsplaene/{plan_id}")).status_code == 403
    # Admin ohne Fachschaft darf
    async with _client(db, _person("adm", "teacher", "admin")) as c:
        r = await c.get(f"/context/verlaufsplaene/{plan_id}")
        assert r.json()["darf_bearbeiten"]


async def test_speichern_beschliessen_loeschen(db, welt):
    plan_id = (await _anlegen(db, welt)).json()["id"]
    async with _client(db, FS()) as c:
        r = await c.put(f"/context/verlaufsplaene/{plan_id}", json={
            "abschnitte": [{"titel": " Wahrscheinlichkeit ", "wochen": 8}], "raster": 1})
        assert r.status_code == 200
        p = r.json()
        assert [a["titel"] for a in p["abschnitte"]] == ["Wahrscheinlichkeit"]
        assert p["raster"] == 1 and p["lage"]["abschnitte"][0]["lang"]
        # Kapitel nicht mehr genannt: Kanten weg, beide als „ohne Abschnitt“
        assert len(p["lage"]["kapitel_ohne_abschnitt"]) == 2
        assert (await db.execute(ContextEdge.__table__.select().where(
            ContextEdge.from_node_id == uuid.UUID(plan_id)))).all() == []
        # Ungültig
        assert (await c.put(f"/context/verlaufsplaene/{plan_id}", json={
            "abschnitte": [{"wochen": 0}]})).status_code == 422

        r = await c.post(f"/context/verlaufsplaene/{plan_id}/beschliessen")
        assert r.status_code == 200 and r.json()["status"] == "active" and r.json()["beschlossen_am"]
        assert not r.json()["darf_beschliessen"]
        assert (await c.post(f"/context/verlaufsplaene/{plan_id}/beschliessen")).status_code == 409
        # Nach dem Beschluss direkt änderbar, bleibt beschlossen
        r = await c.put(f"/context/verlaufsplaene/{plan_id}", json={"abschnitte": [{"wochen": 2}]})
        assert r.status_code == 200 and r.json()["status"] == "active"

        assert (await c.delete(f"/context/verlaufsplaene/{plan_id}")).status_code == 204
        assert (await c.get(f"/context/verlaufsplaene/{plan_id}")).status_code == 404


async def test_kommendes_jahr_ohne_kalender_und_vergangenes_nicht(db, welt):
    r = await _anlegen(db, welt, schuljahr="2026/27")
    assert r.status_code == 201
    assert r.json()["kalender_fehlt"] and r.json()["lage"] is None
    assert (await _anlegen(db, welt, schuljahr="2024/25")).status_code == 422
    assert (await _anlegen(db, welt, schuljahr="2025/27")).status_code == 422


async def test_archiv_nur_lesbar(db, welt):
    alt = ContextNode(category="knowledge", content_type="verlaufsplan", title="alt", status="active",
                      subject_id=welt["fach"].id, min_grade=9, max_grade=9, read_scope="school",
                      write_scope="private", owner_pseudonym=MITGLIED,
                      metadata_={"schuljahr": "2024/25", "abschnitte": [{"id": "x", "wochen": 3}]})
    db.add(alt)
    await db.flush()
    async with _client(db, FS()) as c:
        r = await c.get(f"/context/verlaufsplaene/{alt.id}")
        assert r.status_code == 200
        assert r.json()["archiviert"] and not r.json()["darf_bearbeiten"] and r.json()["kalender_fehlt"]
        assert (await c.put(f"/context/verlaufsplaene/{alt.id}", json={"abschnitte": []})).status_code == 409
        assert (await c.delete(f"/context/verlaufsplaene/{alt.id}")).status_code == 409

        liste = (await c.get("/context/verlaufsplaene", params={"subject_id": welt["fach"].id})).json()
        assert liste["aktuelles_schuljahr"] == "2025/26" and liste["darf_anlegen"]
        assert [p["archiviert"] for p in liste["plaene"]] == [True]


async def test_allgemeine_wege_sind_gesperrt(db, welt):
    plan_id = (await _anlegen(db, welt)).json()["id"]
    async with _client(db, FS()) as c:
        r = await c.patch(f"/context/nodes/{plan_id}", json={"metadata": {"abschnitte": [{"wochen": 99}]}})
        assert r.status_code == 422 and "eigenen Ansicht" in r.json()["detail"]
        for r in [
            await c.delete(f"/context/nodes/{plan_id}"),
            await c.patch(f"/context/nodes/{plan_id}/verwalten", json={"status": "archived"}),
            await c.post("/context/nodes", json={
                "category": "knowledge", "content_type": "verlaufsplan", "title": "x",
                "read_scope": "school", "write_scope": "private"}),
        ]:
            assert r.status_code == 422 and r.json()["detail"] == vp.EIGENER_WEG, r.text
