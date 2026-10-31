"""Export der Assistenten (0.27, Plan Schritt 2): Gesamtexport = Einzelexport.

Bis 0.27 ließ der ZIP-Export Auslöser-Beispiele weg, und gleichnamige Assistenten
überschrieben sich im ZIP. Kontext-Dokumente gehen nicht mit, stehen aber als Kommentar
im YAML. Erfordert TEST_DATABASE_URL.
"""
import io
import zipfile

import pytest
import pytest_asyncio
import sqlalchemy as sa
import yaml
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Assistant, AssistantDocument

pytestmark = pytest.mark.asyncio

PRAEFIX = "EXP "


@pytest_asyncio.fixture(autouse=True)
async def aufraeumen(async_engine):
    yield
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.name.like(f"{PRAEFIX}%")))
        await db.commit()


async def _anlegen(client, headers, **mehr):
    resp = await client.post("/assistants", json={
        "name": PRAEFIX + "Doppelt", "system_prompt": "P", "audience": "student",
        "trigger_examples": ["wie rechne ich das aus"], **mehr,
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _dateien(resp) -> dict[str, str]:
    assert resp.status_code == 200, resp.text
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        return {n: z.read(n).decode("utf-8") for n in z.namelist()}


async def test_zip_gleich_einzelexport_und_eindeutig(test_client, auth_headers, async_engine):
    a = await _anlegen(test_client, auth_headers)
    b = await _anlegen(test_client, auth_headers)
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        db.add(AssistantDocument(assistant_id=a["id"], filename="pse.md", mime_type="text/markdown",
                                 size_bytes=3, content="PSE"))
        await db.commit()

    dateien = _dateien(await test_client.get(
        "/admin/assistants/export-all", params={"audience": "student"}, headers=auth_headers))
    assert "exp-doppelt.yaml" in dateien
    assert f"exp-doppelt-{b['id']}.yaml" in dateien

    einzeln = await test_client.get(f"/assistants/{a['id']}/export", headers=auth_headers)
    assert dateien["exp-doppelt.yaml"] == einzeln.text
    daten = yaml.safe_load(einzeln.text)
    assert daten["metadata"]["trigger_examples"] == ["wie rechne ich das aus"]
    assert "#   - pse.md" in einzeln.text
    assert "exp-doppelt.yaml" in einzeln.headers["content-disposition"]

    # Rundreise: die Datei aus dem ZIP wieder einspielen — die Beispiele kommen mit.
    zurueck = await test_client.post("/assistants/import", headers=auth_headers, files={
        "file": ("exp.yaml", dateien[f"exp-doppelt-{b['id']}.yaml"].encode(), "application/x-yaml")})
    assert zurueck.status_code in (200, 201), zurueck.text
    assert zurueck.json()["trigger_examples"] == ["wie rechne ich das aus"]


async def test_filter_wie_die_liste(test_client, auth_headers):
    await _anlegen(test_client, auth_headers, name=PRAEFIX + "Nur Lehrkraft", audience="teacher")
    await _anlegen(test_client, auth_headers, name=PRAEFIX + "Schueler")
    dateien = _dateien(await test_client.get(
        "/admin/assistants/export-all", params={"audience": "student"}, headers=auth_headers))
    assert "exp-nur-lehrkraft.yaml" not in dateien
    assert "exp-schueler.yaml" in dateien
    alle = _dateien(await test_client.get("/admin/assistants/export-all", headers=auth_headers))
    assert "exp-nur-lehrkraft.yaml" in alle
