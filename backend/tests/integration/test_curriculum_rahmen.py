"""Rahmenangaben am Curriculum (0.46, Päckchen AP Teil B, Schritt 4; E20).

Der Editor schreibt sie als `metadata.rahmen` über `PATCH /context/nodes/{id}` — dort geprüft
und bereinigt; der YAML-Export trägt sie, der Import übernimmt sie; „Rückgängig“ nimmt sie mit.
"""
import importlib.util
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import yaml
from fastapi import HTTPException

from app.auth.jwt import JwtPayload
from app.context.curriculum_export import build_curriculum_export_dict
from app.context.curriculum_verlauf import sichern, zuruecknehmen
from app.context.router import update_node
from app.context.schemas import (
    ContextNodeUpdate, CurriculumDraftConfirmed, CurriculumDraftKapitel, CurriculumDraftLernsequenz,
)
from app.context.service import import_curriculum_from_draft, load_curriculum_tree
from app.db.models import ContextNode, Subject

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]
ADMIN = JwtPayload(sub=f"admin-{TOKEN}", roles=["admin", "teacher"], role="admin", grade=None,
                   exp=9999999999, iat=0, jti=str(uuid.uuid4()))


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


@pytest_asyncio.fixture
async def cid(db):
    fachplan = f"BP_RAHMEN_{TOKEN}"
    code = f"R{TOKEN[:4]}".upper()
    db.add(Subject(slug=f"rahmen-{TOKEN}", name=f"Rahmen {TOKEN}", fach_code=code))
    db.add(ContextNode(category="knowledge", content_type="fachplan", title="BP", status="active",
                       owner_pseudonym="system", read_scope="global", write_scope="school",
                       metadata_={"fachplan_id": fachplan}))
    await db.flush()
    draft = CurriculumDraftConfirmed(schule="T", fach_code=code, schulart="G", jahrgangsstufe="7/8",
                                     fachplan_id=fachplan, bp_version="2016", kapitel=[
        CurriculumDraftKapitel(titel="K", reihenfolge=1, lernsequenzen=[
            CurriculumDraftLernsequenz(bp_titel="L", reihenfolge=1, eintraege=[])])])
    cid, _ = await import_curriculum_from_draft(db, draft, ADMIN.sub)
    return cid


async def _meta(db, cid):
    return (await db.get(ContextNode, cid, populate_existing=True)).metadata_


async def test_editor_speichert_bereinigt(db, cid):
    meta = dict(await _meta(db, cid))
    meta["rahmen"] = {"wochenstunden": {"7": "2", "8": "1,5"}, "lehrwerk": " Fokus Chemie ", "absprachen": ""}
    await update_node(cid, ContextNodeUpdate(metadata=meta), db=db, user=ADMIN)
    neu = await _meta(db, cid)
    assert neu["rahmen"] == {"wochenstunden": {"7": 2, "8": 1.5}, "lehrwerk": "Fokus Chemie"}
    assert neu["jahrgangsstufe"] == "7/8"  # der Rest bleibt


async def test_editor_weist_unbrauchbares_ab(db, cid):
    meta = {**(await _meta(db, cid)), "rahmen": {"wochenstunden": {"7": "viel"}}}
    with pytest.raises(HTTPException) as e:
        await update_node(cid, ContextNodeUpdate(metadata=meta), db=db, user=ADMIN)
    assert e.value.status_code == 422


async def test_yaml_rundreise(db, cid):
    meta = {**(await _meta(db, cid)), "rahmen": {"wochenstunden": {"7": 2, "8": 2}, "beschluesse": "- Exkursion"}}
    await update_node(cid, ContextNodeUpdate(metadata=meta), db=db, user=ADMIN)

    daten = await build_curriculum_export_dict(db, await load_curriculum_tree(db, cid))
    assert daten["rahmen"] == {"wochenstunden": {"7": 2, "8": 2}, "beschluesse": "- Exkursion"}

    pfad = Path(__file__).resolve().parents[2] / "scripts" / "import_curriculum.py"
    spec = importlib.util.spec_from_file_location("_import_curriculum_rahmen", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    neu = yaml.safe_load(yaml.safe_dump(daten, allow_unicode=True)) | {"jahrgangsstufe": "9/10"}
    cid2, _ = await import_curriculum_from_draft(db, modul.convert_yaml_to_draft(neu), ADMIN.sub)
    assert (await _meta(db, cid2))["rahmen"] == daten["rahmen"]


async def test_ohne_rahmen_kein_feld_im_export(db, cid):
    daten = await build_curriculum_export_dict(db, await load_curriculum_tree(db, cid))
    assert "rahmen" not in daten
    assert "rahmen" not in await _meta(db, cid)


async def test_rueckgaengig_nimmt_den_rahmen_mit(db, cid):
    await sichern(db, cid, grund="editor", von=ADMIN.sub)
    meta = {**(await _meta(db, cid)), "rahmen": {"lehrwerk": "neu"}}
    await update_node(cid, ContextNodeUpdate(metadata=meta), db=db, user=ADMIN)
    await zuruecknehmen(db, await db.get(ContextNode, cid))
    assert "rahmen" not in await _meta(db, cid)
