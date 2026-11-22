"""Leitlinien der Schule (0.50, Päckchen AT).

Anlegen und Ändern über die Schnittstelle (nur Admins, Kürzel Pflicht und eindeutig), Lesen für
Schüler:innen, Verweise im Curriculum (Export, Import, Abdeckung) und die Felder `leitlinien` und
`leitperspektiven` des Curriculum-Assistenten.
"""
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.auth.jwt import JwtPayload
from app.chat.tools import TOOL_REGISTRY, ToolContext
import app.context.curriculum_tools  # noqa: F401 — registriert
from app.context.curriculum_abdeckung import abdeckung
from app.context.curriculum_export import hinweise_uuid_to_code
from app.context.leitlinien import alle_leitlinien, pruefe_leitlinie
from app.context.service import hinweise_code_to_uuid, load_curriculum_tree
from app.db.models import ContextEdge, ContextNode, Group, GroupMembership, Subject

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:5].upper()
# Kürzel einer Leitperspektive bestehen aus Buchstaben — Ziffern im Token würden „X12345“ zu
# einem Aspekt-Kürzel machen.
LP = "X" + TOKEN.translate(str.maketrans("0123456789", "GHIJKLMNOP"))
SDG = f"SDG{TOKEN}"
MITGLIED = f"ll-{TOKEN.lower()}"


def _user(sub, *rollen):
    return JwtPayload(sub=sub, roles=list(rollen), role=rollen[0], grade=None,
                      exp=9999999999, iat=0, jti=str(uuid.uuid4()))


def _knoten(typ, titel, meta, **kw):
    return ContextNode(category="knowledge", content_type=typ, title=titel, content=f"Über {titel}",
                       status="active", read_scope="school", write_scope="school",
                       owner_pseudonym="admin", metadata_=meta, **kw)


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


@pytest_asyncio.fixture
async def leitlinie(db):
    lb = _knoten("leitbild", f"Nachhaltigkeitsziele {TOKEN}", {"kuerzel": SDG})
    a13 = _knoten("leitbild_aspekt", "Klimaschutz", {"kuerzel": f"{SDG}-13", "leitlinie": SDG})
    a2 = _knoten("leitbild_aspekt", "Kein Hunger", {"kuerzel": f"{SDG}-2", "leitlinie": SDG.lower()})
    db.add_all([lb, a13, a2])
    await db.flush()
    return {"lb": lb, "a13": a13, "a2": a2}


# ── Prüfung der Kürzel ───────────────────────────────────────────────────────


async def test_kuerzel_pflicht_eindeutig_und_vereinheitlicht(db, leitlinie):
    with pytest.raises(ValueError, match="Kürzel fehlt"):
        await pruefe_leitlinie(db, "leitbild", {})
    with pytest.raises(ValueError, match="trägt schon"):
        await pruefe_leitlinie(db, "leitbild", {"kuerzel": SDG.lower()})
    # Der Knoten selbst blockiert sein Kürzel nicht.
    assert (await pruefe_leitlinie(db, "leitbild", {"kuerzel": SDG}, leitlinie["lb"].id))["kuerzel"] == SDG
    meta = await pruefe_leitlinie(db, "leitbild_aspekt", {"kuerzel": f" {SDG}-1 ", "leitlinie": f"{SDG.lower()}"})
    assert meta == {"kuerzel": f"{SDG}-1", "leitlinie": SDG}


async def test_aspekt_braucht_vorhandene_leitlinie(db, leitlinie):
    with pytest.raises(ValueError, match="gibt es nicht"):
        await pruefe_leitlinie(db, "leitbild_aspekt", {"kuerzel": f"X{TOKEN}", "leitlinie": f"NIX{TOKEN}"})


async def test_kuerzel_der_leitlinie_bleibt_solange_aspekte_es_nennen(db, leitlinie):
    with pytest.raises(ValueError, match="nennen 2 Aspekte"):
        await pruefe_leitlinie(db, "leitbild", {"kuerzel": f"NEU{TOKEN}"}, leitlinie["lb"].id,
                               vorher={"kuerzel": SDG})


async def test_alle_leitlinien_ordnet_aspekte_natuerlich(db, leitlinie):
    unsere = [l for l in await alle_leitlinien(db) if l.kuerzel == SDG]
    assert [a.kuerzel for a in unsere[0].aspekte] == [f"{SDG}-2", f"{SDG}-13"]


# ── Schnittstelle: nur Admins schreiben, alle lesen ──────────────────────────


@pytest_asyncio.fixture
async def aufraeumen(async_engine):
    yield
    async with async_engine.begin() as conn:
        await conn.execute(sa.delete(ContextNode).where(
            ContextNode.content_type.in_(("leitbild", "leitbild_aspekt")),
            ContextNode.title.like(f"%{TOKEN}%")))


async def test_schnittstelle_rechte_und_pruefung(test_client, auth_headers, auth_headers_teacher2,
                                                 auth_headers_student, aufraeumen):
    neu = {"category": "knowledge", "content_type": "leitbild", "title": f"Weltethos {TOKEN}",
           "read_scope": "school", "write_scope": "school", "metadata": {"kuerzel": f"we {TOKEN}"}}
    r = await test_client.post("/context/nodes", json=neu, headers=auth_headers_teacher2)
    assert r.status_code == 403
    r = await test_client.post("/context/nodes", json=neu, headers=auth_headers)  # Admin
    assert r.status_code == 201, r.text
    lb = r.json()
    assert lb["metadata"]["kuerzel"] == f"WE{TOKEN}"
    assert (await test_client.post("/context/nodes", json=neu, headers=auth_headers)).status_code == 422

    aspekt = {"category": "knowledge", "content_type": "leitbild_aspekt", "title": f"Wahrhaftigkeit {TOKEN}",
              "content": "Nicht lügen.", "read_scope": "school", "write_scope": "school",
              "metadata": {"kuerzel": f"WE{TOKEN}-3", "leitlinie": f"WE{TOKEN}"}}
    r = await test_client.post("/context/nodes", json=aspekt, headers=auth_headers)
    assert r.status_code == 201, r.text
    ohne = {**aspekt, "title": f"Ohne {TOKEN}", "metadata": {"kuerzel": f"WE{TOKEN}-4", "leitlinie": "GIBTSNICHT"}}
    assert (await test_client.post("/context/nodes", json=ohne, headers=auth_headers)).status_code == 422

    # Kürzel der Leitlinie ändern, während ein Aspekt es nennt: abgewiesen.
    r = await test_client.patch(f"/context/nodes/{lb['id']}", json={"metadata": {"kuerzel": "ANDERS"}},
                                headers=auth_headers)
    assert r.status_code == 422
    # Eine Lehrkraft ändert nichts.
    r = await test_client.patch(f"/context/nodes/{lb['id']}", json={"title": "x"}, headers=auth_headers_teacher2)
    assert r.status_code == 403

    # Schüler:innen lesen (AT F6).
    r = await test_client.get("/context/nodes", params={"content_type": "leitbild_aspekt", "q": TOKEN},
                              headers=auth_headers_student)
    assert r.status_code == 200
    assert f"Wahrhaftigkeit {TOKEN}" in [n["title"] for n in r.json()]


# ── Verweise im Curriculum: Export, Import, Abdeckung ────────────────────────


async def test_export_und_import_ueber_kuerzel(db, leitlinie):
    a13, lb = leitlinie["a13"], leitlinie["lb"]
    text = f"Bezug @[Ziele](lb:{lb.id}) und @[{SDG}-13: Klimaschutz](lba:{a13.id})."
    portabel = await hinweise_uuid_to_code(text, db)
    assert portabel == f"Bezug @[Ziele](lb:{SDG}) und @[{SDG}-13: Klimaschutz](lba:{SDG}-13)."

    warnungen = []
    zurueck = await hinweise_code_to_uuid(portabel, db, warnungen)
    assert zurueck == text and warnungen == []

    fremd = await hinweise_code_to_uuid("@[X](lba:FEHLT9)", db, warnungen)
    assert fremd == "@[X](lba:FEHLT9)"
    assert warnungen == ["Aspekt einer Leitlinie 'FEHLT9' nicht gefunden"]


@pytest_asyncio.fixture
async def curriculum(db, leitlinie):
    fach = Subject(slug=f"ll-{TOKEN.lower()}", name=f"Physik {TOKEN}", fach_code=f"L{TOKEN[:4]}")
    db.add(fach)
    await db.flush()
    fs = Group(name=f"FS {TOKEN}", slug=f"fs-ll-{TOKEN.lower()}", type="subject_department", subject_id=fach.id)
    db.add(fs)
    await db.flush()
    db.add(GroupMembership(group_id=fs.id, pseudonym=MITGLIED, role_in_group="teacher"))

    def teil(typ, titel, **kw):
        return ContextNode(category="knowledge", content_type=typ, title=titel, status="draft",
                           read_scope="school", write_scope="subject", write_scope_group_id=fs.id,
                           subject_id=fach.id, owner_pseudonym=MITGLIED, **kw)

    a13 = leitlinie["a13"]
    cur = teil("curriculum", "Physik 7/8", min_grade=7, max_grade=8,
               metadata_={"jahrgangsstufe": "7/8", "bp_version": "2016.V3", "fach": "Physik"})
    kap = teil("kapitel", "Energie", metadata_={"reihenfolge": 1, "std": 4})
    ls = teil("lernsequenz", "Kraftwerke", metadata_={"reihenfolge": 1, "std": 4, "eintraege": [
        {"ik": [], "pk": [], "konkretisierung": "Kohle und Wind",
         "hinweise": f"Exkursion @[{SDG}-13: Klimaschutz](lba:{a13.id})"}]})
    db.add_all([cur, kap, ls])
    await db.flush()
    db.add_all([ContextEdge(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"),
                ContextEdge(from_node_id=ls.id, to_node_id=kap.id, relation="part_of")])
    await db.flush()
    return {"cur": cur, "ls": ls}


async def test_abdeckung_zeigt_vorkommende_aspekte(db, leitlinie, curriculum):
    a = await abdeckung(db, await load_curriculum_tree(db, curriculum["cur"].id))
    unsere = next(l for l in a["leitlinien"] if l["kuerzel"] == SDG)
    assert unsere["vorkommend"] == 1
    assert {x["kuerzel"]: x["lernsequenzen"] for x in unsere["aspekte"]} == {
        f"{SDG}-2": [], f"{SDG}-13": ["Kraftwerke"]}


# ── Curriculum-Assistent ─────────────────────────────────────────────────────


async def _ruf(name, db, cur, **args):
    ctx = ToolContext(db=db, user=_user(MITGLIED, "teacher"), group_id=None, conversation_id=None,
                      curriculum_node_id=cur.id)
    return await TOOL_REGISTRY[name].handler(args, ctx)


async def test_assistent_liest_kuerzel_statt_token(db, leitlinie, curriculum):
    entwurf = await _ruf("get_curriculum_draft", db, curriculum["cur"])
    eintrag = entwurf["kapitel"][0]["lernsequenzen"][0]["eintraege"][0]
    assert eintrag["hinweise"] == "Exkursion"
    assert eintrag["leitlinien"] == [f"{SDG}-13"]
    unsere = next(l for l in entwurf["leitlinien_der_schule"] if l["kuerzel"] == SDG)
    assert [a["kuerzel"] for a in unsere["aspekte"]] == [f"{SDG}-2", f"{SDG}-13"]

    abd = await _ruf("get_curriculum_coverage", db, curriculum["cur"])
    unsere = next(l for l in abd["leitlinien"] if l["kuerzel"] == SDG)
    assert unsere["nicht_vorkommend"] == [f"{SDG}-2"]


@pytest_asyncio.fixture
async def leitperspektive(db):
    def lp(typ, titel, meta):
        return ContextNode(category="knowledge", content_type=typ, title=titel, status="active",
                           read_scope="global", write_scope="global", owner_pseudonym="system", metadata_=meta)

    kopf = lp("leitperspektive", f"Nachhaltige Entwicklung {TOKEN}", {"bp_id": f"BP2016BW_ALLG_LP_{LP}", "kuerzel": LP})
    a3 = lp("leitperspektive_aspekt", "Werte und Normen in Entscheidungssituationen",
            {"bp_id": f"{LP}_03", "kuerzel": LP, "aspekt_nr": 3})
    a1 = lp("leitperspektive_aspekt", "Bedeutung nachhaltiger Entwicklung",
            {"bp_id": f"{LP}_01", "kuerzel": LP, "aspekt_nr": 1})
    db.add_all([kopf, a3, a1])
    await db.flush()
    return {"kopf": kopf, "a3": a3, "a1": a1}


async def test_assistent_holt_aspekte_der_leitperspektiven_auf_abruf(db, leitlinie, curriculum, leitperspektive):
    entwurf = await _ruf("get_curriculum_draft", db, curriculum["cur"])
    kopf = next(e for e in entwurf["leitperspektiven"] if e["kuerzel"] == LP)
    assert kopf["aspekte"] == 2  # nur die Zahl — die Aspekte selbst kommen auf Abruf

    lp = await _ruf("get_bp_competences", db, curriculum["cur"], typ="lp", bereich=LP.lower())
    assert [e["kuerzel"] for e in lp["leitperspektiven"]] == [LP]
    assert lp["leitperspektiven"][0]["aspekte"] == [
        {"kuerzel": f"{LP}_01", "titel": "Bedeutung nachhaltiger Entwicklung"},
        {"kuerzel": f"{LP}_03", "titel": "Werte und Normen in Entscheidungssituationen"}]


async def test_assistent_schreibt_aspekt_einer_leitperspektive_in_jeder_schreibweise(
        db, leitlinie, curriculum, leitperspektive):
    ls, cur, a3 = curriculum["ls"], curriculum["cur"], leitperspektive["a3"]
    for schreibweise in (f"{LP}_03", f"{LP} 3", f"{LP.lower()}3", f"{LP}-03", "Werte und Normen in Entscheidungssituationen"):
        r = await _ruf("apply_curriculum_operations", db, cur, operations=[
            {"op": "eintrag_aendern", "lernsequenz_id": str(ls.id), "eintrag": 1, "leitperspektiven": [schreibweise]}])
        assert r.get("ok") is True, (schreibweise, r)
        await db.refresh(ls)
        hinweise = ls.metadata_["eintraege"][0]["hinweise"]
        # Beschriftung wie aus dem Editor
        assert f"@[{LP} 3: Werte und Normen in Entscheidungssituationen](lpa:{a3.id})" in hinweise, schreibweise
    kanten = set((await db.execute(sa.select(ContextEdge.to_node_id).where(
        ContextEdge.from_node_id == ls.id, ContextEdge.relation == "references"))).scalars())
    assert a3.id in kanten


async def test_aspekt_aus_dem_editor_liest_der_assistent_als_kuerzel(db, leitlinie, curriculum, leitperspektive):
    ls, a1 = curriculum["ls"], leitperspektive["a1"]
    eintraege = [{**ls.metadata_["eintraege"][0],
                  "hinweise": f"Diskussion @[{LP} 1: Bedeutung nachhaltiger Entwicklung](lpa:{a1.id})"}]
    ls.metadata_ = {**ls.metadata_, "eintraege": eintraege}
    await db.flush()
    entwurf = await _ruf("get_curriculum_draft", db, curriculum["cur"])
    eintrag = entwurf["kapitel"][0]["lernsequenzen"][0]["eintraege"][0]
    assert eintrag["hinweise"] == "Diskussion"
    assert eintrag["leitperspektiven"] == [f"{LP}_01"]


async def test_assistent_schreibt_leitlinien_und_behaelt_sie_bei_neuem_hinweis(db, leitlinie, curriculum,
                                                                              leitperspektive):
    ls, cur = curriculum["ls"], curriculum["cur"]
    lp = leitperspektive["kopf"]

    r = await _ruf("apply_curriculum_operations", db, cur, operations=[
        {"op": "eintrag_aendern", "lernsequenz_id": str(ls.id), "eintrag": 1,
         "leitlinien": [f"{SDG.lower()}-2", "Klimaschutz"], "leitperspektiven": [LP]}])
    assert r.get("ok") is True, r
    await db.refresh(ls)
    hinweise = ls.metadata_["eintraege"][0]["hinweise"]
    assert hinweise.startswith("Exkursion @[")
    assert f"(lp:{lp.id})" in hinweise
    assert f"(lba:{leitlinie['a2'].id})" in hinweise and f"(lba:{leitlinie['a13'].id})" in hinweise
    ziele = set((await db.execute(sa.select(ContextEdge.to_node_id).where(
        ContextEdge.from_node_id == ls.id, ContextEdge.relation == "references"))).scalars())
    assert {lp.id, leitlinie["a2"].id, leitlinie["a13"].id} <= ziele

    # Nur der Text ändert sich — die Verweise bleiben.
    r = await _ruf("apply_curriculum_operations", db, cur, operations=[
        {"op": "eintrag_aendern", "lernsequenz_id": str(ls.id), "eintrag": 1, "hinweise": "Besuch im Windpark"}])
    assert r.get("ok") is True, r
    await db.refresh(ls)
    hinweise = ls.metadata_["eintraege"][0]["hinweise"]
    assert hinweise.startswith("Besuch im Windpark @[") and f"(lba:{leitlinie['a2'].id})" in hinweise


async def test_assistent_unbekanntes_kuerzel_nennt_die_moeglichen(db, leitlinie, curriculum):
    r = await _ruf("preview_curriculum_operations", db, curriculum["cur"], operations=[
        {"op": "eintrag_aendern", "lernsequenz_id": str(curriculum["ls"].id), "eintrag": 1,
         "leitlinien": ["SDG99-UNBEKANNT"]}])
    assert r.get("ok") is False
    assert "Möglich:" in str(r) and f"{SDG}-13" in str(r)


# ── Leitfaden Demokratiebildung (0.53.1): `lpa:` zeigt auch auf seine Teile ─────

NR = 900 + int(uuid.uuid4().int % 99)  # Baustein-Nummer, die echte Daten nicht haben
LFDB_B = f"BP2016BW_ALLG_LP_LFDB_B{NR}"


@pytest_asyncio.fixture
async def lfdb(db):
    def k(typ, titel, bp_id):
        return ContextNode(category="knowledge", content_type=typ, title=titel, status="active",
                           read_scope="global", write_scope="global", owner_pseudonym="system",
                           metadata_={"bp_id": bp_id})

    kopf = k("leitperspektive", "Leitfaden Demokratiebildung", "BP2016BW_ALLG_LP_LFDB")
    b = k("lfdb_baustein", f"Baustein {NR}: Identität {TOKEN}", LFDB_B)
    t = k("lfdb_themenblock", f"Wer bin ich {TOKEN}", f"{LFDB_B}_T1")
    kp = k("lfdb_kompetenz", f"Was macht mich aus {TOKEN}?", f"{LFDB_B}_T1_K2")
    db.add_all([kopf, b, t, kp])
    await db.flush()
    return {"b": b, "t": t, "k": kp}


async def test_assistent_schreibt_und_liest_verweise_auf_den_lfdb(db, leitlinie, curriculum, lfdb):
    ls, cur, t, kp = curriculum["ls"], curriculum["cur"], lfdb["t"], lfdb["k"]
    r = await _ruf("apply_curriculum_operations", db, cur, operations=[
        {"op": "eintrag_aendern", "lernsequenz_id": str(ls.id), "eintrag": 1,
         "leitperspektiven": [f"LFDB B{NR}.T1", f"lfdb_b{NR}_t1_k2"]}])
    assert r.get("ok") is True, r
    await db.refresh(ls)
    hinweise = ls.metadata_["eintraege"][0]["hinweise"]
    assert f"@[LFDB B{NR}.T1: Wer bin ich {TOKEN}](lpa:{t.id})" in hinweise
    assert f"(lpa:{kp.id})" in hinweise
    kanten = set((await db.execute(sa.select(ContextEdge.to_node_id).where(
        ContextEdge.from_node_id == ls.id, ContextEdge.relation == "references"))).scalars())
    assert {t.id, kp.id} <= kanten

    entwurf = await _ruf("get_curriculum_draft", db, cur)
    eintrag = entwurf["kapitel"][0]["lernsequenzen"][0]["eintraege"][0]
    assert eintrag["leitperspektiven"] == [f"LFDB_B{NR}_T1", f"LFDB_B{NR}_T1_K2"]

    lp = await _ruf("get_bp_competences", db, cur, typ="lp", bereich="LFDB")
    teile = [a["kuerzel"] for a in lp["leitperspektiven"][0]["aspekte"]]
    assert [x for x in teile if f"B{NR}" in x] == [f"LFDB_B{NR}", f"LFDB_B{NR}_T1", f"LFDB_B{NR}_T1_K2"]


async def test_lfdb_verweis_ueberlebt_export_und_import(db, lfdb):
    t = lfdb["t"]
    text = f"Bezug @[LFDB B{NR}.T1: Wer bin ich](lpa:{t.id})."
    portabel = await hinweise_uuid_to_code(text, db)
    assert portabel == f"Bezug @[LFDB B{NR}.T1: Wer bin ich](lpa:{LFDB_B}_T1)."
    warnungen = []
    assert await hinweise_code_to_uuid(portabel, db, warnungen) == text and warnungen == []
