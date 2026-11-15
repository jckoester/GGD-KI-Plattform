"""Fachfremde IK/PK in Curricula umhängen (0.45, `scripts/curriculum_kompetenzen_reparieren.py`).

Der Import vor dem 25.08.2026 löste PK-Nummern ohne Fach auf. Das Skript sucht dieselbe Nummer
im Fach und in der Fassung des Curriculums und hängt Eintrag und Kante um — nur bei genau einem
Treffer. Verweise in Hinweisen bleiben; der Probelauf schreibt nichts; ein zweiter Lauf findet
nichts mehr.
"""
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.context.curriculum_abdeckung import abdeckung
from app.context.kompetenz_reparatur import kompetenzen_reparieren
from app.context.service import load_curriculum_tree
from app.db.models import ContextEdge, ContextNode, Subject

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]
BP = "2016"


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


async def _k(db, typ, titel, fach, **kw):
    n = ContextNode(category="knowledge", content_type=typ, title=titel, status=kw.pop("status", "active"),
                    read_scope="global", write_scope="global", owner_pseudonym="system",
                    subject_id=fach.id if fach else None, **kw)
    db.add(n)
    await db.flush()
    return n


@pytest_asyncio.fixture
async def welt(db):
    mathe = Subject(slug=f"m-{TOKEN}", name=f"Mathe {TOKEN}", fach_code=f"M{TOKEN[:4]}".upper())
    kunst = Subject(slug=f"k-{TOKEN}", name=f"Kunst {TOKEN}", fach_code=f"K{TOKEN[:4]}".upper())
    db.add_all([mathe, kunst])
    await db.flush()

    async def kompetenz(typ, nr, fach, **kw):
        return await _k(db, typ, f"{nr} {fach.name}", fach, bp_version=BP,
                        metadata_={"kompetenz_nr": nr, "thematische_gruppe": "G"}, **kw)

    k = {
        "pk_m": await kompetenz("pk_kompetenz", "2.1.1", mathe, status="archived"),  # alte Fassung: archiviert
        "pk_k": await kompetenz("pk_kompetenz", "2.1.1", kunst),
        "pk_k2": await kompetenz("pk_kompetenz", "2.9.9", kunst),                    # gibt es in Mathe nicht
        "ik_m": await kompetenz("ik_kompetenz", "3.1(1)", mathe, min_grade=9, max_grade=10),
        "ik_m_78": await kompetenz("ik_kompetenz", "3.1(1)", mathe, min_grade=7, max_grade=8),
        "ik_k": await kompetenz("ik_kompetenz", "3.1(1)", kunst, min_grade=9, max_grade=10),
        "ik_hinweis": await kompetenz("ik_kompetenz", "3.5(5)", kunst, min_grade=9, max_grade=10),
    }
    gemeinsam = dict(subject_id=mathe.id, min_grade=9, max_grade=9)
    cur = await _k(db, "curriculum", f"M9 {TOKEN}", mathe, min_grade=9, max_grade=9,
                   metadata_={"bp_version": BP})
    kap = await _k(db, "kapitel", "Kap", mathe, min_grade=9, max_grade=9)
    eintrag = {
        "ik": [{"nr": "3.1(1)", "node_id": str(k["ik_k"].id), "partiell": True}],
        "pk": [{"pk_id": "2.1.1", "node_id": str(k["pk_k"].id)},
               {"pk_id": "2.9.9", "node_id": str(k["pk_k2"].id)}],
        "hinweise": f"Siehe #[3.5(5)](ik:{k['ik_hinweis'].id})",
    }
    ls = await _k(db, "lernsequenz", "LS", mathe, min_grade=9, max_grade=9, metadata_={"eintraege": [eintrag]})
    db.add_all([
        ContextEdge(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"),
        ContextEdge(from_node_id=ls.id, to_node_id=kap.id, relation="part_of"),
        ContextEdge(from_node_id=ls.id, to_node_id=k["ik_k"].id, relation="references", metadata_={"partiell": "true"}),
        ContextEdge(from_node_id=ls.id, to_node_id=k["pk_k"].id, relation="develops"),
        ContextEdge(from_node_id=ls.id, to_node_id=k["pk_k2"].id, relation="develops"),
        ContextEdge(from_node_id=ls.id, to_node_id=k["ik_hinweis"].id, relation="references"),
    ])
    await db.flush()
    return {"cur": cur, "ls": ls, "k": k, "gemeinsam": gemeinsam}


async def _ziele(db, ls):
    return {(r, t) for r, t in (await db.execute(sa.select(ContextEdge.relation, ContextEdge.to_node_id).where(
        ContextEdge.from_node_id == ls.id, ContextEdge.relation != "part_of"))).all()}


async def test_abdeckung_meldet_fremdes_fach(db, welt):
    a = await abdeckung(db, await load_curriculum_tree(db, welt["cur"].id))
    assert sorted((f["typ"], f["nr"]) for f in a["fremdes_fach"]) == [("ik", "3.1(1)"), ("pk", "2.1.1"), ("pk", "2.9.9")]
    assert all(f["fach"] == f"Kunst {TOKEN}" for f in a["fremdes_fach"])  # der Hinweis-Verweis zählt nicht


async def test_probelauf_schreibt_nichts(db, welt):
    vorher = await _ziele(db, welt["ls"])
    funde = await kompetenzen_reparieren(db, curriculum_id=welt["cur"].id)
    assert len(funde) == 3
    assert await _ziele(db, welt["ls"]) == vorher
    await db.refresh(welt["ls"])
    assert welt["ls"].metadata_["eintraege"][0]["pk"][0]["node_id"] == str(welt["k"]["pk_k"].id)


async def test_umhaengen(db, welt):
    k, ls = welt["k"], welt["ls"]
    funde = await kompetenzen_reparieren(db, curriculum_id=welt["cur"].id, anwenden=True)
    ergebnis = {(f.typ, f.nr): f for f in funde}
    assert ergebnis[("pk", "2.1.1")].neu_id == k["pk_m"].id           # auch archiviert (alte Fassung)
    assert ergebnis[("ik", "3.1(1)")].neu_id == k["ik_m"].id           # das aus dem Band 9/10
    assert ergebnis[("pk", "2.9.9")].neu_id is None and "keine" in ergebnis[("pk", "2.9.9")].grund

    await db.refresh(ls)
    e = ls.metadata_["eintraege"][0]
    assert e["ik"] == [{"nr": "3.1(1)", "node_id": str(k["ik_m"].id), "partiell": True}]
    assert [p["node_id"] for p in e["pk"]] == [str(k["pk_m"].id), str(k["pk_k2"].id)]
    assert await _ziele(db, ls) == {
        ("references", k["ik_m"].id), ("develops", k["pk_m"].id), ("develops", k["pk_k2"].id),
        ("references", k["ik_hinweis"].id),  # Hinweis: gewollter Fachbezug, bleibt
    }
    partiell = (await db.execute(sa.select(ContextEdge.metadata_).where(
        ContextEdge.from_node_id == ls.id, ContextEdge.to_node_id == k["ik_m"].id))).scalar_one()
    assert partiell == {"partiell": "true"}

    zweiter = await kompetenzen_reparieren(db, curriculum_id=welt["cur"].id, anwenden=True)
    assert [(f.nr, f.neu_id) for f in zweiter] == [("2.9.9", None)]  # nur der unlösbare bleibt
