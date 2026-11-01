"""Urheber in der Assistenten-Freigabe (0.27, Plan Schritt 7, F4).

Die Warteschlange `/admin/assistants/pending` nennt das Stundenplan-Kürzel der einreichenden
Lehrkraft, falls hinterlegt — sonst nichts. Erfordert TEST_DATABASE_URL.
"""
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Assistant

pytestmark = pytest.mark.asyncio

MIT, OHNE = "urheber-mit-kuerzel", "urheber-ohne-kuerzel"


@pytest_asyncio.fixture
async def eingereicht(async_engine):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        for wer in (MIT, OHNE):
            db.add(Assistant(name=f"URH {wer}", system_prompt="P", model="", status="pending_review",
                             audience="student", scope="all_students", created_by=wer, creator_role="teacher"))
        await db.execute(sa.text(
            "INSERT INTO user_preferences (pseudonym, preferences) VALUES (:p, '{\"webuntis_kuerzel\": \"AK\"}') "
            "ON CONFLICT (pseudonym) DO UPDATE SET preferences = EXCLUDED.preferences"), {"p": MIT})
        await db.commit()
    yield
    async with fabrik() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.name.like("URH %")))
        await db.execute(sa.text("DELETE FROM user_preferences WHERE pseudonym = :p"), {"p": MIT})
        await db.commit()


async def test_warteschlange_nennt_das_kuerzel(test_client, auth_headers, eingereicht):
    resp = await test_client.get("/admin/assistants/pending", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    je_name = {a["name"]: a["urheber_kuerzel"] for a in resp.json()["items"] if a["name"].startswith("URH ")}
    assert je_name == {f"URH {MIT}": "AK", f"URH {OHNE}": None}
