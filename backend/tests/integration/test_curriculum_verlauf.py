"""Rückgängig im Curriculum-Editor (0.46, Päckchen AP Teil B, Schritt 3).

Vor dem Speichern hält der Editor den Stand fest; „Rückgängig“ stellt ihn wieder her:
geänderte Felder und Einträge, gelöschte Kapitel samt Lernsequenzen (mit derselben Kennung und
der Einheit, die daran hing), neue Teile verschwinden, Kompetenzkanten wie vorher. Der Status
bleibt der heutige. Nur wer schreiben darf, sichert und nimmt zurück.
"""
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException

from app.auth.jwt import JwtPayload
from app.context.curriculum_verlauf import VERLAUF_LIMIT, sichern
from app.context.router import curriculum_sichern, curriculum_verlauf_lesen, curriculum_zuruecknehmen
from app.db.models import (
    ContextEdge, ContextNode, CurriculumSnapshot, Group, GroupMembership, Subject,
)

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]
MITGLIED = f"mitglied-{TOKEN}"


def _user(sub, *rollen):
    return JwtPayload(sub=sub, roles=list(rollen), role=rollen[0], grade=None,
                      exp=9999999999, iat=0, jti=str(uuid.uuid4()))


LEHRKRAFT = _user(MITGLIED, "teacher")
KOLLEGIN = _user(f"kollegin-{TOKEN}", "teacher")
FREMDE = _user(f"fremd-{TOKEN}", "teacher")


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


@pytest_asyncio.fixture
async def welt(db):
    fach = Subject(slug=f"vl-{TOKEN}", name=f"Verlauf {TOKEN}", fach_code=f"V{TOKEN[:4]}".upper())
    db.add(fach)
    await db.flush()
    fs = Group(name=f"FS {TOKEN}", slug=f"fs-vl-{TOKEN}", type="subject_department", subject_id=fach.id)
    db.add(fs)
    await db.flush()
    db.add_all([GroupMembership(group_id=fs.id, pseudonym=MITGLIED, role_in_group="teacher"),
                GroupMembership(group_id=fs.id, pseudonym=KOLLEGIN.sub, role_in_group="teacher")])

    def knoten(typ, titel, **kw):
        return ContextNode(category="knowledge", content_type=typ, title=titel, status="draft",
                           read_scope="school", write_scope="subject", write_scope_group_id=fs.id,
                           subject_id=fach.id, owner_pseudonym=MITGLIED, min_grade=9, max_grade=9, **kw)

    ik = ContextNode(category="knowledge", content_type="ik_kompetenz", title="IK", status="active",
                     read_scope="global", write_scope="global", owner_pseudonym="system", subject_id=fach.id)
    pk = ContextNode(category="knowledge", content_type="pk_kompetenz", title="PK", status="active",
                     read_scope="global", write_scope="global", owner_pseudonym="system", subject_id=fach.id)
    cur = knoten("curriculum", "Cur", metadata_={"jahrgangsstufe": "9"})
    kap = knoten("kapitel", "Kapitel 1", metadata_={"reihenfolge": 1})
    ls = knoten("lernsequenz", "LS 1", metadata_={"std": "6", "eintraege": [
        {"ik": [{"nr": "3.1(1)", "node_id": None}], "begriffe": [{"name": "Atom"}]}]})
    einheit = ContextNode(category="knowledge", content_type="unterrichtseinheit", title="Einheit",
                          status="active", read_scope="private", write_scope="private",
                          owner_pseudonym=KOLLEGIN.sub, subject_id=fach.id)
    db.add_all([ik, pk, cur, kap, ls, einheit])
    await db.flush()
    db.add_all([ContextEdge(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"),
                ContextEdge(from_node_id=ls.id, to_node_id=kap.id, relation="part_of"),
                ContextEdge(from_node_id=ls.id, to_node_id=ik.id, relation="references",
                            metadata_={"partiell": "true"}),
                ContextEdge(from_node_id=einheit.id, to_node_id=kap.id, relation="references")])
    await db.flush()
    return {"fach": fach, "fs": fs, "ik": ik, "pk": pk, "cur": cur, "kap": kap, "ls": ls, "einheit": einheit}


async def _kanten(db, von):
    return {(r, z) for r, z in (await db.execute(sa.select(ContextEdge.relation, ContextEdge.to_node_id)
                                                  .where(ContextEdge.from_node_id == von))).all()}


async def _knoten(db, nid):
    return await db.get(ContextNode, nid, populate_existing=True)


async def test_aenderungen_werden_zurueckgenommen(db, welt):
    w = welt
    await curriculum_sichern(w["cur"].id, db=db, user=LEHRKRAFT)

    # „Speichern“: Titel und Einträge ändern, Kompetenz tauschen, ein Kapitel dazu.
    w["ls"].title = "LS geändert"
    w["ls"].metadata_ = {"std": "8", "eintraege": []}
    await db.execute(sa.delete(ContextEdge).where(ContextEdge.from_node_id == w["ls"].id,
                                                  ContextEdge.relation == "references"))
    db.add(ContextEdge(from_node_id=w["ls"].id, to_node_id=w["pk"].id, relation="develops"))
    neu = ContextNode(category="knowledge", content_type="kapitel", title="Kapitel 2", status="draft",
                      read_scope="school", write_scope="subject", write_scope_group_id=w["fs"].id,
                      subject_id=w["fach"].id, owner_pseudonym=MITGLIED)
    db.add(neu)
    await db.flush()
    db.add(ContextEdge(from_node_id=neu.id, to_node_id=w["cur"].id, relation="part_of"))
    await db.flush()

    antwort = await curriculum_zuruecknehmen(w["cur"].id, db=db, user=LEHRKRAFT)
    assert antwort["zurueckgenommen"]["grund"] == "editor" and antwort["anzahl"] == 0

    ls = await _knoten(db, w["ls"].id)
    assert ls.title == "LS 1"
    assert ls.metadata_["eintraege"][0]["begriffe"] == [{"name": "Atom"}]
    assert await _kanten(db, w["ls"].id) == {("part_of", w["kap"].id), ("references", w["ik"].id)}
    partiell = (await db.execute(sa.select(ContextEdge.metadata_).where(
        ContextEdge.from_node_id == w["ls"].id, ContextEdge.to_node_id == w["ik"].id))).scalar_one()
    assert partiell == {"partiell": "true"}
    assert await _knoten(db, neu.id) is None


async def test_geloeschtes_kapitel_kommt_mit_derselben_kennung_zurueck(db, welt):
    w = welt
    await curriculum_sichern(w["cur"].id, db=db, user=LEHRKRAFT)
    kap_id, ls_id = w["kap"].id, w["ls"].id
    await db.execute(sa.delete(ContextNode).where(ContextNode.id.in_([kap_id, ls_id])))
    db.expunge(w["kap"])
    db.expunge(w["ls"])
    await db.flush()

    await curriculum_zuruecknehmen(w["cur"].id, db=db, user=LEHRKRAFT)
    assert (await _knoten(db, kap_id)).title == "Kapitel 1"
    assert (await _knoten(db, ls_id)).metadata_["std"] == "6"
    assert await _kanten(db, kap_id) == {("part_of", w["cur"].id)}
    assert await _kanten(db, w["einheit"].id) == {("references", kap_id)}  # die Einheit hängt wieder dran


async def test_status_bleibt_der_heutige(db, welt):
    w = welt
    await curriculum_sichern(w["cur"].id, db=db, user=LEHRKRAFT)
    for n in (w["cur"], w["kap"], w["ls"]):
        n.status = "active"
    w["ls"].title = "nach dem Veröffentlichen"
    await db.flush()

    await curriculum_zuruecknehmen(w["cur"].id, db=db, user=LEHRKRAFT)
    ls = await _knoten(db, w["ls"].id)
    assert ls.title == "LS 1" and ls.status == "active"
    assert (await _knoten(db, w["cur"].id)).status == "active"


async def test_schritt_fuer_schritt_und_ende(db, welt):
    w = welt
    await curriculum_sichern(w["cur"].id, db=db, user=LEHRKRAFT)
    w["ls"].title = "zweiter Stand"
    await db.flush()
    await curriculum_sichern(w["cur"].id, db=db, user=KOLLEGIN)
    w["ls"].title = "dritter Stand"
    await db.flush()

    stand = await curriculum_verlauf_lesen(w["cur"].id, db=db, user=LEHRKRAFT)
    assert stand["anzahl"] == 2 and stand["letzter"]["von_mir"] is False

    await curriculum_zuruecknehmen(w["cur"].id, db=db, user=LEHRKRAFT)
    assert (await _knoten(db, w["ls"].id)).title == "zweiter Stand"
    await curriculum_zuruecknehmen(w["cur"].id, db=db, user=LEHRKRAFT)
    assert (await _knoten(db, w["ls"].id)).title == "LS 1"
    with pytest.raises(HTTPException) as e:
        await curriculum_zuruecknehmen(w["cur"].id, db=db, user=LEHRKRAFT)
    assert e.value.status_code == 404


async def test_verlauf_ist_begrenzt(db, welt):
    for _ in range(VERLAUF_LIMIT + 2):
        await sichern(db, welt["cur"].id, grund="editor", von=MITGLIED)
    anzahl = await db.scalar(sa.select(sa.func.count()).where(
        CurriculumSnapshot.curriculum_id == welt["cur"].id))
    assert anzahl == VERLAUF_LIMIT


async def test_nur_wer_schreiben_darf(db, welt):
    for weg in (curriculum_sichern, curriculum_zuruecknehmen, curriculum_verlauf_lesen):
        with pytest.raises(HTTPException) as e:
            await weg(welt["cur"].id, db=db, user=FREMDE)
        # Entwurf: Fremde Lehrkräfte lesen ihn seit 0.52, den Verlauf führt nur die Fachschaft.
        assert e.value.status_code == 403
