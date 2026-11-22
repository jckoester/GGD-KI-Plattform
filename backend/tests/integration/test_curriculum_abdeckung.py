"""Abdeckung eines Curriculums (0.45, Päckchen AP Teil A, Schritt 3).

`GET /context/curricula/{id}/coverage`: je IK des Bands verknüpft, partiell oder fehlt — mit den
anderen veröffentlichten Curricula des Bands —, je PK die Zahl der Lernsequenzen; verknüpfte IK
außerhalb von Band oder Fassung gesondert. Ein Entwurf verrät auch seine Abdeckung nicht.
"""
import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.auth.jwt import JwtPayload
from app.context.router import curriculum_abdeckung
from app.db.models import ContextEdge, ContextNode, Group, GroupMembership, Subject

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]
MITGLIED = f"mitglied-abd-{TOKEN}"
BP = "2016.V3"


def _user(sub, *rollen):
    return JwtPayload(sub=sub, roles=list(rollen), role=rollen[0], grade=None,
                      exp=9999999999, iat=0, jti=str(uuid.uuid4()))


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


async def _knoten(db, typ, titel, **kw):
    write_scope = kw.pop("write_scope", "global")
    n = ContextNode(category="knowledge", content_type=typ, title=titel, status=kw.pop("status", "active"),
                    read_scope="global" if write_scope == "global" else "school", write_scope=write_scope,
                    owner_pseudonym="system", **kw)
    db.add(n)
    await db.flush()
    return n


@pytest_asyncio.fixture
async def welt(db):
    fach = Subject(slug=f"abd-{TOKEN}", name=f"Abd {TOKEN}", fach_code=f"A{TOKEN[:4]}".upper())
    db.add(fach)
    await db.flush()
    fs = Group(name=f"FS {TOKEN}", slug=f"fs-abd-{TOKEN}", type="subject_department", subject_id=fach.id)
    db.add(fs)
    await db.flush()
    db.add(GroupMembership(group_id=fs.id, pseudonym=MITGLIED, role_in_group="teacher"))

    async def kompetenz(typ, nr, gruppe, lo=None, hi=None, bp=BP):
        return await _knoten(db, typ, f"{nr} Text {nr}", subject_id=fach.id, bp_version=bp,
                             min_grade=lo, max_grade=hi,
                             metadata_={"kompetenz_nr": nr, "thematische_gruppe": gruppe})

    ik = {nr: await kompetenz("ik_kompetenz", nr, "3.1 Zahl", 9, 10)
          for nr in ("3.1(1)", "3.1(2)", "3.1(10)", "3.1(3)")}
    ik["7/8"] = await kompetenz("ik_kompetenz", "3.1(1)", "3.1 Zahl", 7, 8)           # anderes Band
    ik["V2"] = await kompetenz("ik_kompetenz", "3.1(9)", "3.1 Zahl", 9, 10, bp="2016.V2")  # andere Fassung
    pk = {nr: await kompetenz("pk_kompetenz", nr, "2.1 Argumentieren") for nr in ("2.1(1)", "2.1(2)")}

    async def curriculum(titel, lo, hi, status, lernsequenzen):
        gemeinsam = dict(subject_id=fach.id, min_grade=lo, max_grade=hi, status=status,
                         write_scope="subject", write_scope_group_id=fs.id)
        cur = await _knoten(db, "curriculum", titel, metadata_={"bp_version": BP}, **gemeinsam)
        kap = await _knoten(db, "kapitel", f"{titel} K", **gemeinsam)
        db.add(ContextEdge(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"))
        for ls_titel, kanten in lernsequenzen.items():
            # Gezählt werden die Spalten IK und PK der Einträge; die Kanten schreibt der Editor daraus.
            eintrag = {
                "ik": [{"node_id": str(z.id), "partiell": m.get("partiell") == "true"}
                       for z, rel, m in kanten if rel == "references"],
                "pk": [{"node_id": str(z.id)} for z, rel, _ in kanten if rel == "develops"],
            }
            ls = await _knoten(db, "lernsequenz", ls_titel, metadata_={"eintraege": [eintrag]}, **gemeinsam)
            db.add(ContextEdge(from_node_id=ls.id, to_node_id=kap.id, relation="part_of"))
            for ziel, relation, meta in kanten:
                db.add(ContextEdge(from_node_id=ls.id, to_node_id=ziel.id, relation=relation, metadata_=meta))
        await db.flush()
        return cur

    neun = await curriculum(f"Kl9 {TOKEN}", 9, 9, "draft", {
        "LS A": [(ik["3.1(1)"], "references", {"partiell": "false"}), (pk["2.1(1)"], "develops", {}),
                 (ik["V2"], "references", {"partiell": "false"})],
        "LS B": [(ik["3.1(2)"], "references", {"partiell": "true"}), (pk["2.1(1)"], "develops", {})],
    })
    await curriculum(f"Kl10 {TOKEN}", 10, 10, "active", {
        "LS C": [(ik["3.1(10)"], "references", {"partiell": "false"}),
                 (ik["3.1(2)"], "references", {"partiell": "false"})],
    })
    await curriculum(f"Entwurf10 {TOKEN}", 10, 10, "draft", {  # Entwürfe zählen nicht als „anderswo“
        "LS D": [(ik["3.1(3)"], "references", {"partiell": "false"})],
    })
    return {"neun": neun, "ik": ik, "pk": pk}


async def test_abdeckung_je_kompetenz(db, welt):
    a = await curriculum_abdeckung(welt["neun"].id, db=db, user=_user(MITGLIED, "teacher"))
    ik = a["ik"]
    assert {k: ik[k] for k in ("gesamt", "verknuepft", "partiell", "fehlt", "fehlt_anderswo")} == {
        "gesamt": 4, "verknuepft": 1, "partiell": 1, "fehlt": 2, "fehlt_anderswo": 1}
    [gruppe] = ik["gruppen"]
    assert gruppe["titel"] == "3.1 Zahl"
    zeilen = {k["nr"]: k for k in gruppe["kompetenzen"]}
    assert list(zeilen) == ["3.1(1)", "3.1(2)", "3.1(3)", "3.1(10)"]  # natürlich sortiert
    assert zeilen["3.1(1)"]["zustand"] == "verknuepft" and zeilen["3.1(1)"]["lernsequenzen"] == ["LS A"]
    assert zeilen["3.1(1)"]["titel"] == "Text 3.1(1)"
    assert zeilen["3.1(2)"]["zustand"] == "partiell" and zeilen["3.1(2)"]["anderswo"] == [f"Kl10 {TOKEN}"]
    assert zeilen["3.1(10)"]["zustand"] == "fehlt" and zeilen["3.1(10)"]["anderswo"] == [f"Kl10 {TOKEN}"]
    assert "anderswo" not in zeilen["3.1(3)"]  # nur im Entwurf eines anderen Curriculums

    assert a["pk"]["gesamt"] == 2 and a["pk"]["genutzt"] == 1
    assert [(k["nr"], k["anzahl"]) for k in a["pk"]["gruppen"][0]["kompetenzen"]] == [("2.1(1)", 2), ("2.1(2)", 0)]
    assert [k["nr"] for k in a["ausserhalb"]] == ["3.1(9)"]


async def test_abdeckung_eines_entwurfs_nur_fuer_lehrkraefte(db, welt):
    """Seit 0.52 (AZ) auch für Lehrkräfte außerhalb der Fachschaft; Schüler:innen nicht."""
    await curriculum_abdeckung(welt["neun"].id, db=db, user=_user(f"fremd-{TOKEN}", "teacher"))
    with pytest.raises(HTTPException) as e:
        await curriculum_abdeckung(welt["neun"].id, db=db, user=_user(f"s-{TOKEN}", "student"))
    assert e.value.status_code == 404
