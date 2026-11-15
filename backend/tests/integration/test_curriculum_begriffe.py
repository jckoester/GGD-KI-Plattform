"""Begriffe und Fachmethoden am Eintrag eines Curriculums (0.44, Päckchen AQ, Schritt 2).

Gespeichert wird Text (`metadata.eintraege[].begriffe`, `fachmethoden`); aufgelöst wird im
Lesen und Ändern des Routers für die lesende Person, neben dem Baum (`begriffe`). Hier: das
Zwischenformat kommt im Eintrag an, die Auflösung stimmt, und sie landet nicht im Baum.
"""
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import JwtPayload
from app.context.router import get_curriculum, update_curriculum_meta
from app.context.schemas import (
    CurriculumDraftConfirmed,
    CurriculumDraftEntry,
    CurriculumDraftKapitel,
    CurriculumDraftLernsequenz,
    CurriculumMetaUpdate,
)
from app.context.service import import_curriculum_from_draft, load_curriculum_tree
from app.db.models import ContextNode, NodeAlias, Subject

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]


def _n(s: str) -> str:
    return f"Q{TOKEN}{s}"


def _user(*rollen, sub="lehrkraft-begriffe"):
    return JwtPayload(sub=sub, roles=list(rollen), role=rollen[0], grade=None,
                      exp=9999999999, iat=0, jti=str(uuid.uuid4()))


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


async def _fach(db, name, code, bezug=()):
    f = Subject(slug=f"{name.lower()}-{TOKEN}", name=f"{name} {TOKEN}", fach_code=code, bezugsfaecher=list(bezug))
    db.add(f)
    await db.flush()
    return f


async def _begriff(db, titel, fach, *, aliase=(), **kw):
    lesen = kw.pop("read_scope", "school")
    n = ContextNode(category="concept", content_type="begriff", title=titel, status="active",
                    subject_id=fach.id, read_scope=lesen, write_scope="private" if lesen == "private" else "school",
                    metadata_=kw.pop("metadata_", {}), **kw)
    db.add(n)
    await db.flush()
    db.add_all(NodeAlias(node_id=n.id, alias=a) for a in aliase)
    await db.flush()
    return n


@pytest_asyncio.fixture
async def faecher(db):
    bio = await _fach(db, "Bio", f"B{TOKEN[:4]}".upper())
    chemie = await _fach(db, "Chemie", f"C{TOKEN[:4]}".upper(), bezug=[bio.slug])
    return bio, chemie


async def _curriculum(db, chemie, eintraege: list[CurriculumDraftEntry]):
    fachplan = f"BP_AQ_{TOKEN}"
    db.add(ContextNode(category="knowledge", content_type="fachplan", title="BP Chemie", status="active",
                       owner_pseudonym="system", read_scope="global", write_scope="school",
                       metadata_={"fachplan_id": fachplan}))
    await db.flush()
    draft = CurriculumDraftConfirmed(
        schule="Test", fach_code=chemie.fach_code, fach=chemie.name, schulart="G8", jahrgangsstufe="9",
        fachplan_id=fachplan, bp_version="2016",
        kapitel=[CurriculumDraftKapitel(titel="Redox", reihenfolge=1, lernsequenzen=[
            CurriculumDraftLernsequenz(bp_titel="Sequenz", reihenfolge=1, eintraege=eintraege)])],
    )
    cid, _ = await import_curriculum_from_draft(db, draft, "lehrkraft-begriffe")
    node = await db.get(ContextNode, cid)
    node.subject_id = chemie.id  # vom Fach-Code unabhängig machen
    await db.flush()
    return cid


def _eintraege(tree):
    return [e for k in tree["kapitel"] for ls in k["lernsequenzen"] for e in ls["metadata"]["eintraege"]]


async def test_zwischenformat_kommt_normalisiert_im_eintrag_an(db, faecher):
    _, chemie = faecher
    cid = await _curriculum(db, chemie, [
        CurriculumDraftEntry(konkretisierung="K", begriffe=[
            "  Oxidation ", {"name": "Oxidation", "fassung": "Elektronen"}, "oxidation", "", {"fassung": "x"},
        ], fachmethoden=["Titration", {"name": "Titration", "fassung": "fällt weg"}, "Chromatographie"]),
        CurriculumDraftEntry(konkretisierung="ohne"),
    ])
    erster, zweiter = _eintraege(await load_curriculum_tree(db, cid))
    assert erster["begriffe"] == [{"name": "Oxidation"}, {"name": "Oxidation", "fassung": "Elektronen"}]
    assert erster["fachmethoden"] == [{"name": "Titration"}, {"name": "Chromatographie"}]
    # Leere Felder stehen gar nicht erst im Eintrag.
    assert "begriffe" not in zweiter and "fachmethoden" not in zweiter


async def test_get_loest_auf_neben_dem_baum(db, faecher):
    bio, chemie = faecher
    redox = await _begriff(db, _n("Redoxreaktion"), chemie, aliase=[_n("Redox")])
    zelle = await _begriff(db, _n("Zelle"), bio)
    alt = await _begriff(db, _n("Oxidation"), chemie, metadata_={"fassung": "Sauerstoff"})
    neu = await _begriff(db, _n("Oxidation"), chemie, metadata_={"fassung": "Elektronen"})
    cid = await _curriculum(db, chemie, [
        CurriculumDraftEntry(begriffe=[_n("Redox"), _n("Zelle"), _n("Oxidation"), _n("Fehlt")]),
        CurriculumDraftEntry(begriffe=[{"name": _n("Oxidation"), "fassung": "Elektronen"}, _n("Redox")],
                             fachmethoden=[_n("Redoxreaktion")]),
    ])
    antwort = await get_curriculum(cid, db=db, user=_user("teacher"))
    je_name = {(b["name"], b["fassung"]): b for b in antwort["begriffe"]}
    # Jedes Paar einmal, in der Reihenfolge des ersten Auftretens.
    assert list(je_name) == [(_n("Redox"), None), (_n("Zelle"), None), (_n("Oxidation"), None),
                             (_n("Fehlt"), None), (_n("Oxidation"), "Elektronen")]

    gefunden = je_name[(_n("Redox"), None)]
    assert gefunden["zustand"] == "gefunden"
    assert (gefunden["node_id"], gefunden["titel"], gefunden["bezugsfach"]) == (str(redox.id), redox.title, False)
    bezug = je_name[(_n("Zelle"), None)]
    assert (bezug["node_id"], bezug["fach"], bezug["bezugsfach"]) == (str(zelle.id), bio.name, True)
    mehr = je_name[(_n("Oxidation"), None)]
    assert mehr["zustand"] == "mehrdeutig"
    assert {(k["node_id"], k["fassung"]) for k in mehr["kandidaten"]} == {
        (str(alt.id), "Sauerstoff"), (str(neu.id), "Elektronen")}
    assert je_name[(_n("Oxidation"), "Elektronen")]["node_id"] == str(neu.id)
    assert je_name[(_n("Fehlt"), None)]["zustand"] == "fehlt"

    # Fachmethoden werden nicht aufgelöst (E2), und der Baum bleibt reiner Text.
    assert all(b["name"] != _n("Redoxreaktion") or b["fassung"] for b in antwort["begriffe"])
    for e in _eintraege(antwort):
        assert all(set(b) <= {"name", "fassung"} for b in e.get("begriffe", []))


async def test_aufloesung_gilt_fuer_die_lesende_person(db, faecher):
    _, chemie = faecher
    await _begriff(db, _n("Notiz"), chemie, read_scope="private", owner_pseudonym="lehrkraft-begriffe")
    cid = await _curriculum(db, chemie, [CurriculumDraftEntry(begriffe=[_n("Notiz")])])
    (ich,) = (await get_curriculum(cid, db=db, user=_user("teacher")))["begriffe"]
    (andere,) = (await get_curriculum(cid, db=db, user=_user("teacher", sub="jemand-anderes")))["begriffe"]
    assert (ich["zustand"], andere["zustand"]) == ("gefunden", "fehlt")


async def test_patch_liefert_die_aufloesung_mit(db, faecher):
    _, chemie = faecher
    await _begriff(db, _n("Säure"), chemie)
    cid = await _curriculum(db, chemie, [CurriculumDraftEntry(begriffe=[_n("Säuren")])])
    antwort = await update_curriculum_meta(cid, CurriculumMetaUpdate(title="Neu"), db=db, user=_user("admin", "teacher"))
    (b,) = antwort["begriffe"]
    assert (b["name"], b["zustand"]) == (_n("Säuren"), "gefunden")  # Einzahlform


async def test_curriculum_ohne_begriffe(db, faecher):
    _, chemie = faecher
    cid = await _curriculum(db, chemie, [CurriculumDraftEntry(konkretisierung="K")])
    assert (await get_curriculum(cid, db=db, user=_user("teacher")))["begriffe"] == []


async def test_eine_abfrage_fuer_den_ganzen_baum(db, faecher):
    """Die Auflösung kostet eine Abfrage für die Begriffe und eine für die Fachnamen."""
    from sqlalchemy import event
    from app.context.curriculum_begriffe import begriffe_aufloesen

    _, chemie = faecher
    for i in range(10):
        await _begriff(db, _n(f"Stoff{i}"), chemie)
    cid = await _curriculum(db, chemie, [CurriculumDraftEntry(begriffe=[_n(f"Stoff{j}") for j in range(i, i + 5)])
                                         for i in range(6)])
    tree = await load_curriculum_tree(db, cid)
    abfragen = []
    engine = db.bind.sync_engine

    def zaehle(conn, cursor, statement, *a):
        abfragen.append(statement)

    event.listen(engine, "before_cursor_execute", zaehle)
    try:
        aufl = await begriffe_aufloesen(db, tree, _user("teacher"))
    finally:
        event.remove(engine, "before_cursor_execute", zaehle)
    assert len(aufl) == 10  # Stoff0 … Stoff9, jedes einmal
    assert sum(1 for b in aufl if b["zustand"] == "gefunden") == 10
    # Bezugsfächer, Begriffe, Fachnamen.
    assert len(abfragen) == 3, abfragen


async def test_unbekannte_eintragsschluessel_ueberstehen_die_metadatenpruefung(db, faecher):
    """Schritt 0: `lernsequenz` hat kein Feldschema — `begriffe` geht ohne Migration durch."""
    _, chemie = faecher
    cid = await _curriculum(db, chemie, [CurriculumDraftEntry(begriffe=["A"], fachmethoden=["B"])])
    ls = (await db.execute(sa.select(ContextNode).where(
        ContextNode.content_type == "lernsequenz",
        ContextNode.metadata_["import_key"].astext.like(f"BP_AQ_{TOKEN}%")))).scalar_one()
    from app.context.metadata import validate_node_metadata
    validate_node_metadata("lernsequenz", ls.metadata_)


async def test_yaml_konverter_reicht_die_felder_durch():
    """`backend/scripts/import_curriculum.py` übernimmt die Felder einzeln — ohne Zeile ginge es verloren."""
    import importlib.util
    from pathlib import Path

    pfad = Path(__file__).resolve().parents[2] / "scripts" / "import_curriculum.py"
    spec = importlib.util.spec_from_file_location("_import_curriculum_aq", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    draft = modul.convert_yaml_to_draft({
        "schule": "S", "fach_code": "CH", "schulart": "G", "jahrgangsstufe": "9", "bp_version": "2016",
        "kapitel": [{"titel": "K", "reihenfolge": 1, "lernsequenzen": [{"bp_titel": "L", "reihenfolge": 1, "eintraege": [
            {"konkretisierung": "x", "begriffe": ["Oxidation", {"name": "Reduktion", "fassung": "Elektronen"}],
             "fachmethoden": ["Titration"]},
            {"konkretisierung": "ohne"},
        ]}]}],
    })
    erster, zweiter = draft.kapitel[0].lernsequenzen[0].eintraege
    assert erster.begriffe == ["Oxidation", {"name": "Reduktion", "fassung": "Elektronen"}]
    assert erster.fachmethoden == ["Titration"]
    assert (zweiter.begriffe, zweiter.fachmethoden) == ([], [])


# ── Schritt 3: Editor-Wege ───────────────────────────────────────────────────


async def _lernsequenz(db, cid):
    tree = await load_curriculum_tree(db, cid)
    return await db.get(ContextNode, uuid.UUID(str(tree["kapitel"][0]["lernsequenzen"][0]["id"])))


async def test_speichern_ueber_den_editor_normalisiert(db, faecher):
    """Der Editor schreibt die Einträge als Ganzes über `PATCH /context/nodes/{id}`."""
    from app.context.router import update_node
    from app.context.schemas import ContextNodeUpdate

    _, chemie = faecher
    cid = await _curriculum(db, chemie, [CurriculumDraftEntry(konkretisierung="K")])
    ls = await _lernsequenz(db, cid)
    meta = dict(ls.metadata_)
    meta["eintraege"] = [{**meta["eintraege"][0], "begriffe": [" Redox ", {"name": "redox"}, ""],
                          "fachmethoden": []}]
    await update_node(ls.id, ContextNodeUpdate(metadata=meta), db=db, user=_user("admin", "teacher"))
    (eintrag,) = (await db.get(ContextNode, ls.id)).metadata_["eintraege"]
    assert eintrag["begriffe"] == [{"name": "Redox"}]
    assert "fachmethoden" not in eintrag
    assert eintrag["konkretisierung"] == "K"  # alles andere bleibt


async def test_endpunkt_loest_frisch_getippte_namen_auf(db, faecher):
    from app.context.router import begriffe_im_curriculum_aufloesen
    from app.context.schemas import BegriffeAufloesenAnfrage

    _, chemie = faecher
    redox = await _begriff(db, _n("Redox"), chemie)
    cid = await _curriculum(db, chemie, [CurriculumDraftEntry(konkretisierung="K")])
    anfrage = BegriffeAufloesenAnfrage(namen=[
        {"name": f" {_n('Redox')} "}, {"name": _n("redox")}, {"name": _n("Neu"), "fassung": "X"}, {"name": "  "}])
    aus = await begriffe_im_curriculum_aufloesen(cid, anfrage, db=db, user=_user("teacher"))
    # Jede Schreibweise einzeln — der Editor ordnet die Antwort seinen Chips zu.
    assert [(a["name"], a["fassung"], a["zustand"]) for a in aus] == [
        (_n("Redox"), None, "gefunden"), (_n("redox"), None, "gefunden"), (_n("Neu"), "X", "fehlt")]
    assert aus[0]["node_id"] == str(redox.id)


async def test_endpunkte_pruefen_das_lesen(db, faecher):
    from fastapi import HTTPException
    from app.context.router import begriffe_im_curriculum_aufloesen, fachmethoden_vorschlaege
    from app.context.schemas import BegriffeAufloesenAnfrage

    _, chemie = faecher
    cid = await _curriculum(db, chemie, [CurriculumDraftEntry(konkretisierung="K")])
    node = await db.get(ContextNode, cid)
    node.read_scope, node.write_scope, node.write_scope_group_id = "private", "private", None
    await db.flush()
    fremd = _user("teacher", sub="jemand-anderes")
    with pytest.raises(HTTPException) as e:
        await begriffe_im_curriculum_aufloesen(cid, BegriffeAufloesenAnfrage(namen=[]), db=db, user=fremd)
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        await fachmethoden_vorschlaege(cid, q="", db=db, user=fremd)
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        await fachmethoden_vorschlaege(uuid.uuid4(), q="", db=db, user=fremd)
    assert e.value.status_code == 404


async def test_fachmethoden_aus_den_curricula_des_fachs(db, faecher):
    from app.context.router import fachmethoden_vorschlaege

    bio, chemie = faecher
    cid = await _curriculum(db, chemie, [
        CurriculumDraftEntry(fachmethoden=["Titration", "Chromatographie"]),
        CurriculumDraftEntry(fachmethoden=["titration", "Säure-Base-Titration"]),
    ])
    # Mehrere Lernsequenzen im Fach — mit nur einer fiel eine falsch geklammerte
    # `IN`-Liste nicht auf (Abnahme 15.11.2026: `uuid = record`).
    for i in range(3):
        db.add(ContextNode(category="knowledge", content_type="lernsequenz", title=f"weitere {i}", status="active",
                           subject_id=chemie.id, read_scope="school", write_scope="school",
                           metadata_={"eintraege": [{"fachmethoden": [{"name": "Titration"}]}] if i == 0 else []}))
    await db.flush()
    # Eine fremde Lernsequenz eines anderen Fachs zählt nicht mit.
    db.add(ContextNode(category="knowledge", content_type="lernsequenz", title="fremd", status="active",
                       subject_id=bio.id, read_scope="school", write_scope="school",
                       metadata_={"eintraege": [{"fachmethoden": [{"name": "Mikroskopieren"}]}, "kaputt"]}))
    await db.flush()

    alle = await fachmethoden_vorschlaege(cid, q="", db=db, user=_user("teacher"))
    assert alle == [{"name": "Titration", "anzahl": 3}, {"name": "Chromatographie", "anzahl": 1},
                    {"name": "Säure-Base-Titration", "anzahl": 1}]
    gefiltert = await fachmethoden_vorschlaege(cid, q="tit", db=db, user=_user("teacher"))
    # Wer mit dem Gesuchten beginnt, steht vorn.
    assert [m["name"] for m in gefiltert] == ["Titration", "Säure-Base-Titration"]


# ── Schritt 5: Export ────────────────────────────────────────────────────────


async def test_yaml_rundreise_traegt_begriffe_und_fachmethoden(db, faecher):
    """Export → YAML-Text → Konverter → Import: die Namen kommen an, die Zielinstanz löst sie
    selbst auf (hier dieselbe Datenbank, anderes Band)."""
    import yaml

    from app.context.curriculum_export import build_curriculum_export_dict

    _, chemie = faecher
    gefunden = await _begriff(db, _n("Redox"), chemie)
    cid = await _curriculum(db, chemie, [CurriculumDraftEntry(
        konkretisierung="K", begriffe=[_n("Redox"), {"name": "Oxidation", "fassung": "Elektronen"}],
        fachmethoden=["Titration"]), CurriculumDraftEntry(konkretisierung="leer")])

    daten = await build_curriculum_export_dict(db, await load_curriculum_tree(db, cid))
    erster, zweiter = daten["kapitel"][0]["lernsequenzen"][0]["eintraege"]
    assert erster["begriffe"] == [_n("Redox"), {"name": "Oxidation", "fassung": "Elektronen"}]
    assert erster["fachmethoden"] == ["Titration"]
    assert "begriffe" not in zweiter and "fachmethoden" not in zweiter

    import importlib.util
    from pathlib import Path

    pfad = Path(__file__).resolve().parents[2] / "scripts" / "import_curriculum.py"
    spec = importlib.util.spec_from_file_location("_import_curriculum_aq5", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    text = yaml.safe_dump(daten, allow_unicode=True, sort_keys=False)
    neu = yaml.safe_load(text) | {"jahrgangsstufe": "10"}
    draft = modul.convert_yaml_to_draft(neu)
    cid2, _ = await import_curriculum_from_draft(db, draft, "lehrkraft-begriffe")
    node = await db.get(ContextNode, cid2)
    node.subject_id = chemie.id
    await db.flush()

    e = _eintraege(await load_curriculum_tree(db, cid2))[0]
    assert e["begriffe"] == [{"name": _n("Redox")}, {"name": "Oxidation", "fassung": "Elektronen"}]
    assert e["fachmethoden"] == [{"name": "Titration"}]
    aufl = (await get_curriculum(cid2, db=db, user=_user("teacher")))["begriffe"]
    assert aufl[0]["node_id"] == str(gefunden.id)
