"""Querverweise des Bildungsplans in ein anderes Fach (Päckchen AY Teil 1, Schritt 2).
Erfordert TEST_DATABASE_URL."""
import uuid

import pytest
import pytest_asyncio

from app.context.querverweise import querverweise
from app.db.models import ContextEdge, ContextNode, Subject

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]


def _bp(typ, titel, fach, bp_id, status="active", bp_version="2016.V3", min_grade=7, max_grade=8, **meta):
    nr = titel.split(" ", 1)[0]
    meta = {"bp_id": bp_id, ("nr" if typ == "leitidee" else "kompetenz_nr"): nr, **meta}
    return ContextNode(category="knowledge", content_type=typ, title=titel, status=status,
                       subject_id=fach.id, bp_version=bp_version, min_grade=min_grade,
                       max_grade=max_grade, read_scope="global", write_scope="private",
                       owner_pseudonym="system", metadata_=meta)


def _kante(von, zu):
    return ContextEdge(from_node_id=von.id, to_node_id=zu.id, relation="related_to")


@pytest_asyncio.fixture
async def welt(db_session):
    db = db_session
    ch = Subject(slug=f"ch-{TOKEN}", name=f"Chemie {TOKEN}", fach_code=f"C{TOKEN[:3]}".upper(),
                 color="#16a34a", icon="flask-conical", sort_order=2)
    ph = Subject(slug=f"ph-{TOKEN}", name=f"Physik {TOKEN}", fach_code=f"P{TOKEN[:3]}".upper(),
                 color="#2563eb", icon="atom", sort_order=1)
    ma = Subject(slug=f"ma-{TOKEN}", name=f"Mathe {TOKEN}", fach_code=f"M{TOKEN[:3]}".upper(), sort_order=0)
    db.add_all([ch, ph, ma])
    await db.flush()

    w = {"ch": ch, "ph": ph, "ma": ma}
    # Quelle: eine Chemie-Kompetenz, dazu eine zweite derselben Chemie (gleiches Fach)
    w["quelle"] = _bp("ik_kompetenz", "3.2.1(4) Dichte bestimmen", ch, f"BP_{TOKEN}_CH.V3_IK_7-8_01_00_04")
    w["gleiches_fach"] = _bp("ik_kompetenz", "3.2.2(1) Atome", ch, f"BP_{TOKEN}_CH.V3_IK_7-8_02_00_01")
    # Ziele in Physik: Kompetenz (aktiv), Bereich (aktiv), künftig
    w["ph_ik"] = _bp("ik_kompetenz", "3.2.1(3) Masse und Volumen", ph, f"BP_{TOKEN}_PH.V3_IK_7-8_01_00_03")
    w["ph_bereich"] = _bp("leitidee", "3.4.3 Schwingungen", ph, f"BP_{TOKEN}_PH.V3_IK_11-12-BF_03",
                          min_grade=None, max_grade=None)
    w["ph_kuenftig"] = _bp("ik_kompetenz", "3.3.1(2) Druck", ph, f"BP_{TOKEN}_PH.V4_IK_9-10_01_00_02",
                           status="upcoming", bp_version="2016.V9", min_grade=9, max_grade=10)
    # Archiviertes Mathe-Ziel mit aktiver Nachfolge-Fassung im selben Band …
    w["ma_alt"] = _bp("ik_kompetenz", "3.2.4(2) Proportionalität", ma, f"BP_{TOKEN}_M_IK_7-8_04_00_02",
                      status="archived", bp_version="2016", min_grade=None, max_grade=None)
    w["ma_neu"] = _bp("ik_kompetenz", "3.2.4(2) Proportionale Zuordnungen", ma,
                      f"BP_{TOKEN}_M.V3_IK_7-8_04_00_02")
    # … und dieselbe Nummer aktiv in einem anderen Band: darf nicht gewählt werden
    w["ma_anderes_band"] = _bp("ik_kompetenz", "3.2.4(2) Etwas ganz anderes", ma,
                               f"BP_{TOKEN}_M.V3_IK_9-10_04_00_02", min_grade=9, max_grade=10)
    # Archiviertes Ziel, dessen Nummer nur in einem anderen Band aktiv ist: fällt weg
    w["ma_alt2"] = _bp("ik_kompetenz", "3.2.5(1) Terme", ma, f"BP_{TOKEN}_M_IK_7-8_05_00_01",
                       status="archived", bp_version="2016", min_grade=None, max_grade=None)
    w["ma_fremdband"] = _bp("ik_kompetenz", "3.2.5(1) Wahrscheinlichkeit", ma,
                            f"BP_{TOKEN}_M.V3_IK_9-10_05_00_01", min_grade=9, max_grade=10)
    # Archiviertes Ziel ohne Nachfolge: fällt weg
    w["ma_ohne"] = _bp("leitidee", "3.9.9 Verschwunden", ma, f"BP_{TOKEN}_M_IK_7-8_09",
                       status="archived", bp_version="2016")
    db.add_all([v for k, v in w.items() if isinstance(v, ContextNode)])
    await db.flush()
    db.add_all([
        _kante(w["quelle"], w["ph_ik"]),             # hin
        _kante(w["ph_bereich"], w["quelle"]),        # her: Physik verweist auf Chemie
        _kante(w["quelle"], w["ph_kuenftig"]),
        _kante(w["quelle"], w["ma_alt"]),
        _kante(w["quelle"], w["ma_ohne"]),
        _kante(w["quelle"], w["ma_alt2"]),
        _kante(w["quelle"], w["gleiches_fach"]),     # kein Querverweis: gleiches Fach
        _kante(w["ph_ik"], w["quelle"]),             # gegenseitig: nur einmal zählen
    ])
    await db.flush()
    return w


async def test_beide_richtungen_umlenkung_und_reihenfolge(db_session, welt):
    aus = await querverweise(db_session, [welt["quelle"].id])
    liste = aus[str(welt["quelle"].id)]
    # Sortiert nach Fach (sort_order: Mathe, Physik), dann Stufe, dann Nummer
    assert [(e["fach"], e["nr"]) for e in liste] == [
        (welt["ma"].name, "3.2.4(2)"),
        (welt["ph"].name, "3.2.1(3)"),
        (welt["ph"].name, "3.3.1(2)"),
        (welt["ph"].name, "3.4.3"),
    ]
    ma = liste[0]
    assert ma["ziel_id"] == str(welt["ma_neu"].id), "archiviert → aktive Fassung im selben Band"
    assert ma["titel"] == "Proportionale Zuordnungen"


async def test_bereich_bleibt_bereich_mit_stufen_aus_dem_band(db_session, welt):
    liste = (await querverweise(db_session, [welt["quelle"].id]))[str(welt["quelle"].id)]
    bereich = next(e for e in liste if e["typ"] == "bereich")
    assert bereich["titel"] == "Schwingungen"
    assert (bereich["min_grade"], bereich["max_grade"]) == (11, 12)
    assert bereich["fach_code"] == welt["ph"].fach_code
    assert (bereich["color"], bereich["icon"]) == ("#2563eb", "atom")


async def test_kuenftiges_ziel_gekennzeichnet(db_session, welt):
    liste = (await querverweise(db_session, [welt["quelle"].id]))[str(welt["quelle"].id)]
    kuenftig = next(e for e in liste if e["nr"] == "3.3.1(2)")
    assert kuenftig["status"] == "upcoming"
    # Fassung steht nicht im Fahrplan → kein Jahr, aber die Kennzeichnung bleibt
    assert kuenftig["ab_schuljahr"] is None


async def test_ohne_nachfolge_und_gleiches_fach_fallen_weg(db_session, welt):
    liste = (await querverweise(db_session, [welt["quelle"].id]))[str(welt["quelle"].id)]
    ziele = {e["ziel_id"] for e in liste}
    assert str(welt["gleiches_fach"].id) not in ziele
    assert str(welt["ma_anderes_band"].id) not in ziele
    assert not any(e["nr"] == "3.9.9" for e in liste)
    assert not any(e["nr"] == "3.2.5(1)" for e in liste), "anderes Band ist keine Nachfolge"


async def test_gegenrichtung_und_leere_eingaben(db_session, welt):
    # Die Physik-Kompetenz sieht die Chemie-Quelle (sie verweist hin, und die Quelle zurück)
    aus = await querverweise(db_session, [welt["ph_ik"].id])
    assert [e["ziel_id"] for e in aus[str(welt["ph_ik"].id)]] == [str(welt["quelle"].id)]
    # Ohne Querverweis (nur eine Kante ins eigene Fach): fehlt in der Rückgabe
    assert str(welt["gleiches_fach"].id) not in await querverweise(db_session, [welt["gleiches_fach"].id])
    assert await querverweise(db_session, []) == {}



# ── Schritt 3: Endpunkt POST /context/querverweise ─────────────────────────────

def _client(db, user):
    import httpx
    from fastapi import FastAPI

    from app.auth.dependencies import get_current_user
    from app.context.router import router
    from app.db.session import get_db

    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def _person(*rollen):
    from app.auth.jwt import JwtPayload

    return JwtPayload(sub=f"qv-{TOKEN}", roles=list(rollen), grade="8" if "student" in rollen else None,
                      jti="j", iat=0, exp=9999999999)


async def test_endpunkt_liefert_je_kompetenz_auch_fuer_schuelerinnen(db_session, welt):
    async with _client(db_session, _person("student")) as c:
        r = await c.post("/context/querverweise", json={"kompetenz_ids": [
            str(welt["quelle"].id), str(welt["gleiches_fach"].id)]})
    assert r.status_code == 200
    aus = r.json()
    assert set(aus) == {str(welt["quelle"].id)}
    assert {e["typ"] for e in aus[str(welt["quelle"].id)]} == {"ik", "bereich"}
    assert aus[str(welt["quelle"].id)][0]["fach_slug"] == welt["ma"].slug


async def test_endpunkt_uebergeht_knoten_ausserhalb_des_bildungsplans(db_session, welt):
    """Eine private Notiz mit Kante auf eine Kompetenz verrät über diesen Weg nichts."""
    notiz = ContextNode(category="knowledge", content_type="note", title=f"Notiz {TOKEN}",
                        read_scope="private", write_scope="private", owner_pseudonym="jemand",
                        subject_id=welt["ma"].id)
    db_session.add(notiz)
    await db_session.flush()
    db_session.add(_kante(notiz, welt["quelle"]))
    await db_session.flush()
    async with _client(db_session, _person("teacher")) as c:
        r = await c.post("/context/querverweise", json={"kompetenz_ids": [str(notiz.id)]})
        r2 = await c.post("/context/querverweise", json={"kompetenz_ids": [str(welt["quelle"].id)]})
    assert r.status_code == 200 and r.json() == {}
    assert str(notiz.id) not in {e["ziel_id"] for e in r2.json()[str(welt["quelle"].id)]}


async def test_endpunkt_begrenzt_die_liste(db_session, welt):
    async with _client(db_session, _person("teacher")) as c:
        r = await c.post("/context/querverweise",
                         json={"kompetenz_ids": [str(uuid.uuid4()) for _ in range(3001)]})
        leer = await c.post("/context/querverweise", json={"kompetenz_ids": []})
    assert r.status_code == 422
    assert leer.status_code == 200 and leer.json() == {}


# ── Schritt 5: Fundstellen im anderen Fach ─────────────────────────────────────

def _teil(typ, titel, fach, status, **kw):
    return ContextNode(category="knowledge", content_type=typ, title=titel, status=status,
                       subject_id=fach.id, read_scope="school", write_scope="school",
                       owner_pseudonym="system", **kw)


async def _curriculum(db, fach, titel, status, verknuepft):
    """Curriculum → Kapitel → Lernsequenz, die Lernsequenz verweist (`references`) auf `verknuepft`."""
    cur = _teil("curriculum", titel, fach, status, min_grade=7, max_grade=8, metadata_={"bp_version": "2016.V3"})
    kap = _teil("kapitel", f"Kapitel {titel}", fach, status, metadata_={"reihenfolge": 1})
    ls = _teil("lernsequenz", f"LS {titel}", fach, status)
    db.add_all([cur, kap, ls])
    await db.flush()
    db.add_all([ContextEdge(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"),
                ContextEdge(from_node_id=ls.id, to_node_id=kap.id, relation="part_of")]
               + [ContextEdge(from_node_id=ls.id, to_node_id=z.id, relation="references") for z in verknuepft])
    await db.flush()
    return cur


@pytest_asyncio.fixture
async def mit_curricula(db_session, welt):
    db = db_session
    # Eine Kompetenz im Physik-Bereich „Schwingungen“, über einen Unterbereich
    unterbereich = _bp("leitidee", "3.4.3.1 Pendel", welt["ph"], f"BP_{TOKEN}_PH.V3_IK_11-12-BF_03_01",
                       min_grade=11, max_grade=12)
    pendel = _bp("ik_kompetenz", "3.4.3.1(2) Fadenpendel", welt["ph"], f"BP_{TOKEN}_PH.V3_IK_11-12-BF_03_01_02",
                 min_grade=11, max_grade=12)
    db.add_all([unterbereich, pendel])
    await db.flush()
    db.add_all([ContextEdge(from_node_id=unterbereich.id, to_node_id=welt["ph_bereich"].id, relation="part_of"),
                ContextEdge(from_node_id=pendel.id, to_node_id=unterbereich.id, relation="part_of")])
    await db.flush()
    welt["ph_veroeffentlicht"] = await _curriculum(db, welt["ph"], f"PH 7/8 {TOKEN}", "active", [welt["ph_ik"]])
    welt["ph_entwurf"] = await _curriculum(db, welt["ph"], f"PH Kursstufe {TOKEN}", "draft", [pendel])
    # Ein Chemie-Curriculum, das die Physik-Kompetenz (etwa über die Hinweise) verknüpft: keine Behandlung durch Physik
    welt["ch_fremd"] = await _curriculum(db, welt["ch"], f"CH 7/8 {TOKEN}", "active", [welt["ph_ik"]])
    return welt


def _fund(liste, nr):
    return {(f["curriculum"], f["status"]) for f in next(e for e in liste if e["nr"] == nr)["fundstellen"]}


async def test_fundstellen_fuer_lehrkraft_mit_entwurf_und_bereich(db_session, mit_curricula):
    w = mit_curricula
    liste = (await querverweise(db_session, [w["quelle"].id], _person("teacher")))[str(w["quelle"].id)]
    assert _fund(liste, "3.2.1(3)") == {(w["ph_veroeffentlicht"].title, "active")}, "nur das Zielfach zählt"
    assert _fund(liste, "3.4.3") == {(w["ph_entwurf"].title, "draft")}, "Bereich: über seine Kompetenzen"
    assert _fund(liste, "3.3.1(2)") == set()


async def test_fundstellen_ohne_entwuerfe_fuer_schuelerinnen_und_mit_filter(db_session, mit_curricula):
    w = mit_curricula
    for person, filter_ in ((_person("student"), False), (_person("teacher"), True)):
        liste = (await querverweise(db_session, [w["quelle"].id], person,
                                    nur_veroeffentlicht=filter_))[str(w["quelle"].id)]
        assert _fund(liste, "3.4.3") == set()
        assert _fund(liste, "3.2.1(3)") == {(w["ph_veroeffentlicht"].title, "active")}


async def test_ohne_person_keine_fundstellen(db_session, mit_curricula):
    liste = (await querverweise(db_session, [mit_curricula["quelle"].id]))[str(mit_curricula["quelle"].id)]
    assert all("fundstellen" not in e for e in liste)


async def test_endpunkt_liefert_fundstellen(db_session, mit_curricula):
    w = mit_curricula
    async with _client(db_session, _person("teacher")) as c:
        r = await c.post("/context/querverweise", json={"kompetenz_ids": [str(w["quelle"].id)],
                                                        "nur_veroeffentlicht": True})
    assert r.status_code == 200
    bereich = next(e for e in r.json()[str(w["quelle"].id)] if e["typ"] == "bereich")
    assert bereich["fundstellen"] == []
    ik = next(e for e in r.json()[str(w["quelle"].id)] if e["nr"] == "3.2.1(3)")
    assert [f["curriculum"] for f in ik["fundstellen"]] == [w["ph_veroeffentlicht"].title]
