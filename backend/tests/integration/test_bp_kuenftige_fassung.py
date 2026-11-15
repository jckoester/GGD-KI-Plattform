"""Kommende Bildungsplan-Fassung (`status = 'upcoming'`, 0.46, Päckchen AP Teil B, F10).

Eine Fassung, die laut Fahrplan erst später gilt, legt der Import als `upcoming` ab statt als
`archived`. Curricula lassen sich dafür schon schreiben — Anlegen, Auswahl der Kompetenzen,
Kanten, Abdeckung, Export und Import lesen sie mit —, Suche und Chat lassen sie aus. Gilt sie,
macht der nächste Import sie wieder aktiv.
"""
import importlib.util
import sys
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest
import pytest_asyncio

from app.context.curriculum_abdeckung import abdeckung
from app.context.router import (
    create_curriculum_node,
    create_edge,
    get_fachplan_by_subject,
    get_node,
    list_nodes,
)
from app.context.schemas import ContextEdgeCreate, CurriculumCreate
from app.context.service import load_curriculum_tree, resolve_ik_node
from app.auth.jwt import JwtPayload
from app.db.models import ContextEdge, ContextNode, Group, GroupMembership, Subject

TOKEN = uuid.uuid4().hex[:6]
CODE = f"K{TOKEN[:4]}".upper()
MITGLIED = f"mitglied-{TOKEN}"

FAHRPLAN = {"bildungsplan_default": {"bp_basis": "BP2016BW", "editionen": [
    {"suffix": ""},
    {"suffix": ".V2", "ab_schuljahr": "2016/17", "einstieg_stufen": [5, 12]},
    {"suffix": ".V3", "ab_schuljahr": "2026/27", "einstieg_stufen": [5, 7], "wachstum": "nach_oben"},
]}}


def _user(sub, *rollen):
    return JwtPayload(sub=sub, roles=list(rollen), role=rollen[0], grade=None,
                      exp=9999999999, iat=0, jti=str(uuid.uuid4()))


LEHRKRAFT = _user(MITGLIED, "teacher")


# ── Import ───────────────────────────────────────────────────────────────────


def _import_modul():
    pfad = Path(__file__).parents[3] / "scripts" / "import_bildungsplan.py"
    spec = importlib.util.spec_from_file_location("scripts.import_bildungsplan", pfad)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["scripts.import_bildungsplan"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def pg(db_url, run_migrations):
    """Eigene Verbindung wie der Import (psycopg2, mit Commit) — räumt ihr Fach danach ab."""
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    psycopg2.extras.register_uuid(conn_or_curs=conn)  # wie `run_import`
    cur = conn.cursor()
    cur.execute("INSERT INTO subjects (slug, name, fach_code) VALUES (%s, %s, %s) RETURNING id",
                (f"imp-{TOKEN}", f"Import {TOKEN}", CODE))
    sid = cur.fetchone()[0]

    def knoten(typ, bp, nr, stufe=8):
        suffix = bp[4:]  # "2016.V3" → ".V3"
        cur.execute(
            """INSERT INTO context_nodes (category, content_type, title, status, bp_version, metadata,
                   subject_id, min_grade, max_grade, read_scope, write_scope, owner_pseudonym)
               VALUES ('knowledge', %s, %s, 'active', %s, %s, %s, %s, %s, 'global', 'global', 'system')
               RETURNING id""",
            (typ, f"{nr} {bp}", bp,
             f'{{"bp_version": "{bp}", "bp_id": "BP2016BW_ALLG_GYM_{CODE}{suffix}_{typ}_{nr}"}}',
             sid, None if typ == "fachplan" else stufe, None if typ == "fachplan" else stufe + 1))
        return cur.fetchone()[0]

    ids = {"v1": knoten("ik_kompetenz", "2016", "1"), "v2": knoten("ik_kompetenz", "2016.V2", "1"),
           "v3": knoten("ik_kompetenz", "2016.V3", "1"), "v3_fp": knoten("fachplan", "2016.V3", "FP")}
    conn.commit()
    yield conn, cur, sid, ids
    conn.rollback()
    cur.execute("DELETE FROM context_nodes WHERE subject_id = %s", (sid,))
    cur.execute("DELETE FROM subjects WHERE id = %s", (sid,))
    conn.commit()
    conn.close()


def _status(cur, ids):
    cur.execute("SELECT id, status, archived_at IS NOT NULL FROM context_nodes WHERE id::text = ANY(%s)",
                ([str(i) for i in ids.values()],))
    nach_id = {str(i): (st, arch) for i, st, arch in cur.fetchall()}
    return {k: nach_id[str(v)] for k, v in ids.items()}


def _lauf(mod, cur, sid, jahr, dry_run=False):
    fach = {"slug": f"imp-{TOKEN}", "fach_code": CODE, "min_grade": 8, "max_grade": 12,
            "bildungsplan_suffix": ".V3"}
    return mod._archive_subject_edition(cur, sid, fach["slug"], CODE, ".V3", dry_run,
                                        cfg=FAHRPLAN, fach=fach, schuljahr_start=jahr)


def test_import_legt_kommende_fassung_als_kuenftig_ab(pg):
    """Fach ab Kl. 8, V3 startet 2026/27 in 5–7: erreicht das Fach 2027/28."""
    mod = _import_modul()
    conn, cur, sid, ids = pg

    assert _lauf(mod, cur, sid, 2026, dry_run=True) == 1
    assert {k: st for k, (st, _) in _status(cur, ids).items()} == dict.fromkeys(ids, "active")

    assert _lauf(mod, cur, sid, 2026) == 1  # gezählt wird nur Archiviertes
    assert _status(cur, ids) == {"v1": ("archived", True), "v2": ("active", False),
                                 "v3": ("upcoming", False), "v3_fp": ("upcoming", False)}

    # Ein Jahr später gilt V3 für Kl. 8 — ohne neuen Import des Fachs wieder aktiv.
    _lauf(mod, cur, sid, 2027)
    assert _status(cur, ids)["v3"] == ("active", False)
    assert _status(cur, ids)["v2"] == ("active", False)  # Kl. 9–12 brauchen V2 noch


def test_entfernte_knoten_einer_kommenden_fassung_werden_archiviert(pg):
    mod = _import_modul()
    conn, cur, sid, ids = pg
    _lauf(mod, cur, sid, 2026)
    cur.execute("SELECT metadata->>'bp_id' FROM context_nodes WHERE id::text = %s", (str(ids["v2"]),))
    bekannt = {cur.fetchone()[0]}
    mod.archive_removed_nodes(cur, bekannt, False, subject_ids={sid}, mit_fachlosen=False)
    assert _status(cur, ids)["v3"] == ("archived", True)


# ── Lesen: Curriculum-Wege mit, Suche ohne ───────────────────────────────────


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


@pytest_asyncio.fixture
async def welt(db):
    fach = Subject(slug=f"kf-{TOKEN}", name=f"Künftig {TOKEN}", fach_code=f"Q{TOKEN[:4]}".upper(),
                   min_grade=8, max_grade=12)
    db.add(fach)
    await db.flush()
    fs = Group(name=f"FS {TOKEN}", slug=f"fs-kf-{TOKEN}", type="subject_department", subject_id=fach.id)
    db.add(fs)
    await db.flush()
    db.add(GroupMembership(group_id=fs.id, pseudonym=MITGLIED, role_in_group="teacher"))

    def bp(typ, version, status, nr="", **kw):
        return ContextNode(category="knowledge", content_type=typ, title=f"{nr} {typ} {version}".strip(),
                           status=status, bp_version=version, subject_id=fach.id,
                           read_scope="global", write_scope="global", owner_pseudonym="system",
                           metadata_={"bp_version": version, "kompetenz_nr": nr} if nr else {"bp_version": version},
                           **kw)

    k = {
        "fp_v2": bp("fachplan", "2016.V2", "active"),
        "fp_v3": bp("fachplan", "2016.V3", "upcoming"),
        "ik_v2": bp("ik_kompetenz", "2016.V2", "active", "3.1(1)", min_grade=8, max_grade=8),
        "ik_v3": bp("ik_kompetenz", "2016.V3", "upcoming", "3.1(1)", min_grade=8, max_grade=8),
        "ik_v3_b": bp("ik_kompetenz", "2016.V3", "upcoming", "3.1(2)", min_grade=8, max_grade=8),
        # abgelöstes Doppel derselben Fassung (alte bp_id-Schreibweise) — zählt nirgends
        "ik_v3_alt": bp("ik_kompetenz", "2016.V3", "archived", "3.1(1)", min_grade=8, max_grade=8),
    }
    db.add_all(k.values())
    await db.flush()
    return {"fach": fach, "fs": fs, **k}


def _liste(**kw):
    """`list_nodes` direkt aufrufen — ohne FastAPI stehen sonst `Query`-Objekte in den Vorgaben."""
    args = dict(q=None, category=None, content_type=None, status=None, subject_slug=None, subject_id=None,
                mit_bezugsfaechern=False, subject_id_or_global=None, group_id=None, grade=None,
                bp_version=None, owner=None, exclude_content_type=None, limit=None, offset=None)
    args.update(kw)
    return list_nodes(**args)


async def test_liste_mit_fassung_liest_kuenftige_ohne_nicht(db, welt):
    fid = welt["fach"].id
    ohne = await _liste(content_type=["ik_kompetenz"], subject_id=fid, db=db, user=LEHRKRAFT)
    assert {n.id for n in ohne} == {welt["ik_v2"].id}

    mit = await _liste(content_type=["ik_kompetenz"], subject_id=fid, bp_version="2016.V3",
                       db=db, user=LEHRKRAFT)
    assert {n.id for n in mit} == {welt["ik_v3"].id, welt["ik_v3_b"].id}
    assert {n.gilt_ab for n in mit} == {2027}

    fachplaene = await _liste(content_type=["fachplan"], subject_id=fid, status=["active", "upcoming"],
                              db=db, user=LEHRKRAFT)
    assert {n.id for n in fachplaene} == {welt["fp_v2"].id, welt["fp_v3"].id}
    v3 = next(n for n in fachplaene if n.id == welt["fp_v3"].id)
    assert v3.gilt_ab == 2027  # ohne eigene Stufen: die des Fachs


async def test_einzelabruf_nennt_gilt_ab(db, welt):
    node = await get_node(welt["ik_v3"].id, db=db, user=LEHRKRAFT)
    assert node.status == "upcoming" and node.gilt_ab == 2027


async def test_bildungsplan_ansicht_bietet_kommende_fassung_an(db, welt):
    fid = welt["fach"].id
    standard = await get_fachplan_by_subject(fid, db=db, user=LEHRKRAFT)
    assert standard.bp_version == "2016.V2"
    assert standard.available_versions == ["2016.V2", "2016.V3"]
    assert standard.kuenftige_versionen == {"2016.V3": 2027}

    v3 = await get_fachplan_by_subject(fid, bp_version="2016.V3", db=db, user=LEHRKRAFT)
    assert v3.fachplan.id == welt["fp_v3"].id and v3.fachplan.gilt_ab == 2027


async def test_curriculum_fuer_kommende_fassung(db, welt):
    neu = await create_curriculum_node(CurriculumCreate(
        fach_code=welt["fach"].fach_code, schulart="GYM", jahrgangsstufe="8", bp_version="2016.V3",
        schule="Test", fachplan_node_id=str(welt["fp_v3"].id)), db=db, user=LEHRKRAFT)
    assert neu.status == "draft"

    kap = ContextNode(category="knowledge", content_type="kapitel", title="Kap", status="draft",
                      subject_id=welt["fach"].id, read_scope="school", write_scope="subject",
                      write_scope_group_id=welt["fs"].id, owner_pseudonym=MITGLIED, min_grade=8, max_grade=8)
    ls = ContextNode(category="knowledge", content_type="lernsequenz", title="LS", status="draft",
                     subject_id=welt["fach"].id, read_scope="school", write_scope="subject",
                     write_scope_group_id=welt["fs"].id, owner_pseudonym=MITGLIED, min_grade=8, max_grade=8,
                     metadata_={"eintraege": [{"ik": [{"nr": "3.1(1)", "node_id": str(welt["ik_v3"].id)}]}]})
    db.add_all([kap, ls])
    await db.flush()
    db.add_all([ContextEdge(from_node_id=kap.id, to_node_id=neu.id, relation="part_of"),
                ContextEdge(from_node_id=ls.id, to_node_id=kap.id, relation="part_of")])
    await db.flush()

    # Kante auf eine Kompetenz der kommenden Fassung
    await create_edge(ContextEdgeCreate(from_node_id=ls.id, to_node_id=welt["ik_v3"].id,
                                        relation="references"), db=db, user=LEHRKRAFT)

    a = await abdeckung(db, await load_curriculum_tree(db, neu.id))
    assert a["ik"]["gesamt"] == 2  # das archivierte Doppel zählt nicht mit
    assert a["ik"]["verknuepft"] == 1


async def test_nummer_ohne_fassung_trifft_die_geltende(db, welt):
    fid = welt["fach"].id
    assert await resolve_ik_node(db, fid, "3.1(1)") == welt["ik_v2"].id
    assert await resolve_ik_node(db, fid, "3.1(1)", bp_version="2016.V3") == welt["ik_v3"].id
