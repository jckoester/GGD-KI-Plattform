"""Verwaltungsereignisse landen im Audit-Log (0.28, Plan Schritt 5, erster Durchgang).

Über die echte Schnittstelle: Freigabe, Aktivieren, Deaktivieren, Löschen eines Assistenten,
Site-Text, Sitzungen beenden. Erfordert TEST_DATABASE_URL.
"""
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Assistant

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def fabrik(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def _ereignisse(fabrik, ziel_typ, ziel_id):
    async with fabrik() as db:
        return [(e, r, p) for e, r, p in (await db.execute(sa.text(
            "SELECT event_type, actor_role, payload FROM audit_log"
            " WHERE target_type = :t AND target_id = :i ORDER BY id"),
            {"t": ziel_typ, "i": str(ziel_id)})).all()]


async def test_lebenslauf_eines_assistenten(test_client, auth_headers, fabrik):
    async with fabrik() as db:
        a = Assistant(name="AUD Lebenslauf", system_prompt="P", model="", status="pending_review",
                      audience="student", scope="all_students", creator_role="teacher", created_by="jemand")
        db.add(a)
        await db.commit()
        aid = a.id
    for pfad in ("approve", "deactivate", "activate", "deactivate"):
        resp = await test_client.post(f"/admin/assistants/{aid}/{pfad}", headers=auth_headers)
        assert resp.status_code == 200, (pfad, resp.text)
    resp = await test_client.delete(f"/assistants/{aid}", headers=auth_headers)
    assert resp.status_code == 204, resp.text

    ereignisse = await _ereignisse(fabrik, "assistant", aid)
    assert [e for e, _, _ in ereignisse] == [
        "assistant_approved", "assistant_deactivated", "assistant_activated", "assistant_deactivated",
        "assistant_deleted"]
    assert ereignisse[0][1] == "admin"
    assert ereignisse[0][2] == {"audience": "student", "scope": "all_students"}


async def test_site_text_und_sitzungen(test_client, auth_headers, fabrik):
    resp = await test_client.put("/admin/site-texts/impressum", headers=auth_headers,
                                 json={"content": "Impressum für den Test"})
    if resp.status_code == 404:
        pytest.skip("Site-Text-Key in dieser Konfiguration nicht vorhanden")
    assert resp.status_code == 200, resp.text
    eintraege = await _ereignisse(fabrik, "site_text", "impressum")
    assert eintraege and eintraege[-1][0] == "site_text_changed"
    assert "Impressum für den Test" not in str(eintraege[-1][2])

    async with fabrik() as db:
        await db.execute(sa.text(
            "INSERT INTO pseudonym_audit (pseudonym, role, roles) VALUES ('audit-sitzung', 'student', '[\"student\"]')"
            " ON CONFLICT (pseudonym) DO NOTHING"))
        await db.commit()
    resp = await test_client.post("/admin/users/audit-sitzung/revoke-sessions", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert (await _ereignisse(fabrik, "user", "audit-sitzung"))[-1][0] == "user_sessions_revoked"
