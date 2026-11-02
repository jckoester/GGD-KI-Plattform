"""Vorschau über die echte Schnittstelle (0.29, Schritt 1, ADR-016 Ansatz C).

Ein echtes Vorschau-Token (Rolle `student`, echte Rollen im Merkmal) gegen dieselben Wege
wie die Lehrkraft: Was über Mitgliedschaft und Eigentum entscheidet, muss in der Vorschau
die Schülersicht zeigen. Erfordert TEST_DATABASE_URL.
"""
import time
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.vorschau import Vorschau
from app.db.models import Assistant, ContextNode, Group, GroupMembership, Subject
from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def welt(async_engine):
    """Lehrkraft 1 unterrichtet die Gruppe G und hat einen privaten Knoten, einen privaten
    Assistenten und einen Entwurf."""
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    kennung = uuid.uuid4().hex[:8]
    async with fabrik() as db:
        fach = Subject(slug=f"vfach-{kennung}", name="Vorschaufach")
        db.add(fach)
        await db.flush()
        g = Group(name="Vorschau 9a", slug=f"v-{kennung}", type="teaching_group",
                  subject_id=fach.id)
        andere = Group(name="Vorschau 10b", slug=f"v2-{kennung}", type="teaching_group",
                       subject_id=fach.id)
        db.add_all([g, andere])
        await db.flush()
        for gruppe in (g, andere):
            db.add(GroupMembership(group_id=gruppe.id, pseudonym=TEACHER1_PSEUDO,
                                   role_in_group="teacher", herkunft="eigen"))
        knoten = ContextNode(
            category="concept", content_type="begriff", title="Private Notiz der Lehrkraft",
            content="geheim",
            owner_pseudonym=TEACHER1_PSEUDO, read_scope="private", write_scope="private",
            status="active",
        )
        # Eigener Jahresplan in der **anderen** Gruppe: In der Vorschau gilt nur G als
        # eigene Gruppe — ohne Sonderregel erschiene „Vorschau 10b“ als frühere Gruppe.
        plan = ContextNode(
            category="artifact", content_type="jahresplan", title="Jahresplan 10b",
            content="", owner_pseudonym=TEACHER1_PSEUDO, read_scope="group",
            write_scope="group", read_scope_group_id=andere.id,
            write_scope_group_id=andere.id, status="active",
        )
        db.add(plan)
        privat = Assistant(name=f"Privat {kennung}", system_prompt="P", status="active",
                           audience="all", scope="private", created_by=TEACHER1_PSEUDO,
                           creator_role="teacher", model="")
        db.add_all([knoten, privat])
        await db.commit()
        return {"g": g.id, "andere": andere.id, "knoten": str(knoten.id), "privat": privat.id}


def _kopf(jwt_service, *, vorschau_gruppe=None, normal=False):
    if normal:
        token, _ = jwt_service.issue(pseudonym=TEACHER1_PSEUDO, roles=["teacher"], grade=None)
    else:
        jetzt = int(time.time())
        token, _ = jwt_service.issue(
            pseudonym=TEACHER1_PSEUDO, roles=["student"], grade="9",
            preview=Vorschau(echte_rollen=["teacher"], gruppe_id=vorschau_gruppe,
                             beginn=jetzt, sitzung_ablauf=jetzt + 3600),
            exp=jetzt + 3600,
        )
    return {"Cookie": f"session={token}"}


async def test_eigene_gruppen_nur_die_gewaehlte(test_client, jwt_service, welt):
    normal = await test_client.get("/groups/me", headers=_kopf(jwt_service, normal=True))
    assert {welt["g"], welt["andere"]} <= {x["id"] for x in normal.json()["items"]}
    vorschau = await test_client.get("/groups/me",
                                     headers=_kopf(jwt_service, vorschau_gruppe=welt["g"]))
    assert [x["id"] for x in vorschau.json()["items"]] == [welt["g"]]


async def test_gruppe_aendern_nur_als_lehrkraft(test_client, jwt_service, welt):
    """Diese Wege prüfen nur die Mitgliedschaft als Lehrkraft, keine Rolle — vor 0.29 wären
    sie in der Vorschau offen gewesen."""
    pfad = f"/groups/teaching/{welt['g']}/name"
    vorschau = await test_client.patch(pfad, json={"display_name": "X"},
                                       headers=_kopf(jwt_service, vorschau_gruppe=welt["g"]))
    assert vorschau.status_code == 403
    normal = await test_client.patch(pfad, json={"display_name": "Mathe 9a"},
                                     headers=_kopf(jwt_service, normal=True))
    assert normal.status_code == 200, normal.text


async def test_privater_knoten_der_lehrkraft(test_client, jwt_service, welt):
    pfad = f"/context/nodes/{welt['knoten']}"
    assert (await test_client.get(pfad, headers=_kopf(jwt_service, normal=True))).status_code == 200
    vorschau = await test_client.get(pfad, headers=_kopf(jwt_service, vorschau_gruppe=welt["g"]))
    assert vorschau.status_code in (403, 404)


async def test_eigener_privater_assistent(test_client, jwt_service, welt):
    normal = await test_client.get("/assistants", headers=_kopf(jwt_service, normal=True))
    assert welt["privat"] in {a["id"] for a in normal.json()["items"]}
    kopf = _kopf(jwt_service, vorschau_gruppe=welt["g"])
    vorschau = await test_client.get("/assistants", headers=kopf)
    assert vorschau.status_code == 200
    assert welt["privat"] not in {a["id"] for a in vorschau.json()["items"]}
    assert (await test_client.get(f"/assistants/{welt['privat']}", headers=kopf)).status_code == 403


async def test_archiv_bleibt_leer(test_client, jwt_service, welt):
    normal = await test_client.get("/archive/groups", headers=_kopf(jwt_service, normal=True))
    assert welt["andere"] not in {x["group_id"] for x in normal.json()["items"]}
    vorschau = await test_client.get("/archive/groups",
                                     headers=_kopf(jwt_service, vorschau_gruppe=welt["g"]))
    assert vorschau.status_code == 200
    assert vorschau.json()["items"] == []


async def test_vorschau_ueberdauert_keine_anfrage(test_client, jwt_service, welt):
    """Erst Vorschau, dann normal im selben Task: Die zweite Anfrage sieht wieder alles."""
    await test_client.get("/groups/me", headers=_kopf(jwt_service, vorschau_gruppe=welt["g"]))
    normal = await test_client.get("/groups/me", headers=_kopf(jwt_service, normal=True))
    assert {welt["g"], welt["andere"]} <= {x["id"] for x in normal.json()["items"]}


# ── Schreibsperre (Schritt 3) ───────────────────────────────────────────────────

@pytest.mark.parametrize("methode,pfad,rumpf", [
    ("PATCH", "/preferences", {"ui_level": 1}),
    ("POST", "/tokens", {"name": "x"}),
    ("POST", "/groups/join", {"code": "ABCDEF"}),
    ("POST", "/neuigkeiten/0.28-audit-log/gelesen", None),
    ("POST", "/artifacts/document", {"title": "x", "content": "y"}),
    ("GET", "/auth/step-up?action=read&resource_id=00000000-0000-0000-0000-0000000000aa", None),
])
async def test_gesperrt(test_client, jwt_service, welt, methode, pfad, rumpf):
    antwort = await test_client.request(methode, pfad, json=rumpf,
                                        headers=_kopf(jwt_service, vorschau_gruppe=welt["g"]))
    assert antwort.status_code == 403, antwort.text
    assert antwort.json()["detail"] == "In der Vorschau lässt sich nichts ändern."


async def test_einstellungen_ausserhalb_der_vorschau_offen(test_client, jwt_service, welt):
    antwort = await test_client.patch("/preferences", json={"ui_level": 3},
                                      headers=_kopf(jwt_service, normal=True))
    assert antwort.status_code == 200, antwort.text


async def test_rueckmeldung_und_suche_bleiben_offen(test_client, jwt_service, welt):
    kopf = _kopf(jwt_service, vorschau_gruppe=welt["g"])
    meldung = await test_client.post("/feedback", headers=kopf, json={
        "category": "bug", "content": "Aus der Vorschau gemeldet, ein Test.",
        "app_version": "0.29.0"})
    assert meldung.status_code == 201, meldung.text
    suche = await test_client.post("/context/search", headers=kopf, json={"query": "Energie"})
    assert suche.status_code != 403, suche.text
