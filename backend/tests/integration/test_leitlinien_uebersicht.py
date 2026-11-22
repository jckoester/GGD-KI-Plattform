"""Schulweite Übersicht einer Leitlinie (0.53, Päckchen AU Schritt 1) — über die echte Kette
Lernsequenz → Kapitel → Curriculum. Erfordert TEST_DATABASE_URL."""
import uuid

import pytest
import sqlalchemy as sa
import pytest_asyncio

from app.auth.jwt import JwtPayload
from app.context.leitlinien_uebersicht import leitlinien_uebersicht
from app.db.models import ContextEdge, ContextNode, Subject

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]
KZ = f"T{TOKEN[:4]}".upper()


def _user(sub, *rollen):
    return JwtPayload(sub=sub, roles=list(rollen), role=rollen[0], grade=None,
                      exp=9999999999, iat=0, jti=str(uuid.uuid4()))


LEHRKRAFT = _user(f"lk-{TOKEN}", "teacher")
SCHUELERIN = _user(f"s-{TOKEN}", "student")


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


def _knoten(typ, titel, status="active", **kw):
    return ContextNode(category="knowledge", content_type=typ, title=titel, status=status,
                       read_scope="school", write_scope="school", owner_pseudonym="system", **kw)


@pytest_asyncio.fixture
async def welt(db):
    """Leitlinie mit drei Aspekten; Mathematik mit einem veröffentlichten Curriculum und einer
    Kopie als Entwurf, die es ersetzen soll; Biologie mit einem Entwurf."""
    ll = _knoten("leitbild", f"Testleitlinie {TOKEN}", metadata_={"kuerzel": KZ})
    a1, a2, a3 = (_knoten("leitbild_aspekt", f"Aspekt {i} {TOKEN}",
                          metadata_={"kuerzel": f"{KZ}{i}", "leitlinie": KZ}) for i in (1, 2, 3))
    ma = Subject(slug=f"ma-{TOKEN}", name=f"Mathe {TOKEN}", fach_code=f"M{TOKEN[:3]}".upper())
    bio = Subject(slug=f"bio-{TOKEN}", name=f"Bio {TOKEN}", fach_code=f"B{TOKEN[:3]}".upper())
    db.add_all([ll, a1, a2, a3, ma, bio])
    await db.flush()

    async def curriculum(fach, titel, status, verweise, meta=None, kapitel_status=None):
        cur = _knoten("curriculum", titel, status, subject_id=fach.id, min_grade=7, max_grade=7,
                      metadata_={"bp_version": "2016", **(meta or {})})
        kap = _knoten("kapitel", f"Kap {titel}", kapitel_status or status, subject_id=fach.id,
                      metadata_={"reihenfolge": 1})
        ls = _knoten("lernsequenz", f"LS {titel}", status, subject_id=fach.id)
        db.add_all([cur, kap, ls])
        await db.flush()
        db.add_all([ContextEdge(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"),
                    ContextEdge(from_node_id=ls.id, to_node_id=kap.id, relation="part_of"),
                    *(ContextEdge(from_node_id=ls.id, to_node_id=z.id, relation="references") for z in verweise)])
        await db.flush()
        return cur

    ma_aktiv = await curriculum(ma, f"Ma7 {TOKEN}", "active", [a1, ll])
    ma_kopie = await curriculum(ma, f"Ma7 neu {TOKEN}", "draft", [a2], {"kopie_von": str(ma_aktiv.id)})
    bio_entwurf = await curriculum(bio, f"Bio7 {TOKEN}", "draft", [a1])
    # Ein archiviertes Kapitel in einem veröffentlichten Curriculum zählt nicht.
    await curriculum(bio, f"Bio8 {TOKEN}", "active", [a3], kapitel_status="archived")
    return {"ll": ll, "a": (a1, a2, a3), "ma": ma, "bio": bio, "ma_aktiv": ma_aktiv,
            "ma_kopie": ma_kopie, "bio_entwurf": bio_entwurf}


def _orte(aspekt):
    return sorted((f["curriculum"], f["status"]) for f in aspekt["fundstellen"])


async def test_lehrkraft_sieht_den_geplanten_stand(db, welt):
    u = await leitlinien_uebersicht(db, welt["ll"].id, LEHRKRAFT)
    a1, a2, a3 = u["aspekte"]
    # Die Kopie ersetzt Ma7: deren Verweis auf Aspekt 1 zählt nicht mehr, der der Kopie auf 2 schon.
    assert _orte(a1) == [(f"Bio7 {TOKEN}", "draft")]
    assert _orte(a2) == [(f"Ma7 neu {TOKEN}", "draft")]
    assert a3["fundstellen"] == []  # nur im archivierten Kapitel
    assert u["ohne_fundstelle"] == [f"{KZ}3"]
    assert u["ganz"] == []  # der Verweis auf die Leitlinie als Ganzes stand im ersetzten Ma7
    assert [f["name"] for f in u["faecher"]] == [f"Bio {TOKEN}", f"Mathe {TOKEN}"]
    assert a1["je_fach"] == {str(welt["bio"].id): 1}
    f = a2["fundstellen"][0]
    assert (f["fach"], f["kapitel"], f["lernsequenz"], f["stufen"], f["bp_version"]) == (
        f"Mathe {TOKEN}", f"Kap Ma7 neu {TOKEN}", f"LS Ma7 neu {TOKEN}", "7", "2016")
    assert u["nur_veroeffentlicht"] is False


async def test_nur_veroeffentlichte(db, welt):
    u = await leitlinien_uebersicht(db, welt["ll"].id, LEHRKRAFT, nur_veroeffentlicht=True)
    a1, a2, _ = u["aspekte"]
    assert _orte(a1) == [(f"Ma7 {TOKEN}", "active")]
    assert a2["fundstellen"] == []
    assert [f["curriculum"] for f in u["ganz"]] == [f"Ma7 {TOKEN}"]
    assert u["ohne_fundstelle"] == [f"{KZ}2", f"{KZ}3"]
    assert u["nur_veroeffentlicht"] is True


async def test_ohne_leserecht_fuer_entwuerfe_nur_veroeffentlichte(db, welt):
    """Die Funktion selbst; die Route sperrt Schüler:innen ohnehin (F2)."""
    u = await leitlinien_uebersicht(db, welt["ll"].id, SCHUELERIN)
    assert _orte(u["aspekte"][0]) == [(f"Ma7 {TOKEN}", "active")]
    assert u["nur_veroeffentlicht"] is True


async def test_archivierter_aspekt_und_unbekannte_leitlinie(db, welt):
    a1, _, a3 = welt["a"]
    a3.status = "archived"
    await db.flush()
    u = await leitlinien_uebersicht(db, welt["ll"].id, LEHRKRAFT)
    assert [a["kuerzel"] for a in u["aspekte"]] == [f"{KZ}1", f"{KZ}2"]
    assert await leitlinien_uebersicht(db, a1.id, LEHRKRAFT) is None  # ein Aspekt ist keine Leitlinie
    assert await leitlinien_uebersicht(db, uuid.uuid4(), LEHRKRAFT) is None


async def test_leitperspektive(db, welt):
    """F1: dieselbe Übersicht für eine Leitperspektive — Aspekte über `part_of`, Kürzel = bp_id."""
    lp = _knoten("leitperspektive", f"LP {TOKEN}", metadata_={"bp_id": f"BP2016BW_ALLG_LP_{KZ}"})
    asp = [_knoten("leitperspektive_aspekt", f"LP-Aspekt {i} {TOKEN}",
                   status="archived" if i == 3 else "active",
                   metadata_={"bp_id": f"{KZ}_{i:02d}", "kuerzel": KZ, "aspekt_nr": i}) for i in (10, 2, 3)]
    db.add_all([lp, *asp])
    await db.flush()
    db.add_all([ContextEdge(from_node_id=a.id, to_node_id=lp.id, relation="part_of") for a in asp])
    bio7_ls = (await db.execute(sa.select(ContextNode).where(ContextNode.title == f"LS Bio7 {TOKEN}"))).scalar_one()
    db.add(ContextEdge(from_node_id=bio7_ls.id, to_node_id=asp[1].id, relation="references"))
    await db.flush()

    u = await leitlinien_uebersicht(db, lp.id, LEHRKRAFT)
    assert u["art"] == "leitperspektive"
    assert u["leitlinie"]["kuerzel"] == KZ
    # natürlich sortiert, der archivierte Aspekt fehlt
    assert [a["kuerzel"] for a in u["aspekte"]] == [f"{KZ}_02", f"{KZ}_10"]
    assert _orte(u["aspekte"][0]) == [(f"Bio7 {TOKEN}", "draft")]
    assert u["ohne_fundstelle"] == [f"{KZ}_10"]
    # Ein Aspekt der Leitperspektive ist selbst keine
    assert await leitlinien_uebersicht(db, asp[0].id, LEHRKRAFT) is None
    # Die Leitlinie aus der Welt bleibt eine Leitlinie
    assert (await leitlinien_uebersicht(db, welt["ll"].id, LEHRKRAFT))["art"] == "leitlinie"
