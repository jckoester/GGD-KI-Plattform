"""Admin-Felder am Assistenten nimmt der Server nur von Admins an (0.27).

Bausteine, „Darunter anbieten“ (`fallbacks`) und Operator-Fächer sieht im Editor nur, wer Admin
ist. Bis 0.27 hielt der Server das nicht: Über die Schnittstelle setzte eine Lehrkraft sie an
eigenen Assistenten. Jetzt übergeht er die Eingabe wie bei `sort_order`. Erfordert
TEST_DATABASE_URL.
"""
import pytest
import pytest_asyncio
import sqlalchemy as sa
import yaml
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Assistant

pytestmark = pytest.mark.asyncio

PRAEFIX = "ADF "
B = "begleiten_statt_loesen"


@pytest_asyncio.fixture(autouse=True)
async def aufraeumen(async_engine):
    yield
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.name.like(f"{PRAEFIX}%")))
        await db.commit()


async def _anlegen(client, headers, name):
    resp = await client.post("/assistants", json={
        "name": PRAEFIX + name, "system_prompt": "P", "audience": "student", "bausteine": [B],
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_lehrkraft_setzt_keine_bausteine(test_client, auth_headers_teacher2):
    a = await _anlegen(test_client, auth_headers_teacher2, "L")
    assert a["bausteine"] == []
    resp = await test_client.patch(f"/assistants/{a['id']}", json={"bausteine": [B], "description": "x"},
                                   headers=auth_headers_teacher2)
    assert resp.status_code == 200, resp.text
    assert resp.json()["bausteine"] == []
    assert resp.json()["description"] == "x"      # der Rest der Änderung gilt


async def test_admin_darf(test_client, auth_headers):
    assert (await _anlegen(test_client, auth_headers, "A"))["bausteine"] == [B]


async def test_import_einer_lehrkraft_nennt_was_fehlt(test_client, auth_headers_teacher2):
    datei = yaml.safe_dump({"metadata": {"name": PRAEFIX + "Imp", "audience": "student"},
                            "config": {"system_prompt": "P", "bausteine": [B]}}, allow_unicode=True)
    resp = await test_client.post("/assistants/import", headers=auth_headers_teacher2,
                                  files={"file": ("a.yaml", datei.encode(), "application/x-yaml")})
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["bausteine"] == []
    assert any("nur Admins" in h for h in resp.json()["hinweise"])
