"""Entwürfe von Curricula — die Gegenproben (0.45, Päckchen AP Teil A, Schritt 1).

Ein Entwurf (`status = 'draft'` an Curriculum, Kapitel, Lernsequenz) ist für die Mitglieder der
Fachschaft und Admins da, für niemanden sonst: nicht für eine fachfremde Lehrkraft, nicht für
Schüler:innen, nicht in der Vorschau — weder über die direkte Adresse noch in Suche und
Jahresplanung. Den Status ändert nur „Veröffentlichen“; die allgemeinen Wege weisen das ab.
"""
import time
import uuid
from uuid import UUID

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException

from app.auth import vorschau
from app.auth.jwt import JwtPayload
from app.context.relink import duplicate_curriculum
from app.context.router import (
    copy_node,
    create_curriculum_node,
    create_edge,
    create_node,
    export_curriculum,
    fachmethoden_vorschlaege,
    fehlende_begriffe_im_curriculum,
    get_curriculum,
    get_neighborhood,
    get_node,
    list_curricula_by_subject,
    update_curriculum_meta,
    update_node,
    verwalte_node,
)
from app.context.schemas import (
    BausteinVerwalten,
    ContextEdgeCreate,
    ContextNodeCopyRequest,
    ContextNodeCreate,
    ContextNodeUpdate,
    CurriculumCreate,
    CurriculumMetaUpdate,
)
from app.context.search import Suchprofil, suche
from app.db.models import ContextEdge, ContextNode, Group, GroupMembership, GroupSourceClass, Subject
from app.planning.curriculum_resolver import resolve_group_curricula
from app.planning.service import create_unit_node, update_unit_node

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]
MITGLIED = f"mitglied-{TOKEN}"
ZWEITES = f"zweites-{TOKEN}"
FREMD = f"fremd-{TOKEN}"


def _user(sub, *rollen, preview=None):
    return JwtPayload(sub=sub, roles=list(rollen), role=rollen[0], grade=None,
                      exp=9999999999, iat=0, jti=str(uuid.uuid4()), preview=preview)


LEHRKRAFT = _user(MITGLIED, "teacher")
KOLLEGIN = _user(ZWEITES, "teacher")
FREMDE = _user(FREMD, "teacher")
SCHUELERIN = _user(f"schueler-{TOKEN}", "student")
ADMIN = _user(f"admin-{TOKEN}", "teacher", "admin")


def _vorschau_von(sub):
    """Die Lehrkraft in der Schülervorschau: Rollen simuliert, echte im Merkmal."""
    jetzt = int(time.time())
    return _user(sub, "student", preview=vorschau.Vorschau(
        echte_rollen=["teacher"], beginn=jetzt, sitzung_ablauf=jetzt + 3600))


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


@pytest_asyncio.fixture
async def welt(db):
    """Fach, Fachschaft (zwei Mitglieder), ein Entwurf und ein veröffentlichtes Curriculum."""
    fach = Subject(slug=f"fach-{TOKEN}", name=f"Fach {TOKEN}", fach_code=f"E{TOKEN[:4]}".upper())
    db.add(fach)
    await db.flush()
    fs = Group(name=f"FS {TOKEN}", slug=f"fs-{TOKEN}", type="subject_department", subject_id=fach.id)
    db.add(fs)
    await db.flush()
    db.add_all([GroupMembership(group_id=fs.id, pseudonym=MITGLIED, role_in_group="teacher"),
                GroupMembership(group_id=fs.id, pseudonym=ZWEITES, role_in_group="teacher")])
    ik = ContextNode(category="knowledge", content_type="ik_kompetenz", title=f"IK {TOKEN}",
                     status="active", read_scope="global", write_scope="global", owner_pseudonym="system")
    db.add(ik)
    await db.flush()

    async def baum(status, titel):
        def knoten(typ, t):
            return ContextNode(category="knowledge", content_type=typ, title=t, status=status,
                               read_scope="school", write_scope="subject", write_scope_group_id=fs.id,
                               subject_id=fach.id, owner_pseudonym=MITGLIED, min_grade=9, max_grade=9,
                               metadata_={"jahrgangsstufe": "9", "reihenfolge": 1, "std": "10",
                                          "eintraege": [{"fachmethoden": [{"name": f"Methode {TOKEN}"}]}]})
        cur, kap, ls = knoten("curriculum", titel), knoten("kapitel", f"{titel} Kapitel"), knoten("lernsequenz", f"{titel} LS")
        db.add_all([cur, kap, ls])
        await db.flush()
        db.add_all([ContextEdge(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"),
                    ContextEdge(from_node_id=ls.id, to_node_id=kap.id, relation="part_of")])
        await db.flush()
        return cur, kap, ls

    entwurf = await baum("draft", f"Entwurf{TOKEN}")
    aktiv = await baum("active", f"Aktiv{TOKEN}")
    return {"fach": fach, "fs": fs, "ik": ik, "entwurf": entwurf, "aktiv": aktiv}


async def _abgewiesen(coro, status=404):
    with pytest.raises(HTTPException) as e:
        await coro
    assert e.value.status_code == status, e.value.detail
    return e.value


def in_vorschau(user):
    """Setzt die Vorschau wie `get_current_user` es täte; zurückgesetzt wird sie von
    `_keine_vorschau` (conftest) nach jedem Test."""
    vorschau.fuer_anfrage(user)
    return user


# ── Lesen ────────────────────────────────────────────────────────────────────


async def test_fachschaft_und_admin_lesen_den_entwurf(db, welt):
    cur, kap, ls = welt["entwurf"]
    for wer in (LEHRKRAFT, KOLLEGIN, ADMIN):
        baum = await get_curriculum(cur.id, db=db, user=wer)
        assert [k["title"] for k in baum["kapitel"]] == [kap.title]
        assert [s["title"] for s in baum["kapitel"][0]["lernsequenzen"]] == [ls.title]
        for n in (cur, kap, ls):
            assert (await get_node(n.id, db=db, user=wer)).id == n.id


async def test_fremde_lehrkraft_liest_den_entwurf(db, welt):
    """Seit 0.52 (AZ, hebt E7 auf): lesen alle Lehrkräfte, bearbeiten nur die Fachschaft."""
    cur, kap, ls = welt["entwurf"]
    baum = await get_curriculum(cur.id, db=db, user=FREMDE)
    assert [k["title"] for k in baum["kapitel"]] == [kap.title]
    assert baum["can_edit"] is False and baum["darf_kopieren"] is False
    await export_curriculum(cur.id, format="yaml", db=db, user=FREMDE)
    await fehlende_begriffe_im_curriculum(cur.id, format="json", db=db, user=FREMDE)
    await fachmethoden_vorschlaege(cur.id, q="", db=db, user=FREMDE)
    for n in (cur, kap, ls):
        assert (await get_node(n.id, db=db, user=FREMDE)).id == n.id
        await get_neighborhood(n.id, depth=1, relation=None, category=None, db=db, user=FREMDE)


@pytest.mark.parametrize("wer", ["schuelerin", "vorschau"])
async def test_niemand_sonst_sieht_den_entwurf(db, welt, wer):
    user = SCHUELERIN if wer == "schuelerin" else in_vorschau(_vorschau_von(MITGLIED))
    cur, kap, ls = welt["entwurf"]
    await _abgewiesen(get_curriculum(cur.id, db=db, user=user))
    await _abgewiesen(export_curriculum(cur.id, format="yaml", db=db, user=user))
    await _abgewiesen(fehlende_begriffe_im_curriculum(cur.id, format="json", db=db, user=user))
    await _abgewiesen(fachmethoden_vorschlaege(cur.id, q="", db=db, user=user))
    for n in (cur, kap, ls):  # direkte Adresse — auch für Kapitel und Lernsequenz
        await _abgewiesen(get_node(n.id, db=db, user=user))
        await _abgewiesen(get_neighborhood(n.id, depth=1, relation=None, category=None, db=db, user=user))


async def test_veroeffentlichtes_bleibt_fuer_alle_lesbar(db, welt):
    cur, _, _ = welt["aktiv"]
    for wer in (FREMDE, SCHUELERIN):
        assert (await get_curriculum(cur.id, db=db, user=wer))["id"] == cur.id


async def test_entwurf_nicht_in_liste_suche_und_jahresplanung(db, welt):
    """Auch für die Fachschaft: Ein Entwurf ist kein gültiges Curriculum — Suche und Planung
    nehmen ihn nicht, gleich wer ihn lesen darf."""
    cur, kap, _ = welt["entwurf"]
    aktiv, _, _ = welt["aktiv"]
    # Die Liste zeigt den Entwurf allen Lehrkräften (mit `status`, Schritt 2; seit 0.52 nicht nur
    # der Fachschaft) — Schüler:innen nicht.
    for wer in (LEHRKRAFT, FREMDE):
        liste = await list_curricula_by_subject(welt["fach"].id, db=db, user=wer)
        assert {(c.id, c.status) for c in liste} == {(aktiv.id, "active"), (cur.id, "draft")}
    assert [c.id for c in await list_curricula_by_subject(welt["fach"].id, db=db, user=SCHUELERIN)] == [aktiv.id]

    async def gefunden(titel):
        ergebnis = await suche(titel, Suchprofil(pseudonym=MITGLIED, rollen=("teacher",)), db,
                               nur_identifikation=True)
        return {t["node_id"] for t in ergebnis.identifikation.treffer}

    assert str(aktiv.id) in await gefunden(aktiv.title)  # Gegenkontrolle: die Suche findet Curricula
    assert str(cur.id) not in await gefunden(cur.title)
    assert str(kap.id) not in await gefunden(kap.title)

    klasse = Group(name="9a", slug=f"cls-9a-{TOKEN}", type="school_class")
    kurs = Group(name=f"9a {TOKEN}", slug=f"tg-{TOKEN}", type="teaching_group", subject_id=welt["fach"].id)
    db.add_all([klasse, kurs])
    await db.flush()
    db.add(GroupSourceClass(group_id=kurs.id, class_group_id=klasse.id))
    await db.flush()
    ergebnis = await resolve_group_curricula(db, kurs.id)
    assert [c.curriculum_id for c in ergebnis.curricula] == [aktiv.id]


async def test_fachmethoden_aus_entwuerfen_fliessen_nicht_in_vorschlaege(db, welt):
    aktiv, _, _ = welt["aktiv"]
    vorschlaege = await fachmethoden_vorschlaege(aktiv.id, q="", db=db, user=LEHRKRAFT)
    assert vorschlaege == [{"name": f"Methode {TOKEN}", "anzahl": 1}]  # nur die aus dem aktiven


# ── Schreiben ────────────────────────────────────────────────────────────────


async def test_fachschaft_bearbeitet_den_entwurf(db, welt):
    cur, _, ls = welt["entwurf"]
    neu = await update_curriculum_meta(cur.id, CurriculumMetaUpdate(title=f"Neu{TOKEN}"), db=db, user=KOLLEGIN)
    assert neu["title"] == f"Neu{TOKEN}"
    await update_node(ls.id, ContextNodeUpdate(title=f"LS neu {TOKEN}"), db=db, user=KOLLEGIN)
    kante = await create_edge(ContextEdgeCreate(from_node_id=ls.id, to_node_id=welt["ik"].id,
                                                relation="references"), db=db, user=LEHRKRAFT)
    assert kante.to_node_id == welt["ik"].id


async def test_fremde_schreiben_nicht_in_den_entwurf(db, welt):
    """Sie lesen ihn (0.52) — deshalb 403 statt 404: Der Entwurf ist ihnen ja bekannt."""
    cur, _, ls = welt["entwurf"]
    await _abgewiesen(update_curriculum_meta(cur.id, CurriculumMetaUpdate(title="x"), db=db, user=FREMDE), 403)
    await _abgewiesen(update_node(ls.id, ContextNodeUpdate(title="x"), db=db, user=FREMDE), 403)
    await _abgewiesen(create_edge(ContextEdgeCreate(from_node_id=ls.id, to_node_id=welt["ik"].id,
                                                    relation="references"), db=db, user=FREMDE), 403)


@pytest.mark.parametrize("weg", ["patch", "verwalten"])
async def test_status_aendert_nur_veroeffentlichen(db, welt, weg):
    """Weder die Fachschaft über das allgemeine PATCH noch die Eigentümerin über
    „Meine Bausteine“ — und auch kein Weg zurück in den Entwurf."""
    cur, _, _ = welt["entwurf"]
    aktiv, _, _ = welt["aktiv"]
    for knoten, ziel in ((cur, "active"), (aktiv, "draft")):
        if weg == "patch":
            aufruf = update_node(knoten.id, ContextNodeUpdate(status=ziel), db=db, user=LEHRKRAFT)
        elif ziel == "draft":
            continue  # `BausteinVerwalten` kennt `draft` gar nicht
        else:
            aufruf = verwalte_node(knoten.id, BausteinVerwalten(status=ziel), db=db, user=LEHRKRAFT)
        await _abgewiesen(aufruf, 422)
    await db.refresh(cur)
    assert cur.status == "draft"


async def test_auf_einen_entwurf_zeigen_nur_teile_des_entwurfs(db, welt):
    _, kap, _ = welt["entwurf"]
    _, _, ls_aktiv = welt["aktiv"]
    await _abgewiesen(create_edge(ContextEdgeCreate(from_node_id=ls_aktiv.id, to_node_id=kap.id,
                                                    relation="part_of"), db=db, user=LEHRKRAFT), 422)


async def test_entwurfsteile_lassen_sich_nicht_einzeln_kopieren(db, welt):
    _, kap, _ = welt["entwurf"]
    await _abgewiesen(copy_node(kap.id, ContextNodeCopyRequest(), db=db, user=LEHRKRAFT), 422)


async def test_entwurf_nur_im_curriculum_baum(db, welt):
    """Die Datenbank selbst lässt `draft` nur an den drei Typen zu (Alembic 0106)."""
    welt["ik"].status = "draft"
    with pytest.raises(sa.exc.IntegrityError):
        await db.flush()
    await db.rollback()


# ── Planung ──────────────────────────────────────────────────────────────────


async def _kurs(db, welt):
    kurs = Group(name=f"Kurs {uuid.uuid4().hex[:4]}", slug=f"tg-p-{uuid.uuid4().hex[:6]}",
                 type="teaching_group", subject_id=welt["fach"].id)
    db.add(kurs)
    await db.flush()
    db.add(GroupMembership(group_id=kurs.id, pseudonym=MITGLIED, role_in_group="teacher"))
    await db.flush()
    return kurs


async def test_einheit_haengt_nur_an_veroeffentlichten_kapiteln(db, welt):
    kurs = await _kurs(db, welt)
    _, kap_entwurf, _ = welt["entwurf"]
    _, kap_aktiv, _ = welt["aktiv"]
    await _abgewiesen(create_unit_node(db, kurs.id, welt["fach"].id, LEHRKRAFT, "UE",
                                       kapitel_node_id=kap_entwurf.id), 422)
    ue = await create_unit_node(db, kurs.id, welt["fach"].id, LEHRKRAFT, "UE", kapitel_node_id=kap_aktiv.id)
    await _abgewiesen(update_unit_node(db, ue.id, kurs.id, kapitel_node_id=kap_entwurf.id,
                                       update_kapitel=True), 422)


async def test_archiviertes_kapitel_bleibt_beim_aendern_der_einheit(db, welt):
    """Ersetztes Curriculum (E15): Titel ändern geht, ein anderes archiviertes Kapitel nicht."""
    kurs = await _kurs(db, welt)
    _, kap, _ = welt["aktiv"]
    ue = await create_unit_node(db, kurs.id, welt["fach"].id, LEHRKRAFT, "UE", kapitel_node_id=kap.id)
    kap.status = "archived"
    await db.flush()
    await update_unit_node(db, ue.id, kurs.id, titel="UE neu", kapitel_node_id=kap.id, update_kapitel=True)
    anderes = ContextNode(category="knowledge", content_type="kapitel", title="alt", status="archived",
                          read_scope="school", write_scope="school", owner_pseudonym="system")
    db.add(anderes)
    await db.flush()
    await _abgewiesen(update_unit_node(db, ue.id, kurs.id, kapitel_node_id=anderes.id,
                                       update_kapitel=True), 422)


# ── Anlegen und Kopieren (Schritt 2) ─────────────────────────────────────────


async def test_neues_curriculum_ist_ein_entwurf(db, welt):
    fachplan = ContextNode(category="knowledge", content_type="fachplan", title="BP", status="active",
                           read_scope="global", write_scope="global", owner_pseudonym="system",
                           subject_id=welt["fach"].id, metadata_={"fachplan_id": f"BP_{TOKEN}"})
    db.add(fachplan)
    await db.flush()
    neu = await create_curriculum_node(CurriculumCreate(
        fach_code=welt["fach"].fach_code, schulart="G8", jahrgangsstufe="7", bp_version="2016.V3",
        schule="Test", fachplan_node_id=str(fachplan.id)), db=db, user=LEHRKRAFT)
    assert neu.status == "draft"
    assert neu.owner_pseudonym == MITGLIED
    await _abgewiesen(get_curriculum(neu.id, db=db, user=SCHUELERIN))
    assert (await get_curriculum(neu.id, db=db, user=FREMDE))["can_edit"] is False


def _kapitel(welt, **kw):
    return ContextNodeCreate(category="knowledge", content_type="kapitel", title=f"Neu {uuid.uuid4().hex[:4]}",
                             read_scope="school", write_scope="subject",
                             write_scope_group_id=welt["fs"].id, subject_id=welt["fach"].id, **kw)


async def test_teile_gleich_als_entwurf_anlegen(db, welt):
    """So legt der Editor Kapitel und Lernsequenzen in einem Entwurf an."""
    cur, _, _ = welt["entwurf"]
    kap = await create_node(_kapitel(welt, status="draft"), db=db, user=LEHRKRAFT)
    assert kap.status == "draft"
    await create_edge(ContextEdgeCreate(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"),
                      db=db, user=LEHRKRAFT)
    baum = await get_curriculum(cur.id, db=db, user=KOLLEGIN)
    assert kap.title in [k["title"] for k in baum["kapitel"]]

    await _abgewiesen(create_node(_kapitel(welt, status="draft"), db=db, user=FREMDE), 403)
    begriff = ContextNodeCreate(category="concept", content_type="begriff", title="B", status="draft",
                                subject_id=welt["fach"].id)
    await _abgewiesen(create_node(begriff, db=db, user=LEHRKRAFT), 422)


async def test_frisches_kapitel_erbt_den_entwurf(db, welt):
    """Ein Editor ohne `status` (oder ein älterer Browser-Tab) legt `active` an — die Kante
    in den Entwurf macht das frische Kapitel selbst zum Entwurf."""
    cur, _, _ = welt["entwurf"]
    kap = await create_node(_kapitel(welt), db=db, user=LEHRKRAFT)
    assert kap.status == "active"
    await create_edge(ContextEdgeCreate(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"),
                      db=db, user=LEHRKRAFT)
    assert kap.status == "draft"
    await _abgewiesen(get_node(kap.id, db=db, user=SCHUELERIN))


async def test_haengendes_kapitel_erbt_nicht(db, welt):
    """Ein Kapitel aus einem veröffentlichten Curriculum verschwindet nicht in einem Entwurf."""
    cur, _, _ = welt["entwurf"]
    _, kap_aktiv, _ = welt["aktiv"]
    await _abgewiesen(create_edge(ContextEdgeCreate(from_node_id=kap_aktiv.id, to_node_id=cur.id,
                                                    relation="part_of"), db=db, user=LEHRKRAFT), 422)
    assert kap_aktiv.status == "active"


async def test_kopie_ist_entwurf_der_kopierenden_person(db, welt):
    aktiv, kap, ls = welt["aktiv"]
    weg = ContextNode(category="knowledge", content_type="kapitel", title="Gelöscht", status="deleted",
                      read_scope="school", write_scope="subject", write_scope_group_id=welt["fs"].id,
                      subject_id=welt["fach"].id, owner_pseudonym=MITGLIED)
    db.add(weg)
    await db.flush()
    db.add(ContextEdge(from_node_id=weg.id, to_node_id=aktiv.id, relation="part_of"))
    await db.flush()

    neu_id, ls_map = await duplicate_curriculum(db, aktiv.id, owner=ZWEITES)
    neu = await db.get(ContextNode, neu_id)
    assert (neu.status, neu.owner_pseudonym, neu.metadata_["kopie_von"]) == ("draft", ZWEITES, str(aktiv.id))
    baum = await get_curriculum(neu_id, db=db, user=LEHRKRAFT)
    assert [k["title"] for k in baum["kapitel"]] == [kap.title]  # das gelöschte kommt nicht mit
    kap_neu = await db.get(ContextNode, baum["kapitel"][0]["id"])
    ls_neu = await db.get(ContextNode, UUID(ls_map[str(ls.id)]))
    assert (kap_neu.status, kap_neu.metadata_["kopie_von"]) == ("draft", str(kap.id))
    assert (ls_neu.status, ls_neu.owner_pseudonym) == ("draft", ZWEITES)
    await _abgewiesen(get_curriculum(neu_id, db=db, user=SCHUELERIN))
    assert aktiv.status == "active"


# ── Veröffentlichen, Kopieren, Ersetzen (Schritt 4) ──────────────────────────

from app.context import curriculum_entwurf as entwurf_modul  # noqa: E402
from app.context import router as router_modul  # noqa: E402
from app.context.router import (  # noqa: E402
    curriculum_als_entwurf_kopieren,
    curriculum_veroeffentlichen,
    reaktiviere_node,
    veroeffentlichen_uebersicht,
)
from app.db.models import AuditLog  # noqa: E402
from app.planning.calendar import load_school_year  # noqa: E402
from app.planning.router import list_units  # noqa: E402

VORSITZ = _user(MITGLIED, "teacher", "fachvorsitz")


@pytest.fixture
def mit_vorsitz(monkeypatch):
    """Der Rolle `fachvorsitz` ist eine Gruppe zugeordnet (E9)."""
    for modul in (entwurf_modul, router_modul):
        monkeypatch.setattr(modul, "fachvorsitz_zugeordnet", lambda: True)


@pytest.fixture
def ohne_vorsitz(monkeypatch):
    for modul in (entwurf_modul, router_modul):
        monkeypatch.setattr(modul, "fachvorsitz_zugeordnet", lambda: False)


async def test_ohne_vorsitz_veroeffentlicht_die_fachschaft(db, welt, ohne_vorsitz):
    cur, kap, ls = welt["entwurf"]
    rechte = await get_curriculum(cur.id, db=db, user=KOLLEGIN)
    assert rechte["darf_veroeffentlichen"] and rechte["wer_veroeffentlicht"] == "Mitglieder der Fachschaft und Admins"
    await curriculum_veroeffentlichen(cur.id, db=db, user=KOLLEGIN)
    for n in (cur, kap, ls):
        await db.refresh(n)
        assert n.status == "active"
    assert (await get_curriculum(cur.id, db=db, user=FREMDE))["id"] == cur.id
    eintrag = (await db.execute(sa.select(AuditLog).where(
        AuditLog.event_type == "curriculum_published", AuditLog.target_id == str(cur.id)))).scalar_one()
    assert eintrag.actor_pseudonym == ZWEITES
    await _abgewiesen(curriculum_veroeffentlichen(cur.id, db=db, user=KOLLEGIN), 409)  # schon veröffentlicht


async def test_mit_vorsitz_nur_der_vorsitz(db, welt, mit_vorsitz):
    cur, _, _ = welt["entwurf"]
    aktiv, kap_aktiv, ls_aktiv = welt["aktiv"]
    # Entwurf: die ganze Fachschaft bearbeitet, nur der Vorsitz veröffentlicht.
    assert (await get_curriculum(cur.id, db=db, user=KOLLEGIN))["can_edit"]
    assert not (await get_curriculum(cur.id, db=db, user=KOLLEGIN))["darf_veroeffentlichen"]
    await _abgewiesen(curriculum_veroeffentlichen(cur.id, db=db, user=KOLLEGIN), 403)
    # Veröffentlichtes ändern: nur Vorsitz und Admin — über alle Wege (E13).
    assert not (await get_curriculum(aktiv.id, db=db, user=KOLLEGIN))["can_edit"]
    await _abgewiesen(update_curriculum_meta(aktiv.id, CurriculumMetaUpdate(title="x"), db=db, user=KOLLEGIN), 403)
    await _abgewiesen(update_node(ls_aktiv.id, ContextNodeUpdate(title="x"), db=db, user=KOLLEGIN), 403)
    await _abgewiesen(create_edge(ContextEdgeCreate(from_node_id=ls_aktiv.id, to_node_id=welt["ik"].id,
                                                    relation="references"), db=db, user=KOLLEGIN), 403)
    await update_node(ls_aktiv.id, ContextNodeUpdate(title="LS vom Vorsitz"), db=db, user=VORSITZ)
    await update_curriculum_meta(aktiv.id, CurriculumMetaUpdate(title=f"Admin{TOKEN}"), db=db, user=ADMIN)
    liste = {c.id: c.darf_schreiben for c in await list_curricula_by_subject(welt["fach"].id, db=db, user=KOLLEGIN)}
    assert liste == {aktiv.id: False, cur.id: True}  # Marke „Bearbeitbar“
    # Die Rolle gilt nur in eigenen Fachschaften (E10: kein Fach an der Gruppe, aber Mitgliedschaft).
    fremder_vorsitz = _user(FREMD, "teacher", "fachvorsitz")
    await _abgewiesen(update_node(ls_aktiv.id, ContextNodeUpdate(title="x"), db=db, user=fremder_vorsitz), 403)

    await curriculum_veroeffentlichen(cur.id, db=db, user=VORSITZ)
    await db.refresh(cur)
    assert cur.status == "active"


async def test_vorschau_veroeffentlicht_nicht(db, welt):
    cur, _, _ = welt["entwurf"]
    user = in_vorschau(_vorschau_von(MITGLIED))
    await _abgewiesen(curriculum_veroeffentlichen(cur.id, db=db, user=user))


async def test_als_entwurf_kopieren(db, welt, mit_vorsitz):
    aktiv, _, _ = welt["aktiv"]
    rechte = await get_curriculum(aktiv.id, db=db, user=KOLLEGIN)
    assert rechte["darf_kopieren"] and rechte["offener_entwurf"] is None
    neu = (await curriculum_als_entwurf_kopieren(aktiv.id, db=db, user=KOLLEGIN))["id"]
    kopie = await get_curriculum(neu, db=db, user=KOLLEGIN)
    assert (kopie["status"], kopie["title"], kopie["can_edit"]) == ("draft", aktiv.title, True)
    assert kopie["kopie_von"] == {"id": aktiv.id, "title": aktiv.title}
    assert (await get_curriculum(aktiv.id, db=db, user=LEHRKRAFT))["offener_entwurf"]["id"] == neu
    fehler = await _abgewiesen(curriculum_als_entwurf_kopieren(aktiv.id, db=db, user=LEHRKRAFT), 409)
    assert fehler.detail["entwurf_id"] == str(neu)  # höchstens ein offener Entwurf
    await _abgewiesen(curriculum_als_entwurf_kopieren(aktiv.id, db=db, user=FREMDE), 403)
    await _abgewiesen(curriculum_als_entwurf_kopieren(neu, db=db, user=KOLLEGIN), 409)  # Entwurf: nicht kopieren


async def _einheit(db, welt, kapitel, schuljahr=None):
    kurs = await _kurs(db, welt)
    ue = await create_unit_node(db, kurs.id, welt["fach"].id, LEHRKRAFT, f"UE {uuid.uuid4().hex[:4]}",
                                kapitel_node_id=kapitel.id)
    if schuljahr:
        ue.metadata_ = {**ue.metadata_, "schuljahr": schuljahr}
        await db.flush()
    return kurs, ue


async def _kapitel_der(db, ue):
    return (await db.execute(sa.select(ContextEdge.to_node_id).join(
        ContextNode, ContextNode.id == ContextEdge.to_node_id).where(
        ContextEdge.from_node_id == ue.id, ContextNode.content_type == "kapitel"))).scalar_one()


async def test_kopie_ersetzt_den_vorgaenger(db, welt, ohne_vorsitz):
    """E15: Vorgänger archiviert; Einheiten dieses Schuljahrs wandern; fehlt das Kapitel in der
    Kopie, bleibt die Einheit am alten — die Planung meldet es."""
    aktiv, kap_alt, ls_alt = welt["aktiv"]
    weg = ContextNode(category="knowledge", content_type="kapitel", title="Fällt weg", status="active",
                      read_scope="school", write_scope="subject", write_scope_group_id=welt["fs"].id,
                      subject_id=welt["fach"].id, owner_pseudonym=MITGLIED)
    db.add(weg)
    await db.flush()
    db.add(ContextEdge(from_node_id=weg.id, to_node_id=aktiv.id, relation="part_of"))
    await db.flush()
    kurs, ue_jetzt = await _einheit(db, welt, kap_alt)
    _, ue_alt = await _einheit(db, welt, kap_alt, schuljahr="2019/20")
    kurs_weg, ue_weg = await _einheit(db, welt, weg)

    neu = (await curriculum_als_entwurf_kopieren(aktiv.id, db=db, user=KOLLEGIN))["id"]
    baum = await get_curriculum(neu, db=db, user=KOLLEGIN)
    kap_neu = next(k for k in baum["kapitel"] if k["title"] == kap_alt.title)
    # In der Kopie das Kapitel „Fällt weg“ entfernen (wie im Editor: Kante weg, Knoten gelöscht).
    weg_kopie = next(k for k in baum["kapitel"] if k["title"] == "Fällt weg")
    (await db.get(ContextNode, weg_kopie["id"])).status = "deleted"
    await db.flush()

    u = await veroeffentlichen_uebersicht(neu, db=db, user=KOLLEGIN)
    assert u["vorgaenger"]["id"] == aktiv.id and u["einheiten_umgehaengt"] == 1
    assert u["einheiten_ohne_kapitel"] == [{"gruppe": kurs_weg.name, "kapitel": "Fällt weg"}]
    assert u["darf_veroeffentlichen"]

    ergebnis = await curriculum_veroeffentlichen(neu, db=db, user=KOLLEGIN)
    assert ergebnis["einheiten_umgehaengt"] == 1
    for n in (aktiv, kap_alt, ls_alt, weg):
        await db.refresh(n)
        assert n.status == "archived" and n.archived_at is not None
    assert await _kapitel_der(db, ue_jetzt) == kap_neu["id"]
    assert await _kapitel_der(db, ue_alt) == kap_alt.id      # früheres Schuljahr bleibt
    assert await _kapitel_der(db, ue_weg) == weg.id           # ohne Entsprechung bleibt

    einheiten = {e.id: e for e in await list_units(kurs_weg.id, db=db, user=LEHRKRAFT)}
    assert einheiten[ue_weg.id].kapitel_archiviert           # Banner in der Jahresübersicht
    assert not {e.id: e for e in await list_units(kurs.id, db=db, user=LEHRKRAFT)}[ue_jetzt.id].kapitel_archiviert

    from app.planning import archiv
    inhalt = await archiv.archiv_inhalt(db, kurs_weg, welt["fach"], archiv.MITGLIED, LEHRKRAFT, stati=("active",))
    assert [e.kapitel_ersetzt for e in inhalt.einheiten] == [True]  # Banner in der Einheitenansicht


async def test_reaktivieren_nur_mit_recht(db, welt, mit_vorsitz):
    """E16: Ein ersetzter Vorgänger kommt nur mit dem Recht aus E13 zurück."""
    aktiv, _, _ = welt["aktiv"]
    aktiv.status = "archived"
    await db.flush()
    await _abgewiesen(reaktiviere_node(aktiv.id, db=db, user=KOLLEGIN), 403)
    await reaktiviere_node(aktiv.id, db=db, user=VORSITZ)
    assert aktiv.status == "active"


# ── Löschen und Lebenszyklus (Schritt 5) ─────────────────────────────────────

from datetime import date, datetime, timedelta, timezone  # noqa: E402

from app.context.router import delete_node  # noqa: E402
from app.crons.node_lifecycle_service import archiviere_abgelaufene, loesche_alte_archivierte  # noqa: E402

KOLLEGIN_VORSITZ = _user(ZWEITES, "teacher", "fachvorsitz")


async def _geloescht(db, *knoten):
    for n in knoten:
        assert await db.get(ContextNode, n.id, populate_existing=True) is None


async def test_entwurf_loeschen_mit_vorsitz(db, welt, mit_vorsitz):
    """E12: wer angelegt hat, Fachvorsitz, Admin — nicht jedes Mitglied der Fachschaft."""
    cur, kap, ls = welt["entwurf"]
    assert not (await get_curriculum(cur.id, db=db, user=KOLLEGIN))["darf_loeschen"]
    assert (await get_curriculum(cur.id, db=db, user=LEHRKRAFT))["darf_loeschen"]  # angelegt
    await _abgewiesen(delete_node(cur.id, force=False, db=db, user=KOLLEGIN), 403)
    # Teile eines Entwurfs löscht der Editor — Bearbeitungsrecht genügt.
    await delete_node(ls.id, force=False, db=db, user=KOLLEGIN)
    await delete_node(cur.id, force=False, db=db, user=KOLLEGIN_VORSITZ)
    await _geloescht(db, cur, kap, ls)


async def test_entwurf_loescht_die_person_die_ihn_angelegt_hat(db, welt, mit_vorsitz):
    cur, kap, ls = welt["entwurf"]
    await delete_node(cur.id, force=False, db=db, user=LEHRKRAFT)
    await _geloescht(db, cur, kap, ls)


async def test_ohne_vorsitz_loescht_die_fachschaft(db, welt):
    cur, _, _ = welt["entwurf"]
    assert (await get_curriculum(cur.id, db=db, user=KOLLEGIN))["darf_loeschen"]
    await delete_node(cur.id, force=False, db=db, user=KOLLEGIN)
    await _geloescht(db, cur)


async def test_veroeffentlichtes_loeschen_wie_aendern(db, welt, mit_vorsitz):
    aktiv, _, _ = welt["aktiv"]
    await _abgewiesen(delete_node(aktiv.id, force=False, db=db, user=KOLLEGIN), 403)
    assert (await get_curriculum(aktiv.id, db=db, user=KOLLEGIN_VORSITZ))["darf_loeschen"]


async def test_liste_nennt_letzte_aenderung_des_entwurfs(db, welt):
    cur, _, ls = welt["entwurf"]
    spaeter = datetime.now(timezone.utc) + timedelta(days=3)
    await db.execute(sa.update(ContextNode).where(ContextNode.id == ls.id).values(updated_at=spaeter))
    liste = {c.id: c for c in await list_curricula_by_subject(welt["fach"].id, db=db, user=LEHRKRAFT)}
    assert liste[cur.id].zuletzt_geaendert == spaeter      # Änderung tief im Baum zählt
    assert getattr(liste[welt["aktiv"][0].id], "zuletzt_geaendert", None) is None


async def test_entwurf_laeuft_nicht_ab(db, welt):
    """F5/E12: Ablauf und Löschlauf fassen Entwürfe nicht an — auch mit Ablaufdatum."""
    cur, kap, ls = welt["entwurf"]
    for n in (cur, kap, ls):
        n.valid_until = date(2020, 1, 1)
        n.archived_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    await db.flush()
    await archiviere_abgelaufene(db, heute=date.today())
    await loesche_alte_archivierte(db, jetzt=datetime.now(timezone.utc))
    for n in (cur, kap, ls):
        await db.refresh(n)
        assert n.status == "draft"
