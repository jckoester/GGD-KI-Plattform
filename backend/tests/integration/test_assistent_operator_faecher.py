"""Fächerkreis für Operatoren am Assistenten (Päckchen AF, Schritt 2, Migration 0091).

Über die echte Schnittstelle: Anlegen und Ändern (Slugs klein, ohne Dubletten, unbekannte
abgewiesen), YAML-Rundreise und Import mit einem Fach, das es hier nicht gibt.
Erfordert TEST_DATABASE_URL.
"""
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Assistant, Subject

pytestmark = pytest.mark.asyncio

PRAEFIX = "OPF "
FAECHER = {"opf-biologie": "OPF Biologie", "opf-chemie": "OPF Chemie"}


@pytest_asyncio.fixture(autouse=True)
async def faecher(async_engine):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        for slug, name in FAECHER.items():
            if not (await db.execute(sa.select(Subject.id).where(Subject.slug == slug))).first():
                db.add(Subject(name=name, slug=slug))
        await db.commit()
    yield
    async with fabrik() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.name.like(f"{PRAEFIX}%")))
        await db.commit()


async def _anlegen(client, headers, **mehr):
    return await client.post("/assistants", json={
        "name": PRAEFIX + "NW", "system_prompt": "P", "audience": "student", **mehr,
    }, headers=headers)


async def test_vorgabe_ist_leer(test_client, auth_headers):
    resp = await _anlegen(test_client, auth_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["operator_faecher"] == []


async def test_anlegen_bereinigt(test_client, auth_headers):
    resp = await _anlegen(test_client, auth_headers,
                          operator_faecher=[" OPF-Biologie", "opf-chemie", "opf-biologie", ""])
    assert resp.status_code == 201, resp.text
    assert resp.json()["operator_faecher"] == ["opf-biologie", "opf-chemie"]


async def test_unbekanntes_fach_wird_abgewiesen(test_client, auth_headers):
    resp = await _anlegen(test_client, auth_headers, operator_faecher=["opf-biologie", "gibt-es-nicht"])
    assert resp.status_code == 422
    assert "gibt-es-nicht" in resp.json()["detail"]


async def test_aendern_und_leeren(test_client, auth_headers):
    a = (await _anlegen(test_client, auth_headers)).json()
    resp = await test_client.patch(f"/assistants/{a['id']}", json={"operator_faecher": ["opf-chemie"]},
                                   headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["operator_faecher"] == ["opf-chemie"]
    # Ohne das Feld bleibt es stehen …
    resp = await test_client.patch(f"/assistants/{a['id']}", json={"description": "x"}, headers=auth_headers)
    assert resp.json()["operator_faecher"] == ["opf-chemie"]
    # … mit leerer Liste ist es aus.
    resp = await test_client.patch(f"/assistants/{a['id']}", json={"operator_faecher": []}, headers=auth_headers)
    assert resp.json()["operator_faecher"] == []


async def test_yaml_rundreise(test_client, auth_headers):
    a = (await _anlegen(test_client, auth_headers, operator_faecher=["opf-biologie", "opf-chemie"])).json()
    export = await test_client.get(f"/assistants/{a['id']}/export", headers=auth_headers)
    assert export.status_code == 200
    assert "operator_faecher" in export.text
    resp = await test_client.post("/assistants/import",
                                  files={"file": ("a.yaml", export.content, "application/x-yaml")},
                                  headers=auth_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["operator_faecher"] == ["opf-biologie", "opf-chemie"]
    assert resp.json()["hinweise"] == []


async def test_import_uebergeht_fremdes_fach(test_client, auth_headers):
    yaml_text = (
        "metadata:\n"
        f"  name: {PRAEFIX}Fremd\n"
        "  audience: student\n"
        "config:\n"
        "  system_prompt: P\n"
        "  operator_faecher: [opf-chemie, nwt-anderswo]\n"
    )
    resp = await test_client.post("/assistants/import",
                                  files={"file": ("a.yaml", yaml_text.encode(), "application/x-yaml")},
                                  headers=auth_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["operator_faecher"] == ["opf-chemie"]
    assert any("nwt-anderswo" in h for h in resp.json()["hinweise"])
