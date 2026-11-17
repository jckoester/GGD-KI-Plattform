"""Curricula nach Fassung und Band, Abdeckung über das Band (0.46, Päckchen AP Teil B, Schritt 8).

Bänder kommen aus der Bandüberschrift im Pfad der IK. Parallele Bänder der Oberstufe ordnen ein
Curriculum nur über `metadata.band` zu; ohne Wahl misst seine Abdeckung gegen alle (mit Hinweis).
Die Abdeckung über das Band fasst die zugeordneten Curricula zusammen; mit Entwürfen ersetzt ein
Entwurf mit `kopie_von` das Original.
"""
import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.auth.jwt import JwtPayload
from app.context.router import band_abdeckung_route, curricula_nach_baendern, curriculum_abdeckung
from app.db.models import ContextEdge, ContextNode, Group, GroupMembership, Subject

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]
MITGLIED = f"mitglied-band-{TOKEN}"
V3, V4, ALT = "2016.V3", "2016.V4", "2016"
LF, BASIS, SCHWERPUNKT = ("Klassen 12/13 (Leistungsfach)", "Klassen 12/13 (Basisfach)",
                          "Klassen 12/13 (Basisfach mit Schwerpunkt Sterne)")


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
    fach = Subject(slug=f"band-{TOKEN}", name=f"Band {TOKEN}", fach_code=f"B{TOKEN[:4]}".upper())
    db.add(fach)
    await db.flush()
    fs = Group(name=f"FS {TOKEN}", slug=f"fs-band-{TOKEN}", type="subject_department", subject_id=fach.id)
    db.add(fs)
    await db.flush()
    db.add(GroupMembership(group_id=fs.id, pseudonym=MITGLIED, role_in_group="teacher"))

    async def ik(nr, ueberschrift, lo, hi, bp=V3, status="active"):
        return await _knoten(db, "ik_kompetenz", f"{nr} Text {nr}", subject_id=fach.id, bp_version=bp,
                             status=status, min_grade=lo, max_grade=hi,
                             metadata_={"kompetenz_nr": nr, "breadcrumb": ["BP", ueberschrift, "Bereich"]})

    k = {
        "a1": await ik("3.1(1)", "3.1 Klassen 5/6", 5, 6),
        "a2": await ik("3.1(2)", "3.1 Klassen 5/6", 5, 6),
        "a3": await ik("3.1(3)", "3.1 Klassen 5/6", 5, 6),
        "l1": await ik("3.4(1)", f"3.4 {LF}", 12, 13),
        "l2": await ik("3.4(2)", f"3.4 {LF}", 12, 13),
        "b1": await ik("3.5(1)", f"3.5 {BASIS}", 12, 13),
        # Ohne Stufen wie Physik V2 — die Stufen stehen in der Überschrift.
        "x1": await ik("3.6(1)", f"3.6 {SCHWERPUNKT}", None, None),
        "v4": await ik("3.1(1)", "3.1 Klassen 5/6", 5, 6, bp=V4, status="upcoming"),
        "alt": await ik("3.1(1)", "3.1 Klassen 5/6", 5, 6, bp=ALT, status="archived"),
    }

    async def curriculum(titel, lo, hi, status="active", bp=V3, links=(), **meta):
        gemeinsam = dict(subject_id=fach.id, min_grade=lo, max_grade=hi, status=status,
                         write_scope="subject", write_scope_group_id=fs.id)
        cur = await _knoten(db, "curriculum", titel, metadata_={"bp_version": bp, **meta}, **gemeinsam)
        kap = await _knoten(db, "kapitel", f"{titel} K", **gemeinsam)
        db.add(ContextEdge(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"))
        eintrag = {"ik": [{"node_id": str(k[n].id), "partiell": teil} for n, teil in links], "pk": []}
        ls = await _knoten(db, "lernsequenz", f"{titel} LS", metadata_={"eintraege": [eintrag]}, **gemeinsam)
        db.add(ContextEdge(from_node_id=ls.id, to_node_id=kap.id, relation="part_of"))
        await db.flush()
        return cur

    c = {}
    c["k5"] = await curriculum(f"K5 {TOKEN}", 5, 5, links=[("a1", False), ("a2", True)])
    c["k6"] = await curriculum(f"K6 {TOKEN}", 6, 6, links=[("a2", True)])
    c["k6e"] = await curriculum(f"K6 neu {TOKEN}", 6, 6, status="draft", kopie_von=str(c["k6"].id),
                                links=[("a2", False), ("a3", False)])
    c["os"] = await curriculum(f"OS {TOKEN}", 12, 13)
    c["lf"] = await curriculum(f"LF {TOKEN}", 12, 13, band=LF, links=[("l1", False)])
    c["alt"] = await curriculum(f"Alt {TOKEN}", 5, 5, bp=ALT)
    return {"fach": fach, "ik": k, "cur": c}


async def test_uebersicht_nach_fassung_und_band(db, welt):
    u = await curricula_nach_baendern(welt["fach"].id, db=db, user=_user(MITGLIED, "teacher"))
    assert [(f["bp_version"], f["art"]) for f in u["fassungen"]] == [
        (V3, "geltend"), (V4, "kommend"), (ALT, "aelter")]
    v3 = u["fassungen"][0]
    assert [(b["schluessel"], b["min_grade"], b["max_grade"]) for b in v3["baender"]] == [
        ("Klassen 5/6", 5, 6), (LF, 12, 13), (BASIS, 12, 13), (SCHWERPUNKT, 12, 13)]
    je_band = {b["schluessel"]: [c["title"] for c in b["curricula"]] for b in v3["baender"]}
    assert je_band["Klassen 5/6"] == [f"K5 {TOKEN}", f"K6 {TOKEN}", f"K6 neu {TOKEN}"]
    assert je_band[LF] == [f"LF {TOKEN}"] and je_band[BASIS] == []
    [offen] = v3["nicht_zugeordnet"]
    assert offen["title"] == f"OS {TOKEN}" and offen["baender"] == [LF, BASIS, SCHWERPUNKT]
    entwurf = next(c for c in v3["baender"][0]["curricula"] if c["status"] == "draft")
    assert entwurf["ersetzt"] == {"id": str(welt["cur"]["k6"].id), "title": f"K6 {TOKEN}"}
    assert [c["title"] for b in u["fassungen"][2]["baender"] for c in b["curricula"]] == [f"Alt {TOKEN}"]


async def test_entwuerfe_nur_fuer_die_fachschaft(db, welt):
    u = await curricula_nach_baendern(welt["fach"].id, db=db, user=_user(f"fremd-{TOKEN}", "teacher"))
    titel = [c["title"] for f in u["fassungen"] for b in f["baender"] for c in b["curricula"]]
    assert f"K6 neu {TOKEN}" not in titel and f"K6 {TOKEN}" in titel


async def test_abdeckung_misst_nur_das_band(db, welt):
    """Behebt 0.45: Ein Oberstufen-Curriculum maß gegen Basis- und Leistungsfach zusammen, und IK
    ohne Stufen zählten in jedem Band mit."""
    mitglied = _user(MITGLIED, "teacher")
    lf = await curriculum_abdeckung(welt["cur"]["lf"].id, db=db, user=mitglied)
    assert lf["ik"]["gesamt"] == 2 and lf["band"]["schluessel"] == LF and lf["hinweis"] is None
    k5 = await curriculum_abdeckung(welt["cur"]["k5"].id, db=db, user=mitglied)
    assert k5["ik"]["gesamt"] == 3 and k5["baender_zur_wahl"] == []


async def test_abdeckung_ohne_band_misst_alle_parallelen(db, welt):
    a = await curriculum_abdeckung(welt["cur"]["os"].id, db=db, user=_user(MITGLIED, "teacher"))
    assert a["band"] is None and a["ik"]["gesamt"] == 4
    assert [b["schluessel"] for b in a["baender_zur_wahl"]] == [LF, BASIS, SCHWERPUNKT]
    assert "mehrere Bänder" in a["hinweis"]


async def test_bandabdeckung_ueber_die_curricula(db, welt):
    a = await band_abdeckung_route(welt["fach"].id, bp_version=V3, band="Klassen 5/6", entwuerfe=False,
                                   db=db, user=_user(MITGLIED, "teacher"))
    assert [c["title"] for c in a["curricula"]] == [f"K5 {TOKEN}", f"K6 {TOKEN}"]
    zeilen = {k["nr"]: k for g in a["ik"]["gruppen"] for k in g["kompetenzen"]}
    assert {nr: z["zustand"] for nr, z in zeilen.items()} == {
        "3.1(1)": "verknuepft", "3.1(2)": "partiell", "3.1(3)": "fehlt"}
    assert sorted(x["title"] for x in zeilen["3.1(2)"]["curricula"]) == [f"K5 {TOKEN}", f"K6 {TOKEN}"]
    assert all(x["partiell"] for x in zeilen["3.1(2)"]["curricula"])


async def test_bandabdeckung_mit_entwuerfen_ersetzt_das_original(db, welt):
    a = await band_abdeckung_route(welt["fach"].id, bp_version=V3, band="Klassen 5/6", entwuerfe=True,
                                   db=db, user=_user(MITGLIED, "teacher"))
    assert [c["title"] for c in a["curricula"]] == [f"K5 {TOKEN}", f"K6 neu {TOKEN}"]
    assert {k: a["ik"][k] for k in ("verknuepft", "partiell", "fehlt")} == {
        "verknuepft": 3, "partiell": 0, "fehlt": 0}


async def test_bandabdeckung_entwuerfe_nicht_fuer_fremde(db, welt):
    a = await band_abdeckung_route(welt["fach"].id, bp_version=V3, band="Klassen 5/6", entwuerfe=True,
                                   db=db, user=_user(f"fremd-{TOKEN}", "teacher"))
    assert [c["title"] for c in a["curricula"]] == [f"K5 {TOKEN}", f"K6 {TOKEN}"]


async def test_bandabdeckung_nennt_nicht_zugeordnete(db, welt):
    a = await band_abdeckung_route(welt["fach"].id, bp_version=V3, band=BASIS, entwuerfe=False,
                                   db=db, user=_user(MITGLIED, "teacher"))
    assert a["curricula"] == [] and [c["title"] for c in a["nicht_zugeordnet"]] == [f"OS {TOKEN}"]
    assert a["ik"]["gesamt"] == 1 and a["ik"]["fehlt"] == 1


async def test_unbekanntes_band(db, welt):
    with pytest.raises(HTTPException) as e:
        await band_abdeckung_route(welt["fach"].id, bp_version=V3, band="Klassen 7/8", entwuerfe=False,
                                   db=db, user=_user(MITGLIED, "teacher"))
    assert e.value.status_code == 404


async def test_anlegen_fragt_bei_parallelen_baendern(db, welt):
    import app.context.curriculum_tools  # noqa: F401 — registriert die Funktionen
    from app.chat.tools import TOOL_REGISTRY, ToolContext

    db.add(ContextNode(category="knowledge", content_type="fachplan", title="BP", status="active",
                       read_scope="global", write_scope="global", owner_pseudonym="system",
                       subject_id=welt["fach"].id, bp_version=V3, metadata_={"bp_id": "BP2016BW_ALLG_GYM_X.V3"}))
    await db.flush()
    ctx = ToolContext(db=db, user=_user(MITGLIED, "teacher"), group_id=None, conversation_id=None)
    anlegen = TOOL_REGISTRY["lege_curriculum_an"].handler
    args = {"fach": welt["fach"].name, "jahrgangsstufe": "12/13", "bp_version": V3}

    ohne = await anlegen(args, ctx)
    assert "mehrere Bänder" in ohne["error"] and ohne["baender"] == [LF, BASIS, SCHWERPUNKT]
    # Ein Curriculum ohne Band (OS) kann das Basisfach sein — kein zweites daneben.
    doppel = await anlegen({**args, "band": BASIS}, ctx)
    assert [c["titel"] for c in doppel["vorhanden"]] == [f"OS {TOKEN}"]

    welt["cur"]["os"].status = "deleted"
    await db.flush()
    neu = await anlegen({**args, "band": BASIS}, ctx)
    knoten = await db.get(ContextNode, uuid.UUID(neu["curriculum_id"]))
    assert knoten.metadata_["band"] == BASIS


async def test_band_waehlen_im_editor(db, welt):
    from app.context.router import curriculum_band, update_node
    from app.context.schemas import ContextNodeUpdate

    mitglied = _user(MITGLIED, "teacher")
    os_ = welt["cur"]["os"]
    wahl = await curriculum_band(os_.id, db=db, user=mitglied)
    assert wahl["band"] is None and [b["schluessel"] for b in wahl["baender_zur_wahl"]] == [LF, BASIS, SCHWERPUNKT]
    assert (await curriculum_band(welt["cur"]["k5"].id, db=db, user=mitglied))["baender_zur_wahl"] == []

    meta = {**os_.metadata_}
    with pytest.raises(HTTPException) as e:
        await update_node(os_.id, ContextNodeUpdate(metadata={**meta, "band": "Klassen 5/6"}), db=db, user=mitglied)
    assert e.value.status_code == 422 and "Möglich" in e.value.detail
    await update_node(os_.id, ContextNodeUpdate(metadata={**meta, "band": BASIS}), db=db, user=mitglied)
    assert (await curriculum_band(os_.id, db=db, user=mitglied))["band"]["schluessel"] == BASIS


async def test_bandabdeckung_als_pdf(db, welt):
    antwort = await band_abdeckung_route(welt["fach"].id, bp_version=V3, band="Klassen 5/6", entwuerfe=False,
                                         format="pdf", nur_luecken=True, db=db, user=_user(MITGLIED, "teacher"))
    assert antwort.media_type == "application/pdf" and antwort.body.startswith(b"%PDF")
    assert "abdeckung_" in antwort.headers["content-disposition"]
