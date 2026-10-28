"""Bausteine am Assistenten (0.26, Plan „Rückfall-Assistenten“, Schritt 2, Migration 0093).

Über die echte Schnittstelle: Anlegen und Ändern (ohne Dubletten, unbekannte abgewiesen),
YAML-Rundreise, Import mit einem unbekannten Baustein und die Liste für den Editor.
Erfordert TEST_DATABASE_URL.
"""
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Assistant

pytestmark = pytest.mark.asyncio

PRAEFIX = "BST "
B = "begleiten_statt_loesen"


@pytest_asyncio.fixture(autouse=True)
async def aufraeumen(async_engine):
    yield
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.name.like(f"{PRAEFIX}%")))
        await db.commit()


async def _anlegen(client, headers, **mehr):
    return await client.post("/assistants", json={
        "name": PRAEFIX + "A", "system_prompt": "P", "audience": "student", **mehr,
    }, headers=headers)


async def test_vorgabe_leer_und_bereinigt(test_client, auth_headers):
    assert (await _anlegen(test_client, auth_headers)).json()["bausteine"] == []
    resp = await _anlegen(test_client, auth_headers, name=PRAEFIX + "B", bausteine=[B, f" {B}", ""])
    assert resp.status_code == 201, resp.text
    assert resp.json()["bausteine"] == [B]


async def test_unbekannt_abgewiesen(test_client, auth_headers):
    resp = await _anlegen(test_client, auth_headers, bausteine=["gibt_es_nicht"])
    assert resp.status_code == 422
    assert "gibt_es_nicht" in resp.json()["detail"]


async def test_aendern_und_leeren(test_client, auth_headers):
    a = (await _anlegen(test_client, auth_headers)).json()
    resp = await test_client.patch(f"/assistants/{a['id']}", json={"bausteine": [B]}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["bausteine"] == [B]
    resp = await test_client.patch(f"/assistants/{a['id']}", json={"description": "x"}, headers=auth_headers)
    assert resp.json()["bausteine"] == [B]
    resp = await test_client.patch(f"/assistants/{a['id']}", json={"bausteine": []}, headers=auth_headers)
    assert resp.json()["bausteine"] == []


async def test_yaml_rundreise_und_fremder_baustein(test_client, auth_headers):
    a = (await _anlegen(test_client, auth_headers, bausteine=[B])).json()
    export = await test_client.get(f"/assistants/{a['id']}/export", headers=auth_headers)
    assert "bausteine" in export.text
    resp = await test_client.post("/assistants/import",
                                  files={"file": ("a.yaml", export.content, "application/x-yaml")},
                                  headers=auth_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["bausteine"] == [B]
    yaml_text = (f"metadata:\n  name: {PRAEFIX}Fremd\n  audience: student\n"
                 f"config:\n  system_prompt: P\n  bausteine: [{B}, aus_neuerer_fassung]\n")
    resp = await test_client.post("/assistants/import",
                                  files={"file": ("a.yaml", yaml_text.encode(), "application/x-yaml")},
                                  headers=auth_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["bausteine"] == [B]
    assert any("aus_neuerer_fassung" in h for h in resp.json()["hinweise"])


async def test_liste_fuer_den_editor(test_client, auth_headers):
    resp = await test_client.get("/pedagogy/bausteine", headers=auth_headers)
    assert resp.status_code == 200
    assert B in [b["key"] for b in resp.json()["bausteine"]]
