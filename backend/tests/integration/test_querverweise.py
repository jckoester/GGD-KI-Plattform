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

