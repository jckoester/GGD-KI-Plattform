"""Die Werkzeuge des MCP-Servers (0.54, Päckchen AW Schritt 4) — über die ASGI-App mit echtem
Token, in der Test-Transaktion. Erfordert TEST_DATABASE_URL."""
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.auth import tokens
from app.db.models import ContextEdge, ContextNode, PseudonymAudit, Subject
from app.mcp.auth import SCOPE
from app.mcp.server import einhaengen, lebenszyklus

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]
LEHRKRAFT = f"mcpw-{TOKEN}"   # liest, gehört keiner Fachschaft an
AUTORIN = f"mcpa-{TOKEN}"     # Eigentümerin der Curricula — darf in keiner Antwort stehen
BP = "2016.V3"
HOST = "ki.schule.test"
KOPF = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
WERKZEUGE = {"leitlinien", "leitperspektiven", "leitlinie_uebersicht", "curricula_finden",
             "curriculum_lesen", "curriculum_abdeckung", "bildungsplan_kompetenzen",
             "curriculum_yaml", "curriculum_yaml_pruefen"}


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


def _knoten(typ, titel, status="active", **kw):
    kw.setdefault("read_scope", "school")
    kw.setdefault("write_scope", "private" if kw["read_scope"] == "private" else "school")
    return ContextNode(category="knowledge", content_type=typ, title=titel, status=status,
                       **{"owner_pseudonym": AUTORIN, **kw})


@pytest_asyncio.fixture
async def welt(db):
    fach = Subject(slug=f"mw-{TOKEN}", name=f"Physik {TOKEN}", fach_code=f"P{TOKEN[:4]}".upper())
    db.add_all([fach, PseudonymAudit(pseudonym=LEHRKRAFT, role="teacher", roles=["teacher"], grade=None)])
    await db.flush()
    komp = [_knoten("ik_kompetenz", f"3.2.1({i}) Licht {i}", read_scope="global", subject_id=fach.id,
                    bp_version=BP, min_grade=7, max_grade=8, owner_pseudonym="system",
                    metadata_={"kompetenz_nr": f"3.2.1({i})", "thematische_gruppe": "Optik"}) for i in (1, 2)]
    ll = _knoten("leitbild", f"Testleitlinie {TOKEN}", metadata_={"kuerzel": f"T{TOKEN[:4]}".upper()})
    asp = _knoten("leitbild_aspekt", f"Aspekt {TOKEN}",
                  metadata_={"kuerzel": f"T{TOKEN[:4]}1".upper(), "leitlinie": f"T{TOKEN[:4]}".upper()})
    db.add_all([*komp, ll, asp])
    await db.flush()

    async def curriculum(titel, status, read_scope="school"):
        cur = _knoten("curriculum", titel, status, read_scope=read_scope, subject_id=fach.id,
                      min_grade=7, max_grade=8,
                      metadata_={"jahrgangsstufe": "7/8", "bp_version": BP, "fach": fach.name})
        kap = _knoten("kapitel", f"Optik {titel}", status, read_scope=read_scope, subject_id=fach.id,
                      metadata_={"reihenfolge": 1})
        ls = _knoten("lernsequenz", f"Licht {titel}", status, read_scope=read_scope, subject_id=fach.id,
                     metadata_={"reihenfolge": 1, "std": 4, "eintraege": [
                         {"ik": [{"node_id": str(komp[0].id), "nr": "3.2.1(1)"}], "pk": [], "konkretisierung": "Lichtquellen",
                          "hinweise": f"@[Aspekt](lba:{asp.id})"}]})
        db.add_all([cur, kap, ls])
        await db.flush()
        db.add_all([ContextEdge(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"),
                    ContextEdge(from_node_id=ls.id, to_node_id=kap.id, relation="part_of"),
                    ContextEdge(from_node_id=ls.id, to_node_id=asp.id, relation="references")])
        await db.flush()
        return cur

    return {"fach": fach, "ll": ll,
            "aktiv": await curriculum(f"Physik 7/8 {TOKEN}", "active"),
            "entwurf": await curriculum(f"Physik 7/8 neu {TOKEN}", "draft"),
            "privat": await curriculum(f"Privat {TOKEN}", "active", read_scope="private")}


@asynccontextmanager
async def _verbunden(db):
    """Werkzeuge und Token-Prüfung in der Test-Transaktion. Kein Fixture: Die Task-Gruppe des
    Session-Managers muss im selben Task enden, in dem sie begann."""
    @asynccontextmanager
    async def dieselbe():
        yield db

    app = FastAPI()
    server = einhaengen(app, aktiv=True, oeffentliche_url=f"https://{HOST}/api/mcp", sitzung=dieselbe)
    klartext, _ = await tokens.erzeuge(db, pseudonym=LEHRKRAFT, name="Claude", scopes=[SCOPE],
                                       gueltig_bis=datetime.now(timezone.utc) + timedelta(days=1),
                                       rollen=["teacher"])
    kopf = {**KOPF, "authorization": f"Bearer {klartext}"}
    async with lebenszyklus(server):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=f"https://{HOST}") as c:
            r = await c.post("/mcp", headers=kopf, json={"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
            kopf["mcp-protocol-version"] = r.json()["result"]["protocolVersion"]

            async def rpc(methode, **params):
                r = await c.post("/mcp", headers=kopf, json={"jsonrpc": "2.0", "id": 1, "method": methode,
                                                            "params": params})
                assert r.status_code == 200, r.text
                return r.json()["result"]

            yield rpc


async def _ruf(rpc, name, **argumente):
    """(Daten, Fehler?) eines Werkzeugaufrufs — und der rohe Text für die Personenprüfung."""
    erg = await rpc("tools/call", name=name, arguments=argumente)
    text = erg["content"][0]["text"]
    assert AUTORIN not in text and LEHRKRAFT not in text, f"Pseudonym in der Antwort von {name}"
    return (text if erg.get("isError") else json.loads(text)), bool(erg.get("isError"))


async def test_neun_werkzeuge_alle_lesend(db, welt):
    async with _verbunden(db) as rpc:
        liste = (await rpc("tools/list"))["tools"]
    assert {w["name"] for w in liste} == WERKZEUGE
    for w in liste:
        assert w["annotations"]["readOnlyHint"] is True, w["name"]
        assert w["annotations"]["destructiveHint"] is False, w["name"]


async def test_curricula_finden_wie_im_browser(db, welt):
    async with _verbunden(db) as rpc:
        aus, fehler = await _ruf(rpc, "curricula_finden", fach=f"physik {TOKEN}")
        assert not fehler
        titel = {c["titel"]: c["status"] for c in aus["curricula"]}
        # Entwurf sichtbar (seit 0.52 für alle Lehrkräfte), das private Curriculum einer anderen nicht
        assert titel == {f"Physik 7/8 {TOKEN}": "veröffentlicht", f"Physik 7/8 neu {TOKEN}": "entwurf"}
        aus, _ = await _ruf(rpc, "curricula_finden", fach=f"physik {TOKEN}", jahrgangsstufe="10")
        assert aus["curricula"] == []


async def test_curriculum_lesen_und_abdeckung(db, welt):
    async with _verbunden(db) as rpc:
        aus, fehler = await _ruf(rpc, "curriculum_lesen", curriculum_id=str(welt["entwurf"].id))
        assert not fehler
        assert aus["status"] == "entwurf"
        eintrag = aus["kapitel"][0]["lernsequenzen"][0]["eintraege"][0]
        assert eintrag["ik"] == ["3.2.1(1)"]
        assert eintrag["leitlinien"] == [f"T{TOKEN[:4]}1".upper()]

        aus, fehler = await _ruf(rpc, "curriculum_abdeckung", curriculum_id=str(welt["aktiv"].id))
        assert not fehler
        assert (aus["ik"]["gesamt"], aus["ik"]["verknuepft"]) == (2, 1)

        for kennung in (str(welt["privat"].id), str(uuid.uuid4()), "kein-uuid"):
            text, fehler = await _ruf(rpc, "curriculum_lesen", curriculum_id=kennung)
            assert fehler, kennung


async def test_bildungsplan_kompetenzen(db, welt):
    async with _verbunden(db) as rpc:
        aus, fehler = await _ruf(rpc, "bildungsplan_kompetenzen", fach=welt["fach"].fach_code,
                                 jahrgangsstufe="7/8", bp_version=BP, bereich="optik")
        assert not fehler
        assert [k["nr"] for b in aus["bereiche"] for k in b["kompetenzen"]] == ["3.2.1(1)", "3.2.1(2)"]
        assert aus["fassungen"] == [BP]
        text, fehler = await _ruf(rpc, "bildungsplan_kompetenzen", fach=welt["fach"].fach_code,
                                  jahrgangsstufe="7/8", bp_version="1999")
        assert fehler and BP in text
        _, fehler = await _ruf(rpc, "bildungsplan_kompetenzen", fach=f"Gibtsnicht {TOKEN}", jahrgangsstufe="7")
        assert fehler


async def test_leitlinien_und_uebersicht(db, welt):
    kz = f"T{TOKEN[:4]}".upper()
    async with _verbunden(db) as rpc:
        aus, _ = await _ruf(rpc, "leitlinien")
        eigene = next(l for l in aus["leitlinien"] if l["kuerzel"] == kz)
        assert [a["kuerzel"] for a in eigene["aspekte"]] == [f"{kz}1"]

        aus, fehler = await _ruf(rpc, "leitlinie_uebersicht", kuerzel=kz.lower())
        assert not fehler
        a = aus["aspekte"][0]
        # Entwurf ersetzt nichts (kein kopie_von): beide Curricula zählen, das private nicht
        assert sorted(f["curriculum"] for f in a["fundstellen"]) == sorted([f"Physik 7/8 neu {TOKEN}", f"Physik 7/8 {TOKEN}"])
        assert a["je_fach"] == {welt["fach"].name: 2}
        assert welt["fach"].name in aus["faecher"]

        aus, fehler = await _ruf(rpc, "leitlinie_uebersicht", kuerzel=kz, nur_veroeffentlicht=True)
        assert [f["curriculum"] for f in aus["aspekte"][0]["fundstellen"]] == [f"Physik 7/8 {TOKEN}"]

        text, fehler = await _ruf(rpc, "leitlinie_uebersicht", kuerzel=f"XX{TOKEN}")
        assert fehler and "Kürzel" in text

        aus, fehler = await _ruf(rpc, "leitperspektiven")
        assert not fehler and "leitperspektiven" in aus


async def test_curricula_wie_im_browser(db, welt):
    """Dieselbe Menge wie die Liste der Curricula eines Fachs im Browser (`_lesbare_curricula`)."""
    from app.auth.jwt import JwtPayload
    from app.context.router import _lesbare_curricula

    user = JwtPayload(sub=LEHRKRAFT, roles=["teacher"], grade=None, jti="j", iat=0, exp=9999999999)
    im_browser = {str(c.id) for c in await _lesbare_curricula(db, welt["fach"].id, user)}
    async with _verbunden(db) as rpc:
        aus, _ = await _ruf(rpc, "curricula_finden", fach=welt["fach"].name)
    assert {c["curriculum_id"] for c in aus["curricula"]} == im_browser
    assert str(welt["entwurf"].id) in im_browser and str(welt["privat"].id) not in im_browser


async def test_curriculum_yaml_und_pruefen(db, welt):
    """BA (0.56): Vorlage holen, prüfen — gespeichert wird nichts. Ohne Fachschaft meldet die
    Prüfung das als Fehler; mit Fachschaft läuft sie durch, und es entsteht trotzdem kein Knoten."""
    import sqlalchemy as sa
    import yaml

    from app.db.models import Group, GroupMembership

    fach = welt["fach"]
    db.add(_knoten("fachplan", f"Physik {TOKEN}", read_scope="global", subject_id=fach.id, bp_version=BP,
                   owner_pseudonym="system", metadata_={"bp_id": f"BP_{TOKEN}", "bp_version": BP}))
    await db.flush()

    async def zahl():
        return (await db.execute(sa.select(sa.func.count()).select_from(ContextNode).where(
            ContextNode.subject_id == fach.id))).scalar_one()

    async with _verbunden(db) as rpc:
        aus, fehler = await _ruf(rpc, "curriculum_yaml", curriculum_id=str(welt["aktiv"].id))
        assert not fehler and "Entwurf" in aus["hinweis"]
        daten = yaml.safe_load(aus["yaml"])
        assert daten["kapitel"][0]["titel"] == f"Optik Physik 7/8 {TOKEN}"
        _, fehler = await _ruf(rpc, "curriculum_yaml", curriculum_id=str(welt["privat"].id))
        assert fehler

        daten.update(fach_code=fach.fach_code, bp_id=f"BP_{TOKEN}", jahrgangsstufe="7/8", bp_version=BP)
        text = yaml.safe_dump(daten, allow_unicode=True)
        vorher = await zahl()
        aus, fehler = await _ruf(rpc, "curriculum_yaml_pruefen", yaml=text)
        assert not fehler and not aus["ok"] and "Fachschaft" in aus["fehler"][0]

        gruppe = Group(name=f"FS {TOKEN}", slug=f"fs-{TOKEN}", type="subject_department", subject_id=fach.id)
        db.add(gruppe)
        await db.flush()
        db.add(GroupMembership(group_id=gruppe.id, pseudonym=LEHRKRAFT))
        await db.flush()
        aus, fehler = await _ruf(rpc, "curriculum_yaml_pruefen", yaml=text)
        assert not fehler and aus["ok"], aus
        assert [k["titel"] for k in aus["kapitel"]] == [f"Optik Physik 7/8 {TOKEN}"]
        assert "id" not in aus and "nichts gespeichert" in aus["hinweis"]
        assert await zahl() == vorher

        aus, _ = await _ruf(rpc, "curriculum_yaml_pruefen", yaml="a: &x 1\nb: *x\n")
        assert not aus["ok"] and "Anker" in aus["fehler"][0]
