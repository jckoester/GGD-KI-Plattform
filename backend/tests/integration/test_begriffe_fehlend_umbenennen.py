"""Fehlende Begriffe, Gerüste und Umbenennen (0.44, Päckchen AQ, Schritt 4).

* `GET /context/curricula/{id}/begriffe/fehlend` — Übersicht, Liste, Zip mit Gerüsten.
* Der Fachbegriffe-Import weist ein Gerüst (`geruest: true`) ohne Definition ab (E7 b); mit
  Definition ist es eine gewöhnliche Datei. Andere Dateien ohne Definition bleiben Stubs (A8).
* Beim Umbenennen eines Begriffs bleibt der alte Titel Alias (E12) — in der Oberfläche und
  im Import, dort auch über den nächsten Lauf hinweg.
"""
import io
import uuid
import zipfile

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.auth.jwt import JwtPayload
from app.context import aliase as aliase_modul
from app.context import fachbegriffe_import as seed
from app.context.metadata import STUB_MARKIERUNG
from app.context.router import fehlende_begriffe_im_curriculum, update_node, verwalte_node
from app.context.schemas import (
    BausteinVerwalten,
    ContextNodeUpdate,
    CurriculumDraftConfirmed,
    CurriculumDraftEntry,
    CurriculumDraftKapitel,
    CurriculumDraftLernsequenz,
)
from app.context.service import import_curriculum_from_draft
from app.db.models import ContextNode, Subject

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]


def _n(s: str) -> str:
    return f"Q{TOKEN}{s}"


def _user(*rollen, sub="lehrkraft-fehlend"):
    return JwtPayload(sub=sub, roles=list(rollen), role=rollen[0], grade=None,
                      exp=9999999999, iat=0, jti=str(uuid.uuid4()))


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


@pytest_asyncio.fixture
async def chemie(db):
    f = Subject(slug=f"chemie-{TOKEN}", name=f"Chemie {TOKEN}", fach_code=f"C{TOKEN[:4]}".upper())
    db.add(f)
    await db.flush()
    return f


async def _begriff(db, titel, fach, **kw):
    n = ContextNode(category="concept", content_type="begriff", title=titel, status="active",
                    subject_id=fach.id, read_scope="school", write_scope="school",
                    content="Eine Definition.", owner_pseudonym=kw.pop("owner_pseudonym", "lehrkraft-fehlend"),
                    metadata_=kw.pop("metadata_", {}), **kw)
    db.add(n)
    await db.flush()
    return n


async def _curriculum(db, fach, kapitel: dict[str, list[list]]):
    fachplan = f"BP_AQF_{TOKEN}_{uuid.uuid4().hex[:4]}"
    db.add(ContextNode(category="knowledge", content_type="fachplan", title="BP", status="active",
                       owner_pseudonym="system", read_scope="global", write_scope="school",
                       metadata_={"fachplan_id": fachplan}))
    await db.flush()
    draft = CurriculumDraftConfirmed(
        schule="Test", fach_code=fach.fach_code, fach=fach.name, schulart="G8", jahrgangsstufe="9",
        fachplan_id=fachplan, bp_version="2016",
        kapitel=[CurriculumDraftKapitel(titel=titel, reihenfolge=i + 1, lernsequenzen=[
            CurriculumDraftLernsequenz(bp_titel="LS", reihenfolge=1,
                                       eintraege=[CurriculumDraftEntry(begriffe=b) for b in eintraege])])
                 for i, (titel, eintraege) in enumerate(kapitel.items())],
    )
    cid, _ = await import_curriculum_from_draft(db, draft, "lehrkraft-fehlend")
    node = await db.get(ContextNode, cid)
    node.subject_id = fach.id
    await db.flush()
    return cid


# ── Übersicht und Downloads ──────────────────────────────────────────────────


async def test_fehlend_als_json_txt_und_zip(db, chemie):
    await _begriff(db, _n("Da"), chemie)
    await _begriff(db, _n("Doppelt"), chemie, metadata_={"fassung": "A"})
    await _begriff(db, _n("Doppelt"), chemie, metadata_={"fassung": "B"})
    cid = await _curriculum(db, chemie, {
        "Redox": [[_n("Fehlt"), _n("Da"), _n("Doppelt")], [_n("fehlt"), {"name": _n("Neu"), "fassung": "X"}]],
        "Säuren": [[_n("Fehlt")]],
    })
    liste = await fehlende_begriffe_im_curriculum(cid, format="json", db=db, user=_user("teacher"))
    assert liste["fehlend"] == [
        {"name": _n("Fehlt"), "fassung": None, "anzahl": 3, "kapitel": ["Redox", "Säuren"]},
        {"name": _n("Neu"), "fassung": "X", "anzahl": 1, "kapitel": ["Redox"]},
    ]
    assert [b["name"] for b in liste["mehrdeutig"]] == [_n("Doppelt")]

    txt = await fehlende_begriffe_im_curriculum(cid, format="txt", db=db, user=_user("teacher"))
    text = txt.body.decode("utf-8")
    assert f"- {_n('Fehlt')} — 3× — Redox; Säuren" in text
    assert f"- {_n('Neu')} (X) — 1× — Redox" in text
    assert "Mehrdeutig" in text
    assert txt.headers["content-disposition"].startswith("attachment;")

    z = await fehlende_begriffe_im_curriculum(cid, format="zip", db=db, user=_user("teacher"))
    archiv = zipfile.ZipFile(io.BytesIO(z.body))
    namen = sorted(archiv.namelist())
    assert namen == sorted([f"{_n('Fehlt')}.md", f"{_n('Neu')} (X).md", "_Hinweise.txt"])
    geruest = archiv.read(f"{_n('Neu')} (X).md").decode("utf-8")
    assert "geruest: true" in geruest and "fassung: X" in geruest and "## Definition" in geruest
    assert f"fach: {chemie.name}" in geruest


async def test_gerueste_rundreise_ueber_den_import(db, chemie):
    """Leer eingespielt: abgewiesen, kein Stub. Ausgefüllt: ein ganz normaler Begriff — und
    das Curriculum findet ihn danach."""
    cid = await _curriculum(db, chemie, {"Redox": [[_n("Leer"), _n("Gefuellt")]]})
    z = await fehlende_begriffe_im_curriculum(cid, format="zip", db=db, user=_user("teacher"))
    archiv = zipfile.ZipFile(io.BytesIO(z.body))
    dateien = {n: archiv.read(n) for n in archiv.namelist()}
    gefuellt = f"{_n('Gefuellt')}.md"
    dateien[gefuellt] = dateien[gefuellt] + "Ein ausgefüllter Text.\n".encode("utf-8")

    bilanz = await seed.importiere(db, dateien, ohne_fachschaft=True)
    zustaende = {d.datei: d.zustand for d in bilanz.dateien}
    assert zustaende == {_n("Leer"): "uebergangen", _n("Gefuellt"): "neu"}
    assert any("Gerüst ohne Definition" in w for w in bilanz.warnungen)
    leer = (await db.execute(sa.select(ContextNode).where(ContextNode.title == _n("Leer")))).scalars().all()
    assert leer == []
    neu = (await db.execute(sa.select(ContextNode).where(ContextNode.title == _n("Gefuellt")))).scalar_one()
    assert "geruest" not in neu.metadata_ and STUB_MARKIERUNG not in neu.metadata_

    liste = await fehlende_begriffe_im_curriculum(cid, format="json", db=db, user=_user("teacher"))
    assert [b["name"] for b in liste["fehlend"]] == [_n("Leer")]


async def test_datei_ohne_definition_ohne_kennzeichnung_bleibt_stub(db, chemie):
    """Nur Gerüste werden abgewiesen — der übrige Import bleibt, wie er ist (E7 b)."""
    text = f"---\nknotentyp: begriff\ntitel: {_n('Stub')}\nfach: {chemie.slug}\n---\n\n## Definition\n\n"
    bilanz = await seed.importiere(db, {f"{_n('Stub')}.md": text.encode()}, ohne_fachschaft=True)
    assert [d.zustand for d in bilanz.dateien] == ["neu"]
    stub = (await db.execute(sa.select(ContextNode).where(ContextNode.title == _n("Stub")))).scalar_one()
    assert stub.metadata_[STUB_MARKIERUNG] is True


# ── Umbenennen (E12) ─────────────────────────────────────────────────────────


async def test_umbenennen_im_editor_behaelt_den_alten_namen(db, chemie):
    b = await _begriff(db, _n("Alt"), chemie)
    await aliase_modul.setze(db, b.id, [_n("Nebenname")])
    await update_node(b.id, ContextNodeUpdate(title=_n("Neu")), db=db, user=_user("admin", "teacher"))
    assert await aliase_modul.lade(db, b.id) == [_n("Nebenname"), _n("Alt")]

    # Mit mitgeschickten Aliasen: die gelten, der alte Titel kommt dazu; ein Alias, der jetzt
    # Titel ist, fällt weg.
    await update_node(b.id, ContextNodeUpdate(title=_n("Nebenname"), aliase=[_n("Nebenname"), "X"]),
                      db=db, user=_user("admin", "teacher"))
    assert await aliase_modul.lade(db, b.id) == ["X", _n("Neu")]


async def test_nur_schreibweise_geaendert_kein_alias(db, chemie):
    b = await _begriff(db, _n("Redoxreihe"), chemie)
    await update_node(b.id, ContextNodeUpdate(title=f"  {_n('REDOXREIHE')}"), db=db, user=_user("admin", "teacher"))
    assert await aliase_modul.lade(db, b.id) == []


async def test_umbenennen_in_meinen_bausteinen(db, chemie):
    b = await _begriff(db, _n("Vorher"), chemie)
    await verwalte_node(b.id, BausteinVerwalten(title=_n("Nachher")), db=db, user=_user("admin", "teacher"))
    assert await aliase_modul.lade(db, b.id) == [_n("Vorher")]


async def test_andere_typen_bekommen_keinen_alias(db, chemie):
    n = ContextNode(category="knowledge", content_type="methodenblatt", title=_n("Blatt"), status="active",
                    subject_id=chemie.id, read_scope="school", write_scope="school", content="x",
                    owner_pseudonym="lehrkraft-fehlend", metadata_={})
    db.add(n)
    await db.flush()
    await update_node(n.id, ContextNodeUpdate(title=_n("Blatt neu")), db=db, user=_user("admin", "teacher"))
    assert await aliase_modul.lade(db, n.id) == []


async def test_curriculum_findet_den_umbenannten_begriff(db, chemie):
    from app.context.router import get_curriculum

    b = await _begriff(db, _n("Ursprung"), chemie)
    cid = await _curriculum(db, chemie, {"K": [[_n("Ursprung")]]})
    await update_node(b.id, ContextNodeUpdate(title=_n("Umbenannt")), db=db, user=_user("admin", "teacher"))
    (a,) = (await get_curriculum(cid, db=db, user=_user("teacher")))["begriffe"]
    assert (a["zustand"], a["node_id"]) == ("gefunden", str(b.id))


def _datei(titel, fach, kennung, aliase=()):
    kopf = f"id: {kennung}\nknotentyp: begriff\ntitel: {titel}\nfach: {fach}\n"
    if aliase:
        kopf += f"aliase: [{', '.join(aliase)}]\n"
    return f"---\n{kopf}---\n\n## Definition\n\nText über {titel}.\n".encode("utf-8")


async def test_umbenennen_im_vault_bleibt_ueber_zwei_laeufe_stabil(db, chemie):
    kennung = f"q{TOKEN}-begriff"
    await seed.importiere(db, {"A.md": _datei(_n("Erster"), chemie.slug, kennung, [_n("Neben")])},
                          ohne_fachschaft=True)
    knoten = (await db.execute(sa.select(ContextNode).where(ContextNode.title == _n("Erster")))).scalar_one()

    # Im Vault umbenannt, dieselbe Kennung: alter Titel wird Alias.
    bilanz = await seed.importiere(db, {"A.md": _datei(_n("Zweiter"), chemie.slug, kennung, [_n("Neben")])},
                                   ohne_fachschaft=True)
    assert [d.zustand for d in bilanz.dateien] == ["aktualisiert"]
    await db.refresh(knoten)
    assert knoten.title == _n("Zweiter")
    assert await aliase_modul.lade(db, knoten.id) == [_n("Neben"), _n("Erster")]

    # Derselbe Stand noch einmal: unverändert — weder Handänderung noch Alias verloren.
    bilanz = await seed.importiere(db, {"A.md": _datei(_n("Zweiter"), chemie.slug, kennung, [_n("Neben")])},
                                   ohne_fachschaft=True)
    assert [d.zustand for d in bilanz.dateien] == ["unveraendert"]
    assert await aliase_modul.lade(db, knoten.id) == [_n("Neben"), _n("Erster")]

    # Und noch einmal umbenannt: beide früheren Titel bleiben.
    await seed.importiere(db, {"A.md": _datei(_n("Dritter"), chemie.slug, kennung, [_n("Neben")])},
                          ohne_fachschaft=True)
    assert await aliase_modul.lade(db, knoten.id) == [_n("Neben"), _n("Erster"), _n("Zweiter")]


async def test_fachbegriff_verliert_sein_fach_nicht(db, chemie):
    """Abnahme 15.11.2026: Der Baustein-Editor schickte `subject_id: null`, wenn keine eigene
    Fachschaft gewählt war — der umbenannte Begriff hatte danach kein Fach, und das Curriculum
    fand ihn unter keinem Namen."""
    from fastapi import HTTPException

    b = await _begriff(db, _n("MitFach"), chemie)
    with pytest.raises(HTTPException) as e:
        await update_node(b.id, ContextNodeUpdate(title=_n("Umbenannt"), subject_id=None),
                          db=db, user=_user("admin", "teacher"))
    assert e.value.status_code == 422
    await db.refresh(b)
    assert b.subject_id == chemie.id
