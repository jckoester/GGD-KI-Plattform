"""YAML-Import als Entwurf (0.56, Päckchen BA Schritt 2): ein neuer Entwurf mit eigenem
Schlüssel, nie ein Treffer auf ein vorhandenes Curriculum; mit `kopie_von` ein Ersatz, der beim
Veröffentlichen das Original ablöst. Erfordert TEST_DATABASE_URL."""
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.auth.jwt import JwtPayload
from app.context.curriculum_veroeffentlichen import veroeffentlichen
from app.context.curriculum_yaml import zu_entwurf
from app.context.service import import_curriculum_from_draft, load_curriculum_tree
from app.db.models import ContextNode

pytestmark = pytest.mark.asyncio

BP_ID = "BP2016BW_ALLG_GYM_CH_BATEST"
BP_VERSION = "2016.BA"
ICH = JwtPayload(sub="ba-lehrkraft", roles=["teacher"], grade=None, jti="j", iat=0, exp=9999999999)


@pytest_asyncio.fixture
async def welt(db_session):
    subject_id = (await db_session.execute(sa.text(
        "INSERT INTO subjects (slug, name, fach_code) VALUES ('chemie', 'Chemie', 'CH') "
        "ON CONFLICT (slug) DO UPDATE SET fach_code = EXCLUDED.fach_code RETURNING id"))).scalar_one()
    db_session.add(ContextNode(
        id=uuid.uuid4(), category="knowledge", content_type="fachplan", title="Gymnasium - Chemie",
        status="active", owner_pseudonym="system", read_scope="global", write_scope="school",
        subject_id=subject_id, metadata_={"bp_id": BP_ID, "bp_version": BP_VERSION}))
    await db_session.flush()
    return subject_id


def _datei(*kapitel, jahrgang="8"):
    p = zu_entwurf({
        "schule": "", "fach_code": "CH", "fach": "Chemie", "schulart": "Gymnasium", "jahrgangsstufe": jahrgang,
        "bp_id": BP_ID, "bp_version": BP_VERSION,
        "kapitel": [{"titel": t, "reihenfolge": i, "lernsequenzen": [
            {"bp_titel": f"LS {t}", "reihenfolge": 1, "eintraege": [{"konkretisierung": "x"}]}]}
            for i, t in enumerate(kapitel, 1)],
    })
    assert p.ok, p.fehler
    return p.entwurf


async def _baum(db, cid):
    return await load_curriculum_tree(db, cid)


def _knoten_ids(tree):
    ids = [tree["id"]]
    for kap in tree["kapitel"]:
        ids.append(kap["id"])
        ids += [ls["id"] for ls in kap["lernsequenzen"]]
    return ids


async def test_entwurf_trifft_das_vorhandene_curriculum_nicht(db_session, welt):
    original_id, _ = await import_curriculum_from_draft(db_session, _datei("Stoffe", "Reaktionen"), "system")
    vorher = await _baum(db_session, original_id)

    neu_id, stats = await import_curriculum_from_draft(db_session, _datei("Nur eins"), ICH.sub, als_entwurf=True)

    assert neu_id != original_id
    assert stats.archived_count == 0
    nachher = await _baum(db_session, original_id)
    assert [k["title"] for k in nachher["kapitel"]] == ["Stoffe", "Reaktionen"]
    assert nachher["status"] == vorher["status"] == "active"

    entwurf = await _baum(db_session, neu_id)
    assert [k["title"] for k in entwurf["kapitel"]] == ["Nur eins"]
    knoten = (await db_session.execute(sa.select(ContextNode).where(
        ContextNode.id.in_(_knoten_ids(entwurf))))).scalars().all()
    assert len(knoten) == 3
    assert {k.status for k in knoten} == {"draft"}
    assert {k.owner_pseudonym for k in knoten} == {ICH.sub}
    assert (entwurf["metadata"]["import_key"]).startswith("yaml_")
    assert "kopie_von" not in entwurf["metadata"]


async def test_zwei_importe_zwei_entwuerfe(db_session, welt):
    a, _ = await import_curriculum_from_draft(db_session, _datei("K"), ICH.sub, als_entwurf=True)
    b, _ = await import_curriculum_from_draft(db_session, _datei("K"), ICH.sub, als_entwurf=True)
    assert a != b
    assert [k["title"] for k in (await _baum(db_session, a))["kapitel"]] == ["K"]


async def test_ersatz_mit_kapitel_nach_titel_und_veroeffentlichen(db_session, welt):
    original_id, _ = await import_curriculum_from_draft(db_session, _datei("Stoffe", "Reaktionen"), "system")
    original = await _baum(db_session, original_id)
    alt = {k["title"]: k["id"] for k in original["kapitel"]}

    neu_id, _ = await import_curriculum_from_draft(
        db_session, _datei("  stoffe ", "Neu"), ICH.sub, als_entwurf=True, kopie_von=original_id)

    entwurf = await _baum(db_session, neu_id)
    assert entwurf["title"] == original["title"]
    assert entwurf["metadata"]["kopie_von"] == str(original_id)
    kopie_von = {k["title"]: (k.get("metadata") or {}).get("kopie_von") for k in entwurf["kapitel"]}
    assert kopie_von == {"stoffe": str(alt["Stoffe"]), "Neu": None}

    ergebnis = await veroeffentlichen(db_session, entwurf, ICH)
    assert ergebnis["vorgaenger"]["id"] == original_id
    assert (await db_session.get(ContextNode, original_id)).status == "archived"
    assert (await db_session.get(ContextNode, neu_id)).status == "active"


async def test_ersatz_nur_fuer_veroeffentlichtes_curriculum_im_fach(db_session, welt):
    entwurf_id, _ = await import_curriculum_from_draft(db_session, _datei("K"), ICH.sub, als_entwurf=True)
    fremd = ContextNode(id=uuid.uuid4(), category="knowledge", content_type="concept", title="x", status="active",
                        owner_pseudonym="x", read_scope="school", write_scope="school", subject_id=welt)
    db_session.add(fremd)
    await db_session.flush()
    for ziel in (entwurf_id, fremd.id, uuid.uuid4()):
        with pytest.raises(ValueError, match="ersetzen"):
            await import_curriculum_from_draft(db_session, _datei("K"), ICH.sub, als_entwurf=True, kopie_von=ziel)
    with pytest.raises(ValueError, match="nur für Entwürfe"):
        await import_curriculum_from_draft(db_session, _datei("K"), ICH.sub, kopie_von=entwurf_id)


async def test_doppelte_reihenfolge_legt_keine_kapitel_zusammen(db_session, welt):
    p = zu_entwurf({
        "schule": "", "fach_code": "CH", "schulart": "G", "jahrgangsstufe": "8", "bp_id": BP_ID,
        "bp_version": BP_VERSION, "kapitel": [
            {"titel": "A", "reihenfolge": 1, "lernsequenzen": [{"bp_titel": "a1"}, {"bp_titel": "a2"}]},
            {"titel": "B", "reihenfolge": 1, "lernsequenzen": [
                {"bp_titel": "b1", "reihenfolge": 3}, {"bp_titel": "b2", "reihenfolge": 3}]}]})
    assert p.ok
    assert "Kapitel: Reihenfolge doppelt — nach Position neu nummeriert." in p.warnungen
    cid, _ = await import_curriculum_from_draft(db_session, p.entwurf, ICH.sub, als_entwurf=True)
    tree = await _baum(db_session, cid)
    assert [(k["title"], [ls["title"] for ls in k["lernsequenzen"]]) for k in tree["kapitel"]] == [
        ("A", ["a1", "a2"]), ("B", ["b1", "b2"])]
