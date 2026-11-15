"""Entwürfe von Curricula — die Gegenproben (0.45, Päckchen AP Teil A, Schritt 1).

Ein Entwurf (`status = 'draft'` an Curriculum, Kapitel, Lernsequenz) ist für die Mitglieder der
Fachschaft und Admins da, für niemanden sonst: nicht für eine fachfremde Lehrkraft, nicht für
Schüler:innen, nicht in der Vorschau — weder über die direkte Adresse noch in Suche und
Jahresplanung. Den Status ändert nur „Veröffentlichen“; die allgemeinen Wege weisen das ab.
"""
import time
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException

from app.auth import vorschau
from app.auth.jwt import JwtPayload
from app.context.router import (
    copy_node,
    create_edge,
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
    ContextNodeUpdate,
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


@pytest.mark.parametrize("wer", ["fremd", "schuelerin", "vorschau"])
async def test_niemand_sonst_sieht_den_entwurf(db, welt, wer):
    user = {"fremd": FREMDE, "schuelerin": SCHUELERIN}.get(wer) or in_vorschau(_vorschau_von(MITGLIED))
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
    """Auch für die Fachschaft: Ein Entwurf ist kein gültiges Curriculum."""
    cur, kap, _ = welt["entwurf"]
    aktiv, _, _ = welt["aktiv"]
    liste = await list_curricula_by_subject(welt["fach"].id, db=db, user=LEHRKRAFT)
    assert [c.id for c in liste] == [aktiv.id]

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
    cur, _, ls = welt["entwurf"]
    await _abgewiesen(update_curriculum_meta(cur.id, CurriculumMetaUpdate(title="x"), db=db, user=FREMDE))
    await _abgewiesen(update_node(ls.id, ContextNodeUpdate(title="x"), db=db, user=FREMDE))
    await _abgewiesen(create_edge(ContextEdgeCreate(from_node_id=ls.id, to_node_id=welt["ik"].id,
                                                    relation="references"), db=db, user=FREMDE))


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
