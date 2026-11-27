"""Die Werkzeuge des MCP-Servers (0.54, Päckchen AW Schritt 4) — über die ASGI-App mit echtem
Token, in der Test-Transaktion. Erfordert TEST_DATABASE_URL."""
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
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
             "curriculum_yaml", "curriculum_yaml_pruefen", "verlaufsplaene_finden", "verlaufsplan_lesen"}


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


async def test_elf_werkzeuge_alle_lesend(db, welt):
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


async def test_curricula_finden_kuerzel_genau(db, welt):
    """Ein Kürzel trifft nur sein Fach, nicht jedes, dessen Name es enthält (0.60)."""
    code = welt["fach"].fach_code
    anderes = Subject(slug=f"mx-{TOKEN}", name=f"Musik{code.lower()}kunde", fach_code=f"MU{TOKEN[:3]}".upper())
    db.add(anderes)
    await db.flush()
    db.add(_knoten("curriculum", f"Musik {TOKEN}", subject_id=anderes.id, min_grade=7, max_grade=8,
                   metadata_={"jahrgangsstufe": "7/8"}))
    await db.flush()
    async with _verbunden(db) as rpc:
        aus, _ = await _ruf(rpc, "curricula_finden", fach=code)
        assert {c["fach"] for c in aus["curricula"]} == {welt["fach"].name}
        # Ohne genauen Treffer weiter als Teil des Namens
        aus, _ = await _ruf(rpc, "curricula_finden", fach=f"{code.lower()}kunde")
        assert {c["fach"] for c in aus["curricula"]} == {anderes.name}


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


async def test_querverweise_in_curriculum_und_kompetenzen(db, welt):
    """AY Teil 1 (F7): Querverweise des Bildungsplans in ein anderes Fach, mit Fundstelle."""
    chemie = Subject(slug=f"mwc-{TOKEN}", name=f"Chemie {TOKEN}", fach_code=f"C{TOKEN[:4]}".upper())
    db.add(chemie)
    await db.flush()
    ziel = _knoten("ik_kompetenz", "3.2.2(4) Stoffe und Licht", read_scope="global", subject_id=chemie.id,
                   bp_version=BP, min_grade=7, max_grade=8, owner_pseudonym="system",
                   metadata_={"kompetenz_nr": "3.2.2(4)"})
    cur = _knoten("curriculum", f"Chemie 7/8 {TOKEN}", "active", subject_id=chemie.id, min_grade=7, max_grade=8,
                  metadata_={"jahrgangsstufe": "7/8", "bp_version": BP, "fach": chemie.name})
    kap = _knoten("kapitel", f"Stoffe {TOKEN}", "active", subject_id=chemie.id, metadata_={"reihenfolge": 1})
    ls = _knoten("lernsequenz", f"LS {TOKEN}", "active", subject_id=chemie.id, metadata_={"reihenfolge": 1})
    db.add_all([ziel, cur, kap, ls])
    await db.flush()
    komp = (await db.execute(sa.select(ContextNode).where(
        ContextNode.subject_id == welt["fach"].id, ContextNode.content_type == "ik_kompetenz",
        ContextNode.title.like("3.2.1(1)%")))).scalar_one()
    db.add_all([ContextEdge(from_node_id=komp.id, to_node_id=ziel.id, relation="related_to"),
                ContextEdge(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"),
                ContextEdge(from_node_id=ls.id, to_node_id=kap.id, relation="part_of"),
                ContextEdge(from_node_id=ls.id, to_node_id=ziel.id, relation="references")])
    await db.flush()

    async with _verbunden(db) as rpc:
        aus, fehler = await _ruf(rpc, "curriculum_lesen", curriculum_id=str(welt["aktiv"].id))
        assert not fehler
        assert aus["querverweise"] == [{"ik": "3.2.1(1)", "verweise": [{
            "fach": chemie.name, "kuerzel": chemie.fach_code, "art": "Kompetenz", "nr": "3.2.2(4)",
            "titel": "Stoffe und Licht", "stufen": "7/8",
            "behandelt_in": [f"{cur.title} › {kap.title}"]}]}]

        aus, fehler = await _ruf(rpc, "bildungsplan_kompetenzen", fach=welt["fach"].fach_code,
                                 jahrgangsstufe="7/8", bp_version=BP, bereich="optik")
        assert not fehler
        k1, k2 = [k for b in aus["bereiche"] for k in b["kompetenzen"]]
        assert [v["nr"] for v in k1["querverweise"]] == ["3.2.2(4)"]
        assert "querverweise" not in k2


async def test_absprachen_in_curriculum_lesen(db, welt):
    """AY Teil 2 (0.63): Absprachen beider Richtungen in `curriculum_lesen`, Art aus Sicht des Curriculums."""
    chemie = Subject(slug=f"mwa-{TOKEN}", name=f"Chemie A {TOKEN}", fach_code=f"A{TOKEN[:4]}".upper())
    db.add(chemie)
    await db.flush()
    ph_kap = (await db.execute(sa.select(ContextNode).join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
                               .where(ContextEdge.to_node_id == welt["aktiv"].id, ContextNode.content_type == "kapitel")
                               )).scalars().first()
    cur = _knoten("curriculum", f"Chemie A 7/8 {TOKEN}", "active", subject_id=chemie.id, min_grade=7, max_grade=8,
                  metadata_={"jahrgangsstufe": "7/8", "bp_version": BP, "fach": chemie.name})
    kap = _knoten("kapitel", f"Licht {TOKEN}", "active", subject_id=chemie.id, metadata_={
        "reihenfolge": 1, "absprachen": [{"id": str(uuid.uuid4()), "fach_code": welt["fach"].fach_code,
                                          "kapitel_id": str(ph_kap.id), "kapitel_titel": ph_kap.title,
                                          "art": "vorher", "text": "Optik zuerst"}]})
    db.add_all([cur, kap])
    await db.flush()
    db.add(ContextEdge(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"))
    await db.flush()

    async with _verbunden(db) as rpc:
        aus, fehler = await _ruf(rpc, "curriculum_lesen", curriculum_id=str(cur.id))
        assert not fehler
        [k] = [x for x in aus["kapitel"] if x.get("absprachen")]
        assert k["titel"] == kap.title
        [e] = k["absprachen"]["eigene"]
        assert (e["nr"], e["art"], e["ziel"]["kapitel"]) == (1, "vorher", ph_kap.title)
        aus, fehler = await _ruf(rpc, "curriculum_lesen", curriculum_id=str(welt["aktiv"].id))
        assert not fehler
        [k] = [x for x in aus["kapitel"] if x.get("absprachen")]
        [a] = k["absprachen"]["von_anderen_faechern"]
        assert (a["fach"], a["art"], a["text"]) == (chemie.name, "nachher", "Optik zuerst")
        assert a["eingetragen_in"]["curriculum"] == cur.title


# ── Jahresverlaufspläne (0.60, BD Teil B Schritt 6) ───────────────────────────

async def test_verlaufsplaene_finden_und_lesen(db, welt, monkeypatch):
    from app.context import verlaufsplan as vp
    from tests.unit.test_verlaufsplan_zeit import KALENDER_2025_26

    monkeypatch.setattr(vp, "aktuelles_schuljahr", lambda: "2025/26")
    monkeypatch.setattr(vp, "kalender_fuer", lambda sj: KALENDER_2025_26 if sj == "2025/26" else None)
    kap = (await db.execute(sa.select(ContextNode).join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
                            .where(ContextEdge.to_node_id == welt["aktiv"].id, ContextNode.content_type == "kapitel"))).scalar_one()
    plaene = []
    for sj, status in (("2025/26", "active"), ("2024/25", "draft")):
        p = _knoten("verlaufsplan", f"JVP Physik 7 {sj}", status, subject_id=welt["fach"].id, min_grade=7, max_grade=7,
                    write_scope="school", metadata_={"schuljahr": sj, "planungsart": "kapitel", "beschlossen_am": "2025-10-01",
                                                     "abschnitte": [{"id": "a1", "titel": "Licht", "wochen": 3,
                                                                     "kapitel_ids": [str(kap.id)], "notiz": ""},
                                                                    {"id": "a2", "titel": "Puffer", "wochen": 1, "puffer": True}]})
        db.add(p)
        plaene.append(p)
    await db.flush()

    async with _verbunden(db) as rpc:
        aus, fehler = await _ruf(rpc, "verlaufsplaene_finden", fach=welt["fach"].name)
        assert not fehler, aus
        assert aus["laufendes_schuljahr"] == "2025/26"
        assert [(p["schuljahr"], p["status"], p["archiviert"], p["wochen"]) for p in aus["verlaufsplaene"]] == [
            ("2025/26", "beschlossen", False, 4), ("2024/25", "entwurf", True, 4)]
        aus, _ = await _ruf(rpc, "verlaufsplaene_finden", fach=welt["fach"].name, schuljahr="2024/25", jahrgangsstufe="7")
        assert [p["verlaufsplan_id"] for p in aus["verlaufsplaene"]] == [str(plaene[1].id)]
        aus, _ = await _ruf(rpc, "verlaufsplaene_finden", fach=welt["fach"].name, jahrgangsstufe="8")
        assert aus["verlaufsplaene"] == []

        plan, fehler = await _ruf(rpc, "verlaufsplan_lesen", verlaufsplan_id=str(plaene[0].id))
        assert not fehler, plan
        assert plan["abschnitte"][0]["kapitel"] == [{"id": str(kap.id), "titel": kap.title}]
        assert (plan["abschnitte"][0]["von_woche"], plan["abschnitte"][0]["beginn"]) == (1, "2025-09-15")
        assert plan["abschnitte"][1]["puffer"] is True and plan["puffer_wochen"] == 1
        assert plan["ferien"][0]["name"] == "Herbstferien"
        assert "darf_bearbeiten" not in plan and "curricula" not in plan

        # Früheres Schuljahr ohne Kalender: nur Wochen
        alt, _ = await _ruf(rpc, "verlaufsplan_lesen", verlaufsplan_id=str(plaene[1].id))
        assert alt["status"] == "entwurf" and "Kalender" in alt["hinweis"]

        # Per Kürzel genau gefunden
        aus, _ = await _ruf(rpc, "verlaufsplaene_finden", fach=welt["fach"].fach_code)
        assert len(aus["verlaufsplaene"]) == 2

        # Das Kapitel wird archiviert (neue Fassung): Titel bleibt, gekennzeichnet
        kap.status = "archived"
        await db.flush()
        plan, _ = await _ruf(rpc, "verlaufsplan_lesen", verlaufsplan_id=str(plaene[0].id))
        assert plan["abschnitte"][0]["kapitel"] == [{"id": str(kap.id), "titel": kap.title,
                                                    "nicht_mehr_im_curriculum": True}]

        text, fehler = await _ruf(rpc, "verlaufsplan_lesen", verlaufsplan_id=str(uuid.uuid4()))
        assert fehler and "gibt es nicht" in text
        text, fehler = await _ruf(rpc, "verlaufsplan_lesen", verlaufsplan_id="kein-uuid")
        assert fehler and "Ungültige Kennung" in text
