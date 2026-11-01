"""Kosten und Kontext-Dokumente in der Assistentenliste (0.27, Plan Schritt 10, F7′/F9).

Die Schätzung rechnet mittlere Nachricht **plus** Prompt, Bausteine und Dokumente mal
Modellpreis; ohne bekannten Preis gibt es keine Zahl. Die Dokumente stehen mit Namen und
Größe in der Liste. Erfordert TEST_DATABASE_URL.
"""
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assistants import kosten as kosten_modul
from app.db.models import Assistant, AssistantDocument
from app.litellm.modell_eigenschaften import REFERENZ_NACHRICHT, Eigenschaften

pytestmark = pytest.mark.asyncio

PREIS_EIN, PREIS_AUS = 1e-6, 2e-6


@pytest_asyncio.fixture
async def assistenten(async_engine, monkeypatch):
    async def preise():
        return {"kosten-modell": Eigenschaften(preis_ein_usd=PREIS_EIN, preis_aus_usd=PREIS_AUS)}
    monkeypatch.setattr(kosten_modul, "alle_eigenschaften", preise)
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        mit = Assistant(name="KOS Mit Dokument", system_prompt="P" * 400, model="kosten-modell",
                        status="active", audience="all", scope="all", creator_role="admin")
        ohne_preis = Assistant(name="KOS Ohne Preis", system_prompt="P", model="unbekannt",
                               status="active", audience="all", scope="all", creator_role="admin")
        db.add_all([mit, ohne_preis])
        await db.flush()
        db.add(AssistantDocument(assistant_id=mit.id, filename="PSE mit Schulwerten.md",
                                 mime_type="text/markdown", size_bytes=4000, content="x" * 4000))
        await db.commit()
    yield
    async with fabrik() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.name.like("KOS %")))
        await db.commit()


async def test_liste_nennt_kosten_und_dokumente(test_client, auth_headers, assistenten):
    resp = await test_client.get("/assistants", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    je_name = {a["name"]: a for a in resp.json()["items"] if a["name"].startswith("KOS ")}

    mit = je_name["KOS Mit Dokument"]
    ein, aus = REFERENZ_NACHRICHT
    erwartet = (ein + 400 // 4 + 4000 // 4) * PREIS_EIN + aus * PREIS_AUS
    assert mit["usd_je_nachricht"] == pytest.approx(erwartet)
    assert mit["usd_dokumente"] == pytest.approx(1000 * PREIS_EIN)
    assert mit["dokumente"] == [{"name": "PSE mit Schulwerten.md", "groesse_bytes": 4000}]

    ohne = je_name["KOS Ohne Preis"]
    assert ohne["usd_je_nachricht"] is None and ohne["usd_dokumente"] is None
    assert ohne["dokumente"] == []
