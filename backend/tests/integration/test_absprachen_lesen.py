"""Absprachen in beide Richtungen (0.63, AY Teil 2, Schritt 2). Erfordert TEST_DATABASE_URL."""
import uuid

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.context.absprachen import absprachen_des_curriculums
from app.db.models import ContextEdge, ContextNode
from app.db.session import get_db

pytestmark = pytest.mark.asyncio

LEHRKRAFT = JwtPayload(sub="ay2-lk", roles=["teacher"], grade=None, jti="j", iat=0, exp=9999999999)
SCHUELER = JwtPayload(sub="ay2-s", roles=["student"], grade="8", jti="j", iat=0, exp=9999999999)


async def _fach(db, slug, code):
    return (await db.execute(sa.text(
        "INSERT INTO subjects (slug, name, fach_code) VALUES (:s, :n, :c) "
        "ON CONFLICT (slug) DO UPDATE SET fach_code = EXCLUDED.fach_code, name = EXCLUDED.name RETURNING id"),
        {"s": slug, "n": slug.split("-")[0].title(), "c": code})).scalar_one()


class Welt:
    def __init__(self, db):
        self.db = db

    async def curriculum(self, fach, titel, stufen=(8, 8), status="active", scope="school", kopie_von=None):
        c = ContextNode(id=uuid.uuid4(), category="knowledge", content_type="curriculum", title=titel,
                        status=status, owner_pseudonym="system", read_scope=scope,
                        write_scope="private" if scope == "private" else "school",
                        subject_id=fach, min_grade=stufen[0], max_grade=stufen[1],
                        metadata_={"kopie_von": str(kopie_von)} if kopie_von else {})
        self.db.add(c)
        await self.db.flush()
        return c

    async def kapitel(self, cur, titel, absprachen=None, kopie_von=None, nr=1):
        meta = {"reihenfolge": nr}
        if absprachen is not None:
            meta["absprachen"] = absprachen
        if kopie_von:
            meta["kopie_von"] = str(kopie_von)
        k = ContextNode(id=uuid.uuid4(), category="knowledge", content_type="kapitel", title=titel,
                        status=cur.status, owner_pseudonym="system", read_scope=cur.read_scope,
                        write_scope=cur.write_scope, subject_id=cur.subject_id, metadata_=meta)
        self.db.add(k)
        await self.db.flush()
        self.db.add(ContextEdge(from_node_id=k.id, to_node_id=cur.id, relation="part_of", metadata_={}))
        await self.db.flush()
        return k


def _abspr(fach, kapitel=None, art="vorher", text="", aid=None):
    return {"id": aid or str(uuid.uuid4()), "fach_code": fach, "kapitel_id": str(kapitel.id) if kapitel else None,
            "kapitel_titel": kapitel.title if kapitel else None, "art": art, "text": text}


@pytest_asyncio.fixture
async def w(db_session):
    w = Welt(db_session)
    w.m = await _fach(db_session, "mathematik-ay2", "MAY")
    w.ph = await _fach(db_session, "physik-ay2", "PHAY")
    w.m8 = await w.curriculum(w.m, "Mathematik Kl. 8")
    w.brueche = await w.kapitel(w.m8, "Brüche")
    w.ph8 = await w.curriculum(w.ph, "Physik Kl. 8")
    w.vorher = _abspr("MAY", w.brueche, "vorher", "Bruchrechnung zuerst")
    w.dichte = await w.kapitel(w.ph8, "Dichte", [w.vorher, _abspr("MAY", art="abgestimmt", text="Einheiten gleich")])
    # Mathematik hält die Gegenabsprache fest
    w.brueche.metadata_ = {**w.brueche.metadata_, "absprachen": [_abspr("PHAY", w.dichte, "nachher")]}
    await db_session.flush()
    return w


async def test_beide_richtungen_beidseitig_und_fach(db_session, w):
    r = await absprachen_des_curriculums(db_session, w.m8, LEHRKRAFT)
    k = r["kapitel"][str(w.brueche.id)]
    [eigen] = k["eigene"]
    assert (eigen["fach_code"], eigen["art"], eigen["ziel"]["kapitel"], eigen["ziel"]["curriculum"]) == (
        "PHAY", "nachher", "Dichte", "Physik Kl. 8")
    [aussen] = k["von_aussen"]
    assert (aussen["fach_code"], aussen["art"], aussen["art_hier"], aussen["text"]) == (
        "PHAY", "vorher", "nachher", "Bruchrechnung zuerst")
    assert aussen["quelle"]["kapitel"] == "Dichte" and eigen["beidseitig"] and aussen["beidseitig"]
    assert eigen["text_gegenseite"] == "Bruchrechnung zuerst"
    [an_fach] = r["fach"]
    assert (an_fach["art"], an_fach["text"], an_fach["quelle"]["curriculum"]) == ("abgestimmt", "Einheiten gleich",
                                                                                  "Physik Kl. 8")
    # Von der Physik aus gesehen
    r = await absprachen_des_curriculums(db_session, w.ph8, LEHRKRAFT)
    k = r["kapitel"][str(w.dichte.id)]
    assert [e["art"] for e in k["eigene"]] == ["vorher", "abgestimmt"]
    assert k["eigene"][0]["beidseitig"] and not k["eigene"][1]["beidseitig"]
    assert k["eigene"][1]["ziel"] is None
    assert [a["quelle"]["kapitel"] for a in k["von_aussen"]] == ["Brüche"]


async def test_fach_absprache_nur_bei_ueberschneidenden_stufen(db_session, w):
    m5 = await w.curriculum(w.m, "Mathematik Kl. 5/6", (5, 6))
    await w.kapitel(m5, "Zahlen")
    assert (await absprachen_des_curriculums(db_session, m5, LEHRKRAFT))["fach"] == []


async def test_ersatz_auf_beiden_seiten(db_session, w):
    # Mathematik wird ersetzt: die Absprache der Physik zeigt auf das alte Kapitel
    m8neu = await w.curriculum(w.m, "Mathematik Kl. 8 neu", kopie_von=w.m8.id)
    brueche_neu = await w.kapitel(m8neu, "Brüche", kopie_von=w.brueche.id)
    # Physik wird ersetzt: Ziel der Mathematik-Absprache ist das archivierte Kapitel
    ph8neu = await w.curriculum(w.ph, "Physik Kl. 8 neu", kopie_von=w.ph8.id)
    dichte_neu = await w.kapitel(ph8neu, "Dichte", [w.vorher], kopie_von=w.dichte.id)
    brueche_neu.metadata_ = {**brueche_neu.metadata_, "absprachen": w.brueche.metadata_["absprachen"]}
    for n in (w.m8, w.brueche, w.ph8, w.dichte):
        n.status = "archived"
    await db_session.flush()

    r = await absprachen_des_curriculums(db_session, m8neu, LEHRKRAFT)
    k = r["kapitel"][str(brueche_neu.id)]
    assert k["eigene"][0]["ziel"]["kapitel_id"] == str(dichte_neu.id)
    assert [a["quelle"]["kapitel_id"] for a in k["von_aussen"]] == [str(dichte_neu.id)]
    assert k["eigene"][0]["beidseitig"]


async def test_entwurf_als_kopie_doppelt_nicht_schueler_sehen_keine_entwuerfe(db_session, w):
    entwurf = await w.curriculum(w.ph, "Physik Kl. 8 (Entwurf)", status="draft", kopie_von=w.ph8.id)
    neu = _abspr("MAY", w.brueche, "gleichzeitig", "nur im Entwurf")
    await w.kapitel(entwurf, "Dichte", [w.vorher, neu], kopie_von=w.dichte.id)
    r = await absprachen_des_curriculums(db_session, w.m8, LEHRKRAFT)
    aussen = r["kapitel"][str(w.brueche.id)]["von_aussen"]
    assert sorted((a["text"], a["quelle"]["status"]) for a in aussen) == [
        ("Bruchrechnung zuerst", "active"), ("nur im Entwurf", "draft")]
    r = await absprachen_des_curriculums(db_session, w.m8, SCHUELER)
    assert [a["text"] for a in r["kapitel"][str(w.brueche.id)]["von_aussen"]] == ["Bruchrechnung zuerst"]


async def test_private_quelle_bleibt_verborgen(db_session, w):
    privat = await w.curriculum(w.ph, "Physik privat", scope="private")
    await w.kapitel(privat, "Geheim", [_abspr("MAY", w.brueche, "vorher", "privat")])
    r = await absprachen_des_curriculums(db_session, w.m8, LEHRKRAFT)
    assert "privat" not in [a["text"] for a in r["kapitel"][str(w.brueche.id)]["von_aussen"]]


async def test_route(db_session, w):
    from app.context.router import router

    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: LEHRKRAFT
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/context/curricula/{w.m8.id}/absprachen")
        assert r.status_code == 200, r.text
        assert r.json()["kapitel"][str(w.brueche.id)]["eigene"][0]["fach_code"] == "PHAY"
        assert (await c.get(f"/context/curricula/{uuid.uuid4()}/absprachen")).status_code == 404


async def test_speichern_ueber_den_knoten(db_session, w, monkeypatch):
    from app.context.router import router

    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)

    admin = JwtPayload(sub="ay2-admin", roles=["admin", "teacher"], grade=None, jti="j", iat=0, exp=9999999999)
    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: admin
    meta = {**w.brueche.metadata_, "absprachen": [
        {"fach_code": "phay", "kapitel_id": str(w.dichte.id), "art": "gleichzeitig", "text": " zusammen "}]}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.patch(f"/context/nodes/{w.brueche.id}", json={"metadata": meta})
        assert r.status_code == 200, r.text
        [a] = r.json()["metadata"]["absprachen"]
        assert (a["fach_code"], a["text"], a["kapitel_titel"]) == ("PHAY", "zusammen", "Dichte")
        meta["absprachen"] = [{"fach_code": "PHAY", "art": "vorher"}]
        r = await c.patch(f"/context/nodes/{w.brueche.id}", json={"metadata": meta})
        assert r.status_code == 422 and "braucht ein Kapitel" in r.json()["detail"]


async def test_yaml_rundweg_aufloesen_und_warnungen(db_session, w):
    """Export schreibt Fach und Kapiteltitel; der Import löst sie wieder auf (Schritt 5)."""
    from app.context.absprachen import aus_yaml_aufloesen, export_zeilen, fuer_yaml
    from app.context.service import load_curriculum_tree

    w.m8.metadata_ = {"jahrgangsstufe": "8"}
    w.ph8.metadata_ = {"jahrgangsstufe": "8"}
    await db_session.flush()
    raus = await fuer_yaml(db_session, w.brueche.metadata_["absprachen"])
    assert raus == [{"fach_code": "PHAY", "kapitel": "Dichte", "jahrgangsstufe": "8", "art": "nachher"}]

    rein, warnungen = await aus_yaml_aufloesen(db_session, [
        {"fach_code": "PHAY", "kapitel_titel": "dichte ", "jahrgangsstufe": "8", "art": "nachher", "text": ""},
        {"fach_code": "PHAY", "kapitel_titel": "Gibt es nicht", "jahrgangsstufe": None, "art": "vorher", "text": ""},
        {"fach_code": "XXAY", "kapitel_titel": None, "jahrgangsstufe": None, "art": "abgestimmt", "text": "t"},
    ], "8")
    assert rein[0]["kapitel_id"] == str(w.dichte.id) and rein[0]["kapitel_titel"] == "Dichte"
    assert rein[1]["kapitel_id"] is None and rein[1]["kapitel_titel"] == "Gibt es nicht"
    assert len(rein) == 2
    assert any("nicht gefunden" in x for x in warnungen) and any("„XXAY“" in x for x in warnungen)

    # Gleicher Titel in zwei Curricula: die Stufe entscheidet, sonst Warnung
    ph9 = await w.curriculum(w.ph, "Physik Kl. 9", (9, 9))
    ph9.metadata_ = {"jahrgangsstufe": "9"}
    dichte9 = await w.kapitel(ph9, "Dichte")
    await db_session.flush()
    rein, warnungen = await aus_yaml_aufloesen(db_session, [
        {"fach_code": "PHAY", "kapitel_titel": "Dichte", "jahrgangsstufe": "9", "art": "vorher", "text": ""}])
    assert rein[0]["kapitel_id"] == str(dichte9.id) and warnungen == []
    rein, warnungen = await aus_yaml_aufloesen(db_session, [
        {"fach_code": "PHAY", "kapitel_titel": "Dichte", "jahrgangsstufe": None, "art": "vorher", "text": ""}])
    assert rein[0]["kapitel_id"] is None and "nicht eindeutig" in warnungen[0]

    # PDF/DOCX: kompakte Zeilen der eigenen Absprachen
    tree = await load_curriculum_tree(db_session, w.ph8.id)
    assert tree
    zeilen = await export_zeilen(db_session, tree)
    assert zeilen[str(w.dichte.id)] == ["Mathematik · Brüche — kommt vorher: Bruchrechnung zuerst",
                                        "Mathematik · ganzes Fach — abgestimmt: Einheiten gleich"]


def _verlaufsplan(fach_id, abschnitte, status="active", stufe=8):
    return ContextNode(id=uuid.uuid4(), category="knowledge", content_type="verlaufsplan", title=f"Plan {stufe}",
                       status=status, subject_id=fach_id, min_grade=stufe, max_grade=stufe, read_scope="school",
                       write_scope="private", owner_pseudonym="test",
                       metadata_={"schuljahr": "2025/26", "planungsart": "kapitel", "abschnitte": abschnitte})


async def test_zeitpruefung_mit_den_verlaufsplaenen(db_session, w, monkeypatch):
    """Teil B (Schritt 8): Physik hält „Brüche vorher“ ein, solange Mathematik Brüche zuerst plant."""
    from app.context import verlaufsplan as vp
    from app.planning import calendar
    from tests.unit.test_verlaufsplan_zeit import KALENDER_2025_26

    monkeypatch.setattr(vp, "aktuelles_schuljahr", lambda: "2025/26")
    monkeypatch.setattr(calendar, "kalender_fuer", lambda sj: KALENDER_2025_26 if sj == "2025/26" else None)
    m_plan = _verlaufsplan(w.m, [{"id": "a", "wochen": 4, "kapitel_ids": [str(w.brueche.id)]}])
    ph_plan = _verlaufsplan(w.ph, [{"id": "b", "wochen": 3, "kapitel_ids": []},
                                   {"id": "c", "wochen": 3, "kapitel_ids": [str(w.dichte.id)]}], status="draft")
    db_session.add_all([m_plan, ph_plan])
    await db_session.flush()

    r = await absprachen_des_curriculums(db_session, w.ph8, LEHRKRAFT)
    vorher = r["kapitel"][str(w.dichte.id)]["eigene"][0]
    assert vorher["art"] == "vorher"
    p = vorher["pruefung"]
    assert p["ergebnis"] == "eingehalten" and p["hier"].startswith("Kl. 8, KW") and p["hier"].endswith("(Entwurf)")
    assert "pruefung" not in r["kapitel"][str(w.dichte.id)]["eigene"][1]   # abgestimmt ohne Kapitel

    # Mathematik schiebt Brüche hinter Dichte → aus Sicht der Mathematik verletzt
    m_plan.metadata_ = {**m_plan.metadata_, "abschnitte": [
        {"id": "x", "wochen": 8, "kapitel_ids": []}, {"id": "a", "wochen": 4, "kapitel_ids": [str(w.brueche.id)]}]}
    await db_session.flush()
    r = await absprachen_des_curriculums(db_session, w.m8, LEHRKRAFT)
    k = r["kapitel"][str(w.brueche.id)]
    assert k["eigene"][0]["art"] == "nachher" and k["eigene"][0]["pruefung"]["ergebnis"] == "verletzt"
    assert k["von_aussen"][0]["pruefung"]["ergebnis"] == "verletzt"

    # Ohne Pläne: gleiche Stufe → offen
    m_plan.status = ph_plan.status = "deleted"
    await db_session.flush()
    r = await absprachen_des_curriculums(db_session, w.m8, LEHRKRAFT)
    assert r["kapitel"][str(w.brueche.id)]["eigene"][0]["pruefung"] == {
        "ergebnis": "offen", "grund": "ohne_wochen", "hier": "Kl. 8", "dort": "Kl. 8"}


async def test_absprachen_der_kapitel_auch_ueber_den_nachfolger(db_session, w):
    """Planer (Teil B): Einheiten hängen auch an Kapiteln eines ersetzten Curriculums."""
    from app.context.absprachen import absprachen_der_kapitel

    r = await absprachen_der_kapitel(db_session, {str(w.dichte.id), str(uuid.uuid4())}, LEHRKRAFT)
    assert list(r) == [str(w.dichte.id)] and r[str(w.dichte.id)]["eigene"][0]["art"] == "vorher"
    ph8neu = await w.curriculum(w.ph, "Physik Kl. 8 neu", kopie_von=w.ph8.id)
    await w.kapitel(ph8neu, "Dichte", [w.vorher], kopie_von=w.dichte.id)
    w.ph8.status = w.dichte.status = "archived"
    await db_session.flush()
    r = await absprachen_der_kapitel(db_session, {str(w.dichte.id)}, LEHRKRAFT)
    assert r[str(w.dichte.id)]["eigene"][0]["text"] == "Bruchrechnung zuerst"


async def test_verlaufsplan_zeigt_absprachen_der_kapitel(db_session, w):
    from app.context import verlaufsplan as vp

    w.ph8.metadata_ = {"jahrgangsstufe": "8"}
    plan = ContextNode(id=uuid.uuid4(), category="knowledge", content_type="verlaufsplan", title="Plan 8",
                       status="draft", subject_id=w.ph, min_grade=8, max_grade=8, read_scope="school",
                       write_scope="private", owner_pseudonym="test",
                       metadata_={"schuljahr": vp.aktuelles_schuljahr(), "planungsart": "kapitel",
                                  "abschnitte": [{"id": "a", "wochen": 2, "kapitel_ids": [str(w.dichte.id)]}]})
    db_session.add(plan)
    await db_session.flush()
    v = await vp.voll(db_session, plan, LEHRKRAFT)
    assert v["absprachen"][str(w.dichte.id)]["eigene"][0]["art"] == "vorher"


async def test_curriculum_assistent_liest_absprachen_je_kapitel(db_session, w):
    """Teil C (0.65, F1): `get_curriculum_draft` trägt die Absprachen je Kapitel, mit Nummer."""
    from app.context.curriculum_assistent import entwurf_lesen

    aus = await entwurf_lesen(db_session, LEHRKRAFT, w.m8)
    [k] = aus["kapitel"]
    a = k["absprachen"]
    assert a["eigene"] == [{"nr": 1, "fach": "Physik", "fach_code": "PHAY", "art": "nachher", "text": "",
                            "ziel": {"kapitel": "Dichte", "curriculum": "Physik Kl. 8",
                                     "curriculum_id": str(w.ph8.id), "kapitel_id": str(w.dichte.id)},
                            "beidseitig": True, "text_gegenseite": "Bruchrechnung zuerst"}]
    assert "von_anderen_faechern" not in a          # die beidseitige steht nur einmal
    assert aus["absprachen_an_das_fach"][0]["text"] == "Einheiten gleich"
    # Ohne Absprachen kein Feld
    ph = await entwurf_lesen(db_session, LEHRKRAFT, w.ph8)
    assert "absprachen_an_das_fach" not in ph


async def test_kapitel_eines_fachs_fuer_den_assistenten(db_session, w):
    """Teil C (F3): Ziele im anderen Fach mit Kennung; das eigene Fach ist kein Ziel."""
    from app.context.absprachen import kapitel_eines_fachs

    m5 = await w.curriculum(w.ph, "Physik Kl. 5", (5, 5))
    await w.kapitel(m5, "Magnete")
    r = await kapitel_eines_fachs(db_session, LEHRKRAFT, "phay", w.m, (8, 8))
    assert r["fach_code"] == "PHAY"
    assert [c["titel"] for c in r["curricula"]] == ["Physik Kl. 8", "Physik Kl. 5"]   # eigene Stufe vorn
    assert r["curricula"][0]["kapitel"] == [{"kapitel_id": str(w.dichte.id), "titel": "Dichte"}]
    assert "error" in await kapitel_eines_fachs(db_session, LEHRKRAFT, "MAY", w.m)
    assert "gibt es hier nicht" in (await kapitel_eines_fachs(db_session, LEHRKRAFT, "Gibtsnicht", w.m))["error"]


async def test_querverweise_je_kapitel_fuer_den_assistenten(db_session, w):
    """Teil C (F4): Querverweise des Bildungsplans je Kapitel, mit Fundstelle samt kapitel_id."""
    from app.context.absprachen import querverweise_je_kapitel

    def bp(typ, titel, fach, bp_id):
        return ContextNode(id=uuid.uuid4(), category="knowledge", content_type=typ, title=titel, status="active",
                           subject_id=fach, bp_version="2016.V3", min_grade=7, max_grade=8, read_scope="global",
                           write_scope="private", owner_pseudonym="system",
                           metadata_={"bp_id": bp_id, "kompetenz_nr": titel.split(" ", 1)[0]})
    m_ik = bp("ik_kompetenz", "3.2.1(1) Brüche rechnen", w.m, "BP_AY2_M.V3_IK_7-8_01_00_01")
    ph_ik = bp("ik_kompetenz", "3.2.1(3) Dichte bestimmen", w.ph, "BP_AY2_PH.V3_IK_7-8_01_00_03")
    db_session.add_all([m_ik, ph_ik])
    await db_session.flush()
    m_ls = ContextNode(id=uuid.uuid4(), category="knowledge", content_type="lernsequenz", title="LS Brüche",
                       status="active", owner_pseudonym="system", read_scope="school", write_scope="school",
                       subject_id=w.m, metadata_={"eintraege": [{"ik": [{"node_id": str(m_ik.id), "nr": "3.2.1(1)"}]}]})
    ph_ls = ContextNode(id=uuid.uuid4(), category="knowledge", content_type="lernsequenz", title="LS Dichte",
                        status="active", owner_pseudonym="system", read_scope="school", write_scope="school",
                        subject_id=w.ph, metadata_={"eintraege": []})
    db_session.add_all([m_ls, ph_ls])
    await db_session.flush()
    db_session.add_all([
        ContextEdge(from_node_id=m_ls.id, to_node_id=w.brueche.id, relation="part_of"),
        ContextEdge(from_node_id=ph_ls.id, to_node_id=w.dichte.id, relation="part_of"),
        ContextEdge(from_node_id=m_ik.id, to_node_id=ph_ik.id, relation="related_to"),
        ContextEdge(from_node_id=ph_ls.id, to_node_id=ph_ik.id, relation="references"),
    ])
    await db_session.flush()

    r = await querverweise_je_kapitel(db_session, LEHRKRAFT, w.m8)
    [k] = r["kapitel"]
    assert k["kapitel"] == "Brüche"
    [v] = k["verweise"]
    assert (v["ik"], v["fach_code"], v["nr"]) == ("3.2.1(1)", "PHAY", "3.2.1(3)")
    assert v["behandelt_in"] == [{"curriculum": "Physik Kl. 8", "kapitel": "Dichte", "kapitel_id": str(w.dichte.id)}]


async def test_assistent_absprachen_anlegen_aendern_loeschen_rueckgaengig(db_session, w):
    """Teil C (F2): Absprachen über den Stapel des Curriculum-Assistenten — Vorschau, Schreiben,
    Prüfung wie im Editor, Rückgängig."""
    from app.context.curriculum_assistent import operationen_anwenden, operationen_pruefen
    from app.context.curriculum_verlauf import zuruecknehmen

    w.m8.status = w.brueche.status = "draft"
    await db_session.flush()
    kap = str(w.brueche.id)
    anlegen = [{"op": "absprache_anlegen", "kapitel_id": kap, "fach": "phay", "art": "gleichzeitig",
                "ziel_kapitel_id": str(w.dichte.id), "text": "Messen zusammen"}]
    v = await operationen_pruefen(db_session, w.m8, anlegen)
    assert v["ok"] and not v["geschrieben"]
    assert v["absprachen"] == [{"kapitel": "Brüche", "absprachen": [
        {"nr": 1, "fach_code": "PHAY", "ziel_kapitel": "Dichte", "art": "nachher"},
        {"nr": 2, "fach_code": "PHAY", "ziel_kapitel": "Dichte", "art": "gleichzeitig", "text": "Messen zusammen"}]}]
    assert len((await db_session.get(ContextNode, w.brueche.id)).metadata_["absprachen"]) == 1   # nichts geschrieben

    r = await operationen_anwenden(db_session, LEHRKRAFT, w.m8, anlegen)
    assert r["ok"] and r["geschrieben"]
    await db_session.refresh(w.brueche)
    assert [a["art"] for a in w.brueche.metadata_["absprachen"]] == ["nachher", "gleichzeitig"]
    assert w.brueche.metadata_["absprachen"][1]["kapitel_titel"] == "Dichte"

    r = await operationen_anwenden(db_session, LEHRKRAFT, w.m8, [
        {"op": "absprache_aendern", "kapitel_id": kap, "absprache": 2, "art": "abgestimmt"},
        {"op": "absprache_loeschen", "kapitel_id": kap, "absprache": 1}])
    assert r["ok"], r
    await db_session.refresh(w.brueche)
    assert [(a["art"], a["text"]) for a in w.brueche.metadata_["absprachen"]] == [("abgestimmt", "Messen zusammen")]

    # Fehler wie im Editor: das eigene Fach, Kapitel eines anderen Fachs, fehlende Nummer
    for ops, muster in (
        ([{"op": "absprache_anlegen", "kapitel_id": kap, "fach": "MAY", "art": "abgestimmt", "text": "t"}], "nicht dem eigenen"),
        ([{"op": "absprache_anlegen", "kapitel_id": kap, "fach": "PHAY", "art": "vorher",
           "ziel_kapitel_id": kap}], "gehört nicht zu einem Curriculum von „PHAY“"),
        ([{"op": "absprache_loeschen", "kapitel_id": kap, "absprache": 5}], "gibt es an diesem Kapitel nicht"),
        ([{"op": "absprache_anlegen", "kapitel_id": kap, "fach": "PHAY", "art": "vorher"}], "braucht ein Kapitel"),
    ):
        v = await operationen_pruefen(db_session, w.m8, ops)
        assert not v["ok"] and muster in " ".join(v["fehler"]), (muster, v)

    # Rückgängig: der Stand vor dem letzten Schreiben
    await zuruecknehmen(db_session, w.m8)
    await db_session.flush()
    await db_session.refresh(w.brueche)
    assert [a["art"] for a in w.brueche.metadata_["absprachen"]] == ["nachher", "gleichzeitig"]
