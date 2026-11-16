"""Funktionen des Curriculum-Assistenten (0.46, Päckchen AP Teil B, Schritt 5).

Lesen (Entwurf, Kompetenzen des Bands, Abdeckung, Stundenrahmen) und Schreiben (Stapel ganz oder
gar nicht, Rahmen, Rückgängig) — über die Handler, wie der Chat sie aufruft.
"""
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.auth.jwt import JwtPayload
from app.chat.tools import TOOL_REGISTRY, ToolContext
import app.context.curriculum_tools  # noqa: F401 — registriert
from app.context.curriculum_assistent import NUR_ENTWUERFE
from app.db.models import ContextEdge, ContextNode, CurriculumSnapshot, Group, GroupMembership, Subject

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]
MITGLIED = f"cm-{TOKEN}"
BP = "2016.V3"


def _user(sub, *rollen):
    return JwtPayload(sub=sub, roles=list(rollen), role=rollen[0], grade=None,
                      exp=9999999999, iat=0, jti=str(uuid.uuid4()))


LEHRKRAFT = _user(MITGLIED, "teacher")
FREMDE = _user(f"fremd-{TOKEN}", "teacher")


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


def _komp(fach, typ, nr, gruppe, titel, **kw):
    return ContextNode(category="knowledge", content_type=typ, title=f"{nr} {titel}", status="active",
                       read_scope="global", write_scope="global", owner_pseudonym="system",
                       subject_id=fach.id, bp_version=BP,
                       metadata_={"kompetenz_nr": nr, "thematische_gruppe": gruppe}, **kw)


@pytest_asyncio.fixture
async def welt(db):
    fach = Subject(slug=f"ca-{TOKEN}", name=f"Physik {TOKEN}", fach_code=f"P{TOKEN[:4]}".upper())
    db.add(fach)
    await db.flush()
    fs = Group(name=f"FS {TOKEN}", slug=f"fs-ca-{TOKEN}", type="subject_department", subject_id=fach.id)
    db.add(fs)
    await db.flush()
    db.add(GroupMembership(group_id=fs.id, pseudonym=MITGLIED, role_in_group="teacher"))
    k = {
        "ik1": _komp(fach, "ik_kompetenz", "3.2.1(1)", "Optik", "Licht ausbreiten", min_grade=7, max_grade=8),
        "ik2": _komp(fach, "ik_kompetenz", "3.2.1(2)", "Optik", "Schatten erklären", min_grade=7, max_grade=8),
        "ik3": _komp(fach, "ik_kompetenz", "3.2.2(1)", "Mechanik", "Kräfte messen", min_grade=7, max_grade=8),
        "ik_fremd": _komp(fach, "ik_kompetenz", "3.3.1(1)", "Elektrik", "Spannung", min_grade=9, max_grade=10),
        "pk1": _komp(fach, "pk_kompetenz", "2.1(1)", "Erkenntnisgewinnung", "beobachten"),
    }
    db.add_all(k.values())

    def teil(typ, titel, **kw):
        return ContextNode(category="knowledge", content_type=typ, title=titel, status="draft",
                           read_scope="school", write_scope="subject", write_scope_group_id=fs.id,
                           subject_id=fach.id, owner_pseudonym=MITGLIED, **kw)

    cur = teil("curriculum", "Physik 7/8", min_grade=7, max_grade=8,
               metadata_={"jahrgangsstufe": "7/8", "bp_version": BP, "fach": "Physik", "schulart": "Gym"})
    kap = teil("kapitel", "Optik", metadata_={"reihenfolge": 1, "std": 4, "einleitung": ""})
    ls = teil("lernsequenz", "Licht", metadata_={"reihenfolge": 1, "std": 4, "eintraege": [
        {"ik": [], "pk": [], "konkretisierung": "Lichtquellen"}]})
    db.add_all([cur, kap, ls])
    await db.flush()
    db.add_all([ContextEdge(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"),
                ContextEdge(from_node_id=ls.id, to_node_id=kap.id, relation="part_of")])
    await db.flush()
    return {"fach": fach, "fs": fs, "cur": cur, "kap": kap, "ls": ls, **k}


async def _ruf(name, db, welt, user=LEHRKRAFT, **args):
    ctx = ToolContext(db=db, user=user, group_id=None, conversation_id=None,
                      curriculum_node_id=welt["cur"].id)
    return await TOOL_REGISTRY[name].handler(args, ctx)


async def _staende(db, cid):
    return (await db.execute(sa.select(CurriculumSnapshot.reason).where(
        CurriculumSnapshot.curriculum_id == cid))).scalars().all()


async def test_kompetenzen_uebersicht_und_bereich(db, welt):
    ueber = await _ruf("get_bp_competences", db, welt)
    assert ueber["ik"]["gesamt"] == 3  # 3.3.1(1) gehört zu 9/10
    assert {b["bereich"]: (b["anzahl"], b["nummern"]) for b in ueber["ik"]["bereiche"]} == {
        "Optik": (2, "3.2.1(1) – 3.2.1(2)"), "Mechanik": (1, "3.2.2(1)")}
    assert "text" not in str(ueber["ik"])

    optik = await _ruf("get_bp_competences", db, welt, bereich="opt")
    assert optik["bereiche"][0]["kompetenzen"] == [
        {"nr": "3.2.1(1)", "text": "Licht ausbreiten"}, {"nr": "3.2.1(2)", "text": "Schatten erklären"}]
    praefix = await _ruf("get_bp_competences", db, welt, bereich="3.2.2")
    assert [k["nr"] for b in praefix["bereiche"] for k in b["kompetenzen"]] == ["3.2.2(1)"]
    pk = await _ruf("get_bp_competences", db, welt, bereich="alle", typ="pk")
    assert pk["bereiche"][0]["kompetenzen"][0]["nr"] == "2.1(1)"


async def test_stapel_legt_an_und_verknuepft(db, welt):
    w = welt
    antwort = await _ruf("apply_curriculum_operations", db, w, operations=[
        {"op": "kapitel_anlegen", "titel": "Mechanik", "ref": "k2"},
        {"op": "lernsequenz_anlegen", "kapitel_id": "k2", "titel": "Kräfte", "std": 6, "ref": "l2"},
        {"op": "eintrag_anlegen", "lernsequenz_id": "l2", "ik": ["3.2.2 (1)"], "ik_teilweise": ["3.2.1(2)"],
         "pk": ["2.1(1)"], "konkretisierung": "Federkraftmesser", "begriffe": ["Kraft"], "fachmethoden": ["Messen"]},
        {"op": "eintrag_aendern", "lernsequenz_id": str(w["ls"].id), "eintrag": 1, "ik": ["3.2.1(1)"]},
    ])
    assert antwort["ok"], antwort
    assert antwort["verplant"] == 10
    assert [k["titel"] for k in antwort["gliederung"]] == ["Optik", "Mechanik"]
    assert await _staende(db, w["cur"].id) == ["assistant"]

    entwurf = await _ruf("get_curriculum_draft", db, w)
    mechanik = entwurf["kapitel"][1]
    assert mechanik["std"] == 6 and mechanik["id"] == antwort["neue_kennungen"]["k2"]
    (e,) = mechanik["lernsequenzen"][0]["eintraege"]
    assert e["ik"] == ["3.2.2(1)"] and e["ik_teilweise"] == ["3.2.1(2)"] and e["pk"] == ["2.1(1)"]
    assert e["begriffe"] == [{"name": "Kraft", "zustand": "fehlt"}] and e["fachmethoden"] == ["Messen"]
    assert entwurf["kapitel"][0]["lernsequenzen"][0]["eintraege"][0]["konkretisierung"] == "Lichtquellen"

    neue_ls = uuid.UUID(antwort["neue_kennungen"]["l2"])
    kanten = {(r, z, (m or {}).get("partiell")) for r, z, m in (await db.execute(
        sa.select(ContextEdge.relation, ContextEdge.to_node_id, ContextEdge.metadata_)
        .where(ContextEdge.from_node_id == neue_ls))).all()}
    assert kanten == {("part_of", uuid.UUID(mechanik["id"]), None), ("references", w["ik3"].id, "false"),
                      ("references", w["ik2"].id, "true"), ("develops", w["pk1"].id, None)}
    neu = await db.get(ContextNode, neue_ls)
    assert neu.status == "draft" and neu.owner_pseudonym == MITGLIED

    abdeckung = await _ruf("get_curriculum_coverage", db, w)
    assert (abdeckung["ik"]["verknuepft"], abdeckung["ik"]["teilweise"], abdeckung["ik"]["fehlt"]) == (2, 1, 0)
    assert abdeckung["pk"]["ungenutzt"] == []


async def test_unbekannte_nummer_schreibt_nichts(db, welt):
    antwort = await _ruf("apply_curriculum_operations", db, welt, operations=[
        {"op": "kapitel_anlegen", "titel": "Elektrik"},
        {"op": "eintrag_anlegen", "lernsequenz_id": str(welt["ls"].id), "ik": ["3.3.1(1)"]},
    ])
    assert antwort["ok"] is False
    assert "Operation 2" in antwort["fehler"][0] and "3.3.1(1)" in antwort["fehler"][0]
    assert await _staende(db, welt["cur"].id) == []
    assert len((await _ruf("get_curriculum_draft", db, welt))["kapitel"]) == 1


async def test_verschieben_ordnen_loeschen(db, welt):
    w = welt
    a = await _ruf("apply_curriculum_operations", db, w, operations=[
        {"op": "kapitel_anlegen", "titel": "Einstieg", "position": 1, "ref": "k0"},
        {"op": "lernsequenz_aendern", "lernsequenz_id": str(w["ls"].id), "kapitel_id": "k0", "std": 3},
        {"op": "eintrag_loeschen", "lernsequenz_id": str(w["ls"].id), "eintrag": 1},
        {"op": "kapitel_loeschen", "kapitel_id": str(w["kap"].id)},
    ])
    assert a["ok"], a
    entwurf = await _ruf("get_curriculum_draft", db, w)
    assert [k["titel"] for k in entwurf["kapitel"]] == ["Einstieg"]
    (ls,) = entwurf["kapitel"][0]["lernsequenzen"]
    assert ls["id"] == str(w["ls"].id) and ls["std"] == 3 and ls["eintraege"] == []
    assert await db.get(ContextNode, w["kap"].id, populate_existing=True) is None

    # Rückgängig: derselbe Verlauf wie im Editor.
    zurueck = await _ruf("undo_last_curriculum_change", db, w)
    assert zurueck["ok"] and zurueck["zurueckgenommen"]["von"] == "assistant"
    entwurf = await _ruf("get_curriculum_draft", db, w)
    assert [k["titel"] for k in entwurf["kapitel"]] == ["Optik"]
    assert entwurf["kapitel"][0]["lernsequenzen"][0]["std"] == 4


async def test_rahmen_und_stundenbilanz(db, welt):
    leer = await _ruf("get_hour_frame", db, welt)
    assert leer["verplanbar"] is None and leer["fehlende_stufen"] == [7, 8] and leer["verplant"] == 4

    a = await _ruf("set_curriculum_frame", db, welt, wochenstunden={"7": 2}, lehrwerk="Impulse Physik")
    assert a["ok"] and a["verplanbar"] is None
    a = await _ruf("set_curriculum_frame", db, welt, wochenstunden={"8": "1,5"})
    assert a["rahmen"] == {"wochenstunden": {"7": 2, "8": 1.5}, "lehrwerk": "Impulse Physik"}
    assert a["verplanbar"] == 105

    bilanz = await _ruf("get_hour_frame", db, welt)
    assert (bilanz["verplanbar"], bilanz["verplant"], bilanz["rest"]) == (105, 4, 101)
    assert "fehlende_stufen" not in bilanz
    assert (await _ruf("get_curriculum_draft", db, welt))["rahmen"]["lehrwerk"] == "Impulse Physik"
    assert await _staende(db, welt["cur"].id) == ["assistant", "assistant"]

    falsch = await _ruf("set_curriculum_frame", db, welt, wochenstunden={"7": "viel"})
    assert falsch["ok"] is False


async def test_veroeffentlicht_nur_lesen(db, welt):
    for n in ("cur", "kap", "ls"):
        welt[n].status = "active"
    await db.flush()
    assert "kapitel" in await _ruf("get_curriculum_draft", db, welt)
    for name, args in (("apply_curriculum_operations", {"operations": [{"op": "kapitel_anlegen", "titel": "X"}]}),
                       ("set_curriculum_frame", {"lehrwerk": "X"}),
                       ("undo_last_curriculum_change", {})):
        assert (await _ruf(name, db, welt, **args)) == {"error": NUR_ENTWUERFE}


async def test_fremde_und_ohne_bezug(db, welt):
    for name in ("get_curriculum_draft", "get_bp_competences", "apply_curriculum_operations"):
        antwort = await _ruf(name, db, welt, user=FREMDE, operations=[])
        assert "error" in antwort
    ctx = ToolContext(db=db, user=LEHRKRAFT, group_id=None, conversation_id=None)
    assert "curriculum_id erforderlich" in (await TOOL_REGISTRY["get_hour_frame"].handler({}, ctx))["error"]
    mit = await TOOL_REGISTRY["get_hour_frame"].handler({"curriculum_id": str(welt["cur"].id)}, ctx)
    assert mit["verplant"] == 4
