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
                       ("check_curriculum_operations", {"operations": [{"op": "kapitel_anlegen", "titel": "X"}]}),
                       ("set_curriculum_frame", {"lehrwerk": "X"}),
                       ("undo_last_curriculum_change", {})):
        assert (await _ruf(name, db, welt, **args)) == {"error": NUR_ENTWUERFE}


async def test_fremde_und_ohne_bezug(db, welt):
    for name in ("get_curriculum_draft", "get_bp_competences", "check_curriculum_operations",
                 "apply_curriculum_operations"):
        antwort = await _ruf(name, db, welt, user=FREMDE, operations=[])
        assert "error" in antwort
    ctx = ToolContext(db=db, user=LEHRKRAFT, group_id=None, conversation_id=None)
    assert "curriculum_id erforderlich" in (await TOOL_REGISTRY["get_hour_frame"].handler({}, ctx))["error"]
    mit = await TOOL_REGISTRY["get_hour_frame"].handler({"curriculum_id": str(welt["cur"].id)}, ctx)
    assert mit["verplant"] == 4


# ── Prüflauf, Bilanz, Gelöschtes (Arbeitsanweisung 16.11.) ───────────────────


def _ohne_kennungen(gliederung):
    return [{**k, "id": None, "lernsequenzen": [{**ls, "id": None} for ls in k["lernsequenzen"]]}
            for k in gliederung]


def _stapel(w):
    return [
        {"op": "kapitel_anlegen", "titel": "Mechanik", "ref": "k2"},
        {"op": "lernsequenz_anlegen", "kapitel_id": "k2", "titel": "Kräfte", "std": 6, "ref": "l2"},
        {"op": "eintrag_anlegen", "lernsequenz_id": "l2", "ik": ["3.2.2(1)"]},
        {"op": "eintrag_loeschen", "lernsequenz_id": str(w["ls"].id), "eintrag": 1},
    ]


async def test_pruefen_schreibt_nichts_und_antwortet_wie_schreiben(db, welt):
    w = welt
    await _ruf("set_curriculum_frame", db, w, wochenstunden={"7": 2, "8": 2})
    staende = len(await _staende(db, w["cur"].id))
    vorher = await _ruf("get_curriculum_draft", db, w)

    probe = await _ruf("check_curriculum_operations", db, w, operations=_stapel(w))
    assert probe["ok"] and probe["geschrieben"] is False, probe
    assert probe["gliederung"][1]["id"] is None and probe["gliederung"][1]["lernsequenzen"][0]["id"] is None
    assert (probe["verplant"], probe["verplanbar"], probe["rest"]) == (10, 120, 110)
    assert probe["geloescht"] == {"kapitel": 0, "lernsequenzen": 0, "eintraege": 1}
    assert "neue_kennungen" not in probe
    assert len(await _staende(db, w["cur"].id)) == staende
    assert await _ruf("get_curriculum_draft", db, w) == vorher

    echt = await _ruf("apply_curriculum_operations", db, w, operations=_stapel(w))
    assert echt["ok"] and echt["geschrieben"] is True
    assert _ohne_kennungen(echt["gliederung"]) == _ohne_kennungen(probe["gliederung"])
    for f in ("verplant", "verplanbar", "rest", "geloescht"):
        assert echt[f] == probe[f], f


async def test_pruefen_weist_bandfremde_nummer_ab(db, welt):
    ops = [{"op": "eintrag_anlegen", "lernsequenz_id": str(welt["ls"].id), "ik": ["3.3.1(1)"]}]
    probe = await _ruf("check_curriculum_operations", db, welt, operations=ops)
    echt = await _ruf("apply_curriculum_operations", db, welt, operations=ops)
    assert probe["ok"] is False and probe["fehler"] == echt["fehler"]
    assert await _staende(db, welt["cur"].id) == []


async def test_geloescht_zaehlt_inhalt_geloeschter_kapitel(db, welt):
    w = welt
    probe = await _ruf("check_curriculum_operations", db, w, operations=[
        {"op": "kapitel_loeschen", "kapitel_id": str(w["kap"].id)}])
    assert probe["geloescht"] == {"kapitel": 1, "lernsequenzen": 1, "eintraege": 1}
    assert probe["gliederung"] == []
    # Verschoben ist nicht gelöscht; ein im Stapel angelegter und wieder gelöschter Eintrag zählt nicht.
    probe = await _ruf("check_curriculum_operations", db, w, operations=[
        {"op": "kapitel_anlegen", "titel": "Neu", "ref": "k"},
        {"op": "lernsequenz_aendern", "lernsequenz_id": str(w["ls"].id), "kapitel_id": "k"},
        {"op": "eintrag_aendern", "lernsequenz_id": str(w["ls"].id), "eintrag": 1, "konkretisierung": "X"},
        {"op": "eintrag_anlegen", "lernsequenz_id": str(w["ls"].id)},
        {"op": "eintrag_loeschen", "lernsequenz_id": str(w["ls"].id), "eintrag": 2},
        {"op": "kapitel_loeschen", "kapitel_id": str(w["kap"].id)},
    ])
    assert probe["geloescht"] == {"kapitel": 1, "lernsequenzen": 0, "eintraege": 0}, probe
    ohne = await _ruf("check_curriculum_operations", db, w, operations=[{"op": "kapitel_anlegen", "titel": "X"}])
    assert "geloescht" not in ohne


async def test_ohne_wochenstunden_kein_verplanbar(db, welt):
    for name in ("check_curriculum_operations", "apply_curriculum_operations"):
        a = await _ruf(name, db, welt, operations=[{"op": "kapitel_anlegen", "titel": "X"}])
        assert a["verplanbar"] is None and a["rest"] is None and a["fehlende_stufen"] == [7, 8], a
        assert a["hinweis"] == "Kapitel ohne Lernsequenz: X"


# ── Rückgängig: eigene sofort, fremde nur mit Bestätigung ────────────────────


async def test_eigenen_stapel_zuruecknehmen_ohne_bestaetigung(db, welt):
    await _ruf("apply_curriculum_operations", db, welt, operations=[{"op": "kapitel_anlegen", "titel": "X"}])
    zurueck = await _ruf("undo_last_curriculum_change", db, welt)
    assert zurueck["ok"] and zurueck["zurueckgenommen"]["gegenstand"] == ["inhalte"]
    assert zurueck["verbleibend"] == 0


async def _titel(db, welt):
    return (await _ruf("get_curriculum_draft", db, welt))["kapitel"][0]["titel"]


@pytest.mark.parametrize("grund, von", [("editor", MITGLIED), ("assistant", FREMDE.sub)])
async def test_fremde_aenderung_nur_mit_bestaetigung(db, welt, grund, von):
    from app.context.curriculum_verlauf import sichern

    await sichern(db, welt["cur"].id, grund=grund, von=von)
    welt["kap"].title = "Geändert"
    await db.flush()

    frage = await _ruf("undo_last_curriculum_change", db, welt)
    assert frage["ok"] is False and frage["bestaetigung_noetig"] is True
    letzte = frage["letzte_aenderung"]
    assert (letzte["von"], letzte["von_mir"], letzte["gegenstand"]) == (grund, von == MITGLIED, ["inhalte"])
    assert "zeit" in letzte and FREMDE.sub not in str(frage) and MITGLIED not in str(frage)
    assert await _titel(db, welt) == "Geändert"
    assert len(await _staende(db, welt["cur"].id)) == 1

    zurueck = await _ruf("undo_last_curriculum_change", db, welt, auch_fremde=True)
    assert zurueck["ok"] and zurueck["zurueckgenommen"]["von"] == grund
    assert await _titel(db, welt) == "Optik"


async def test_rueckgaengig_nach_rahmen_nennt_den_rahmen(db, welt):
    await _ruf("apply_curriculum_operations", db, welt, operations=[{"op": "kapitel_anlegen", "titel": "X"}])
    await _ruf("set_curriculum_frame", db, welt, lehrwerk="Impulse")
    zurueck = await _ruf("undo_last_curriculum_change", db, welt)
    assert zurueck["zurueckgenommen"]["gegenstand"] == ["rahmen"]
    entwurf = await _ruf("get_curriculum_draft", db, welt)
    assert entwurf["rahmen"] == {} and [k["titel"] for k in entwurf["kapitel"]] == ["Optik", "X"]


# ── Schritt 6: Bezug, Einstieg, Freischaltung ────────────────────────────────


async def test_freigeschaltet_nur_fuer_lehrkraefte_mit_der_faehigkeit():
    from types import SimpleNamespace

    from app.chat.tools import tools_for

    assistent = SimpleNamespace(tool_groups=["curriculum_planning"])
    namen = {t.name for t in tools_for(assistent, None, False, rollen=["teacher"])}
    assert {"apply_curriculum_operations", "finde_curriculum", "lege_curriculum_an"} <= namen
    schueler = {t.name for t in tools_for(assistent, None, False, rollen=["student"])}
    assert not {n for n, t in TOOL_REGISTRY.items() if "curriculum_planning" in t.groups} & schueler
    ohne = {t.name for t in tools_for(SimpleNamespace(tool_groups=[]), None, False, rollen=["teacher"])}
    assert "apply_curriculum_operations" not in ohne


async def test_bezug_anzeige_und_systemzeile(db, welt):
    from fastapi import HTTPException

    from app.context import curriculum_bezug as cb

    cur = await cb.curriculum_fuer_bezug(db, welt["cur"].id, LEHRKRAFT)
    assert cur.id == welt["cur"].id
    with pytest.raises(HTTPException):
        await cb.curriculum_fuer_bezug(db, welt["cur"].id, FREMDE)
    assert await cb.bezug_fuer_anzeige(db, welt["cur"].id, LEHRKRAFT) == {
        "curriculum_id": str(welt["cur"].id), "titel": "Physik 7/8", "entwurf": True}
    assert await cb.bezug_fuer_anzeige(db, welt["cur"].id, FREMDE) is None
    zeile = await cb.bezugszeile(db, welt["cur"].id, LEHRKRAFT)
    assert "„Physik 7/8“" in zeile and "Kl. 7/8" in zeile and "Entwurf" in zeile


async def _konversation(db):
    from app.db.models import Conversation

    k = Conversation(pseudonym=MITGLIED, model_used="test")
    db.add(k)
    await db.flush()
    return k


async def test_finden_und_waehlen_setzt_den_bezug(db, welt):
    k = await _konversation(db)
    ctx = ToolContext(db=db, user=LEHRKRAFT, group_id=None, conversation_id=k.id)
    gefunden = await TOOL_REGISTRY["finde_curriculum"].handler({"fach": "physik", "jahrgangsstufe": "8"}, ctx)
    assert [c["curriculum_id"] for c in gefunden["curricula"]] == [str(welt["cur"].id)]
    assert gefunden["faecher"][0]["fassungen"] == []  # kein Fachplan in dieser Welt

    gewaehlt = await TOOL_REGISTRY["waehle_curriculum"].handler({"curriculum_id": str(welt["cur"].id)}, ctx)
    assert gewaehlt["bezug_gesetzt"] and gewaehlt["kapitel"][0]["titel"] == "Optik"
    assert ctx.curriculum_node_id == welt["cur"].id
    await db.refresh(k)
    assert k.curriculum_node_id == welt["cur"].id

    assert (await TOOL_REGISTRY["finde_curriculum"].handler({}, ToolContext(
        db=db, user=FREMDE, group_id=None, conversation_id=None)))["curricula"] == []


async def test_veroeffentlichtes_waehlen_und_als_entwurf_kopieren(db, welt):
    for n in ("cur", "kap", "ls"):
        welt[n].status = "active"
    await db.flush()
    k = await _konversation(db)
    ctx = ToolContext(db=db, user=LEHRKRAFT, group_id=None, conversation_id=k.id)
    lesen = await TOOL_REGISTRY["waehle_curriculum"].handler({"curriculum_id": str(welt["cur"].id)}, ctx)
    assert lesen["status"] == "active" and "nur lesen" in lesen["hinweis"]

    kopie = await TOOL_REGISTRY["waehle_curriculum"].handler(
        {"curriculum_id": str(welt["cur"].id), "als_entwurf_kopieren": True}, ctx)
    assert kopie["status"] == "draft" and kopie["curriculum_id"] != str(welt["cur"].id)
    assert ctx.curriculum_node_id == uuid.UUID(kopie["curriculum_id"])
    # Ein zweites Mal: derselbe offene Entwurf, keine zweite Kopie.
    wieder = await TOOL_REGISTRY["waehle_curriculum"].handler(
        {"curriculum_id": str(welt["cur"].id), "als_entwurf_kopieren": True}, ctx)
    assert wieder["curriculum_id"] == kopie["curriculum_id"]


async def test_anlegen_nur_mit_fachplan_und_ohne_doppel(db, welt):
    ctx = ToolContext(db=db, user=LEHRKRAFT, group_id=None, conversation_id=None)
    ohne = await TOOL_REGISTRY["lege_curriculum_an"].handler({"fach": "Physik", "jahrgangsstufe": "9/10"}, ctx)
    assert "error" in ohne and "Fassung" in ohne["error"]

    db.add(ContextNode(category="knowledge", content_type="fachplan", title="BP Physik", status="active",
                       read_scope="global", write_scope="global", owner_pseudonym="system",
                       subject_id=welt["fach"].id, bp_version=BP,
                       metadata_={"bp_id": "BP2016BW_ALLG_GYM_PH.V3"}))
    await db.flush()
    neu = await TOOL_REGISTRY["lege_curriculum_an"].handler({"fach": "Physik", "jahrgangsstufe": "9/10"}, ctx)
    assert neu["bezug_gesetzt"] and neu["status"] == "draft" and neu["kapitel"] == []
    knoten = await db.get(ContextNode, uuid.UUID(neu["curriculum_id"]))
    assert (knoten.min_grade, knoten.max_grade, knoten.metadata_["schulart"]) == (9, 10, "Gymnasium")
    assert knoten.owner_pseudonym == MITGLIED and knoten.metadata_["bp_version"] == BP

    doppel = await TOOL_REGISTRY["lege_curriculum_an"].handler({"fach": "Physik", "jahrgangsstufe": "7/8"}, ctx)
    assert "schon ein Curriculum" in doppel["error"] and doppel["vorhanden"][0]["curriculum_id"] == str(welt["cur"].id)
    fremd = await TOOL_REGISTRY["lege_curriculum_an"].handler(
        {"fach": "Physik", "jahrgangsstufe": "5"}, ToolContext(db=db, user=FREMDE, group_id=None, conversation_id=None))
    assert "error" in fremd
