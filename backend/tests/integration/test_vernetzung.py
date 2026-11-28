"""Vernetzung der Fächer (BE, Teil A, Schritt 2). Erfordert TEST_DATABASE_URL.

Die Welt: Mathematik Kl. 7 (V3, beschlossener Plan 2026/27) und Kl. 8 (V2 und V3), Physik Kl. 8
(V2 mit Plan-Entwurf, V3 ohne Plan), Biologie Kl. 8 ohne jeden Bezug. Das laufende Schuljahr der
Tests ist das der Konfiguration (2026/27): Kl. 8 gilt noch V2, im kommenden Jahr V3.
"""
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.auth.jwt import JwtPayload
from app.context import verlaufsplan as vp
from app.context import vernetzung_zeit as vz
from app.context.vernetzung import vernetzung
from app.db.models import ContextEdge, ContextNode

pytestmark = pytest.mark.asyncio

LEHRKRAFT = JwtPayload(sub="be-lk", roles=["teacher"], grade=None, jti="j", iat=0, exp=9999999999)
SCHUELER = JwtPayload(sub="be-s", roles=["student"], grade="8", jti="j", iat=0, exp=9999999999)


async def _fach(db, slug, code):
    return (await db.execute(sa.text(
        "INSERT INTO subjects (slug, name, fach_code) VALUES (:s, :n, :c) "
        "ON CONFLICT (slug) DO UPDATE SET fach_code = EXCLUDED.fach_code, name = EXCLUDED.name RETURNING id"),
        {"s": slug, "n": slug.split("-")[0].title(), "c": code})).scalar_one()


class Welt:
    def __init__(self, db):
        self.db = db

    async def knoten(self, typ, titel, fach=None, *, status="active", meta=None, stufen=(None, None),
                     bp_version="", scope="school"):
        n = ContextNode(id=uuid.uuid4(), category="knowledge", content_type=typ, title=titel, status=status,
                        owner_pseudonym="system", read_scope=scope, write_scope="school", subject_id=fach,
                        min_grade=stufen[0], max_grade=stufen[1], bp_version=bp_version, metadata_=meta or {})
        self.db.add(n)
        await self.db.flush()
        return n

    async def kante(self, von, zu, relation):
        self.db.add(ContextEdge(from_node_id=von.id, to_node_id=zu.id, relation=relation, metadata_={}))
        await self.db.flush()

    async def ik(self, fach, nr, version, stufe, bereich=None):
        n = await self.knoten("ik_kompetenz", f"Kompetenz {nr}", fach, meta={"kompetenz_nr": nr},
                              stufen=(stufe, stufe), bp_version=version)
        if bereich is not None:
            await self.kante(n, bereich, "part_of")
        return n

    async def curriculum(self, fach, titel, stufe, version, status="active", kopie_von=None, ws=None):
        meta = {"bp_version": version}
        if kopie_von:
            meta["kopie_von"] = str(kopie_von.id)
        if ws:
            meta["rahmen"] = {"wochenstunden": {str(stufe): ws}}
        return await self.knoten("curriculum", titel, fach, status=status, meta=meta, stufen=(stufe, stufe))

    async def kapitel(self, cur, titel, nr, kompetenzen=(), absprachen=None, std=None, lp=(), kopie_von=None):
        meta = {"reihenfolge": nr}
        if absprachen:
            meta["absprachen"] = absprachen
        if std:
            meta["std"] = std
        if kopie_von:
            meta["kopie_von"] = str(kopie_von.id)
        k = await self.knoten("kapitel", titel, cur.subject_id, status=cur.status, meta=meta)
        await self.kante(k, cur, "part_of")
        ls = await self.knoten("lernsequenz", f"{titel} 1", cur.subject_id, status=cur.status)
        await self.kante(ls, k, "part_of")
        for z in (*kompetenzen, *lp):
            await self.kante(ls, z, "references")
        return k

    async def plan(self, fach, stufe, abschnitte, status=vp.BESCHLOSSEN, schuljahr="2026/27"):
        return await self.knoten(vp.TYP, f"Plan {stufe}", fach, status=status, stufen=(stufe, stufe),
                                 meta={"schuljahr": schuljahr, "planungsart": "kapitel", "abschnitte": abschnitte})


def _abspr(fach_code, kapitel=None, art="vorher", text=""):
    return {"id": str(uuid.uuid4()), "fach_code": fach_code, "kapitel_id": str(kapitel.id) if kapitel else None,
            "kapitel_titel": kapitel.title if kapitel else None, "art": art, "text": text}


@pytest_asyncio.fixture
async def w(db_session):
    w = Welt(db_session)
    w.m = await _fach(db_session, "mathematik-be", "MBE")
    w.ph = await _fach(db_session, "physik-be", "PHBE")
    w.bio = await _fach(db_session, "biologie-be", "BIOBE")

    # Bildungsplan
    w.m7a = await w.ik(w.m, "3.2.4(1)", "2016.V3", 7)
    w.m7b = await w.ik(w.m, "3.2.1(2)", "2016.V3", 7)
    w.m8alt = await w.ik(w.m, "3.2.2(1)", "2016.V2", 8)
    w.m8neu = await w.ik(w.m, "3.3.2(1)", "2016.V3", 8)
    w.ph_bereich = await w.knoten("leitidee", "3.2.3 Mechanik", w.ph, stufen=(8, 8), bp_version="2016.V2",
                                  meta={"nr": "3.2.3"})
    w.ph8 = await w.ik(w.ph, "3.2.1(4)", "2016.V2", 8)
    w.ph8b = await w.ik(w.ph, "3.2.3(1)", "2016.V2", 8, bereich=w.ph_bereich)
    w.ph8neu = await w.ik(w.ph, "3.2.1(4)", "2016.V3", 8)
    w.bio8 = await w.ik(w.bio, "3.2.1(1)", "2016.V2", 8)
    await w.ik(w.bio, "3.2.1(1)", "2016.V3", 8)
    await w.kante(w.m7a, w.ph8, "related_to")        # Mathematik → Physik, Kompetenz
    await w.kante(w.ph8neu, w.m7a, "related_to")     # Physik V3 → Mathematik (Rückrichtung)
    await w.kante(w.m8neu, w.m7a, "related_to")      # im eigenen Fach, Kl. 8 → Kl. 7
    await w.kante(w.m7a, w.m7b, "related_to")        # im eigenen Fach, benachbart → zählt nicht
    await w.kante(w.m7b, w.ph_bereich, "related_to")  # auf einen Bereich der Physik
    w.bne = await w.knoten("leitperspektive", "Bildung für nachhaltige Entwicklung",
                           meta={"bp_id": "BP2016BW_ALLG_LP_BNE"})
    w.bne3 = await w.knoten("leitperspektive_aspekt", "Aspekt 3", meta={"bp_id": "BNE_03", "aspekt_nr": 3})
    await w.kante(w.bne3, w.bne, "part_of")

    # Curricula
    w.c_m7 = await w.curriculum(w.m, "Mathematik Kl. 7", 7, "2016.V3")
    w.zuordnungen = await w.kapitel(w.c_m7, "Zuordnungen", 1, [w.m7a], lp=[w.bne3])
    w.terme = await w.kapitel(w.c_m7, "Terme", 2, [w.m7b])
    w.c_m8alt = await w.curriculum(w.m, "Mathematik Kl. 8 alt", 8, "2016.V2")
    w.funktionen_alt = await w.kapitel(w.c_m8alt, "Funktionen (alt)", 1, [w.m8alt])
    w.c_m8neu = await w.curriculum(w.m, "Mathematik Kl. 8 neu", 8, "2016.V3")
    w.funktionen = await w.kapitel(w.c_m8neu, "Lineare Funktionen", 1, [w.m8neu])
    w.c_ph8 = await w.curriculum(w.ph, "Physik Kl. 8", 8, "2016.V2", ws=2)
    w.dichte = await w.kapitel(w.c_ph8, "Dichte", 1, [w.ph8], std=12,
                               absprachen=[_abspr("MBE", w.zuordnungen, "vorher", "Proportionalität zuerst")])
    w.kraft = await w.kapitel(w.c_ph8, "Kraft", 2, [w.ph8b], std=20)
    w.c_ph8neu = await w.curriculum(w.ph, "Physik Kl. 8 neu", 8, "2016.V3")
    w.dichte_neu = await w.kapitel(w.c_ph8neu, "Dichte (neu)", 1, [w.ph8neu])
    w.c_bio8 = await w.curriculum(w.bio, "Biologie Kl. 8", 8, "2016.V2")
    await w.kapitel(w.c_bio8, "Zelle", 1, [w.bio8])

    # Pläne 2026/27
    await w.plan(w.m, 7, [{"wochen": 4, "kapitel_ids": [str(w.zuordnungen.id)]},
                          {"wochen": 3, "kapitel_ids": [str(w.terme.id)]}])
    await w.plan(w.ph, 8, [{"wochen": 2, "kapitel_ids": [str(w.dichte.id)]},
                           {"wochen": 5, "kapitel_ids": [str(w.kraft.id)]}], status=vp.ENTWURF)
    return w


def _kap(r, titel):
    return next(k for k in r["kapitel"] if k["titel"] == titel)


def _bezug(r, a, b, typ=None):
    ids = {str(a.id), str(b.id)}
    return [x for x in r["bezuege"] if {x["a"], x["b"]} == ids and (typ is None or x["typ"] == typ)]


async def test_laufendes_jahr_mit_plan_fassung_und_bezuegen(db_session, w):
    r = await vernetzung(db_session, LEHRKRAFT, w.m)
    assert [(s["stufe"], s["schuljahr"], s["fassung"]) for s in r["stufen"]] == [
        (7, "2026/27", "2016.V3"), (8, "2026/27", "2016.V2")]
    s8 = r["stufen"][1]
    assert [c["titel"] for c in s8["curricula"]] == ["Mathematik Kl. 8 alt"]   # nicht beide übereinander
    assert s8["kalender"] and len(s8["kalenderwochen"]) == s8["wochen"]

    # Lage: Plan in Kl. 7, Plan-Entwurf der Physik in Kl. 8
    assert _kap(r, "Zuordnungen")["lage"] == [{"stufe": 7, "von_woche": 1, "bis_woche": 4, "quelle": "plan"}]
    assert _kap(r, "Kraft")["lage"] == [{"stufe": 8, "von_woche": 3, "bis_woche": 7, "quelle": "entwurf"}]
    # ohne Plan geschätzt; die V3-Kapitel des kommenden Jahres fehlen
    assert _kap(r, "Funktionen (alt)")["lage"][0]["quelle"] == "geschaetzt"
    titel = {k["titel"] for k in r["kapitel"]}
    assert "Lineare Funktionen" not in titel and "Dichte (neu)" not in titel

    # Bezüge: Absprache mit Prüfung, Kompetenz, Bereich; benachbart zählt nicht
    [abspr] = _bezug(r, w.dichte, w.zuordnungen, "absprache")
    assert abspr["texte"] == ["Proportionalität zuerst"] and not abspr["beidseitig"]
    # Mathematik Kl. 7 liegt vor Physik Kl. 8 — eingehalten, auch ohne gleiche Stufe
    assert abspr["pruefung"]["ergebnis"] == "eingehalten"
    [k] = _bezug(r, w.zuordnungen, w.dichte, "kompetenz")
    hier, dort = ("3.2.4(1)", "3.2.1(4)") if k["a"] == str(w.zuordnungen.id) else ("3.2.1(4)", "3.2.4(1)")
    assert not k["eigenes_fach"] and k["beispiele"] == [f"{hier} ↔ {dort}"]
    [b] = _bezug(r, w.terme, w.kraft)
    assert b["typ"] == "bereich" and b["beispiele"] in (["3.2.1(2) ↔ 3.2.3"], ["3.2.3 ↔ 3.2.1(2)"])
    assert not _bezug(r, w.zuordnungen, w.terme)

    # Spuren: Physik ja, Biologie (ohne Bezug) nicht
    assert [(f["code"], f["absprachen"], f["kompetenz"], f["bereich"], f["nur_bereich"]) for f in r["faecher"]] == [
        ("PHBE", 1, 1, 1, False)]
    assert "Zelle" not in titel

    # Leitperspektive am Kapitel der Mitte, zum Kürzel der Leitperspektive gefasst
    assert r["leitlinien"][str(w.zuordnungen.id)] == [
        {"art": "lp", "kuerzel": "BNE", "titel": "Bildung für nachhaltige Entwicklung", "aspekte": ["BNE_03"]}]


async def test_kommendes_jahr_und_weg_einer_klasse(db_session, w):
    # Kommendes Schuljahr: Kl. 8 in V3, ohne Kalender, ohne Pläne
    r = await vernetzung(db_session, LEHRKRAFT, w.m, schuljahr="2027/28")
    s8 = next(s for s in r["stufen"] if s["stufe"] == 8)
    assert (s8["fassung"], s8["kalender"], s8["kalenderwochen"]) == ("2016.V3", False, None)
    assert [c["titel"] for c in s8["curricula"]] == ["Mathematik Kl. 8 neu"]
    assert _kap(r, "Lineare Funktionen")["lage"][0]["quelle"] == "geschaetzt"
    # im eigenen Fach über die Stufe: Kl. 8 neu baut auf Kl. 7 auf
    [eigen] = _bezug(r, w.funktionen, w.zuordnungen)
    assert eigen["eigenes_fach"] and eigen["typ"] == "kompetenz"
    # Physik V3 verweist zurück auf Mathematik
    assert _bezug(r, w.zuordnungen, w.dichte_neu, "kompetenz")

    # Weg der Klasse, die 2026/27 in Kl. 7 ist: Kl. 8 im Jahr 2027/28
    r = await vernetzung(db_session, LEHRKRAFT, w.m, modus=vz.WEG, bezugsstufe=7)
    assert [(s["stufe"], s["schuljahr"], s["fassung"]) for s in r["stufen"]] == [
        (7, "2026/27", "2016.V3"), (8, "2027/28", "2016.V3")]
    assert _kap(r, "Zuordnungen")["lage"][0]["quelle"] == "plan"
    assert r["zeitraum"]["bezugsstufe"] == 7


async def test_entwurf_ersetzt_original_und_leserecht(db_session, w):
    kopie = await w.curriculum(w.ph, "Physik Kl. 8 (Entwurf)", 8, "2016.V2", status="draft", kopie_von=w.c_ph8)
    dichte_e = await w.kapitel(kopie, "Dichte", 1, [w.ph8], kopie_von=w.dichte,
                               absprachen=[_abspr("MBE", w.zuordnungen, "vorher", "neu formuliert")])
    r = await vernetzung(db_session, LEHRKRAFT, w.m, entwuerfe=True)
    ph = [k for k in r["kapitel"] if k["fach_id"] == w.ph]
    assert [k["id"] for k in ph] == [str(dichte_e.id)]
    # der Plan nennt das Original — der Entwurf übernimmt seine Lage
    assert ph[0]["lage"][0]["quelle"] == "entwurf"
    [abspr] = _bezug(r, dichte_e, w.zuordnungen, "absprache")
    assert abspr["texte"] == ["neu formuliert"]

    # Ohne Leserecht für Entwürfe gilt der veröffentlichte Stand
    r = await vernetzung(db_session, SCHUELER, w.m, entwuerfe=True)
    assert not r["zeitraum"]["entwuerfe"]
    assert str(w.dichte.id) in {k["id"] for k in r["kapitel"]}


async def test_beidseitige_absprache_und_fach_absprache(db_session, w):
    w.zuordnungen.metadata_ = {**w.zuordnungen.metadata_, "absprachen": [
        _abspr("PHBE", w.dichte, "nachher", "Physik danach"), _abspr("BIOBE", art="abgestimmt", text="Diagramme")]}
    await db_session.flush()
    r = await vernetzung(db_session, LEHRKRAFT, w.m)
    [abspr] = _bezug(r, w.dichte, w.zuordnungen, "absprache")
    assert abspr["beidseitig"] and sorted(abspr["texte"]) == ["Physik danach", "Proportionalität zuerst"]
    [fa] = r["fach_absprachen"]
    assert (fa["kapitel"], fa["fach_code"], fa["text"]) == (str(w.zuordnungen.id), "BIOBE", "Diagramme")
    # die Absprache an das ganze Fach macht Biologie zur Spur
    assert [f["code"] for f in r["faecher"]] == ["PHBE", "BIOBE"]


async def test_fach_ohne_curricula_und_unbekanntes_fach(db_session, w):
    leer = await _fach(db_session, "musik-be", "MUBE")
    r = await vernetzung(db_session, LEHRKRAFT, leer)
    assert r["stufen"] == [] and r["kapitel"] == []
    with pytest.raises(LookupError):
        await vernetzung(db_session, LEHRKRAFT, 987654)


# ── Endpunkt (Schritt 3) ───────────────────────────────────────────────────────

def _client(db, user):
    import httpx
    from fastapi import FastAPI

    from app.auth.dependencies import get_current_user
    from app.context.vernetzung_router import router
    from app.db.session import get_db

    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_endpunkt_fach_zeitraum_und_rechte(db_session, w):
    async with _client(db_session, LEHRKRAFT) as c:
        r = await c.get("/context/vernetzung", params={"fach": "mbe"})
        assert r.status_code == 200
        assert r.json()["fach"]["code"] == "MBE" and [f["code"] for f in r.json()["faecher"]] == ["PHBE"]
        r = await c.get("/context/vernetzung", params={"fach": str(w.m), "weg": 7})
        assert [s["schuljahr"] for s in r.json()["stufen"]] == ["2026/27", "2027/28"]
        r = await c.get("/context/vernetzung", params={"fach": "MBE", "schuljahr": "2027/28"})
        assert r.json()["stufen"][1]["fassung"] == "2016.V3"
        for params, status in (({"fach": "MBE", "schuljahr": "2027/28", "weg": 7}, 422),
                               ({"fach": "MBE", "schuljahr": "2027"}, 422),
                               ({"fach": "XYZBE"}, 404), ({"fach": "987654"}, 404), ({}, 422)):
            assert (await c.get("/context/vernetzung", params=params)).status_code == status, params
    async with _client(db_session, SCHUELER) as c:
        assert (await c.get("/context/vernetzung", params={"fach": "MBE"})).status_code == 403


# ── Matrix (Teil B, Schritt 10) ───────────────────────────────────────────────

async def test_matrix_je_stufe(db_session, w):
    from app.context.vernetzung import matrix

    await w.kante(w.m8alt, w.ph8b, "related_to")                       # Querverweis M ↔ PH in Kl. 8
    w.kraft.metadata_ = {**w.kraft.metadata_, "absprachen": [_abspr("MBE", w.funktionen_alt, "vorher", "x")]}
    w.funktionen_alt.metadata_ = {**w.funktionen_alt.metadata_,
                                  "absprachen": [_abspr("BIOBE", art="abgestimmt", text="Diagramme")]}
    await db_session.flush()
    r = await matrix(db_session, LEHRKRAFT, 8)
    codes = {f["id"]: f["code"] for f in r["faecher"]}
    assert set(codes.values()) == {"MBE", "PHBE", "BIOBE"} and r["schuljahr"] == "2026/27"
    assert {f["code"]: f["fassung"] for f in r["faecher"]}["MBE"] == "2016.V2"
    zelle = {frozenset((codes[z["a"]], codes[z["b"]])): z for z in r["zellen"]}
    mp = zelle[frozenset(("MBE", "PHBE"))]
    assert (mp["kompetenz"], mp["absprachen"], mp["verletzt"]) == (1, 1, 0)   # geschätzte Lage beweist nichts
    assert zelle[frozenset(("MBE", "BIOBE"))]["ganzes_fach"] == 1
    # Kl. 7 (Zuordnungen) gehört nicht zur Stufe 8: der Bezug Zuordnungen ↔ Dichte zählt hier nicht
    assert mp["kompetenz"] == 1

    # Kommendes Jahr: Kl. 8 in V3 — andere Curricula, andere Bezüge
    r = await matrix(db_session, LEHRKRAFT, 8, schuljahr="2027/28")
    assert {f["code"]: f["fassung"] for f in r["faecher"]}["MBE"] == "2016.V3"
    assert all(z["absprachen"] == 0 for z in r["zellen"])


async def test_matrix_endpunkt(db_session, w):
    async with _client(db_session, LEHRKRAFT) as c:
        r = await c.get("/context/vernetzung/matrix", params={"stufe": 8})
        assert r.status_code == 200 and r.json()["stufe"] == 8
        assert (await c.get("/context/vernetzung/matrix", params={"stufe": 8, "schuljahr": "2027"})).status_code == 422
        assert (await c.get("/context/vernetzung/matrix")).status_code == 422
    async with _client(db_session, SCHUELER) as c:
        assert (await c.get("/context/vernetzung/matrix", params={"stufe": 8})).status_code == 403
