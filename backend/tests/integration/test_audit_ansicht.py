"""Audit-Log lesen über die Schnittstelle (0.28, Plan Schritt 6). Erfordert TEST_DATABASE_URL."""
from datetime import datetime, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.audit import eintrag

pytestmark = pytest.mark.asyncio

AKTEUR = "ansicht-akteur-%_x"  # mit LIKE-Sonderzeichen: der Anfang muss wörtlich zählen


@pytest_asyncio.fixture
async def eintraege(async_engine):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    zeilen = [
        eintrag("admin", "guardrail_changed", akteur=AKTEUR, rolle="admin"),
        eintrag("admin", "site_text_changed", akteur=AKTEUR, rolle="admin", ziel=("site_text", "impressum")),
        eintrag("auth", "login_failed", daten={"grund": "anmeldedaten"}),
    ]
    zeilen[0].occurred_at = datetime(2026, 10, 30, 23, 30, tzinfo=timezone.utc)  # 31.10. 00:30 in Berlin (Winterzeit)
    zeilen[1].occurred_at = datetime(2026, 10, 31, 23, 30, tzinfo=timezone.utc)  # 01.11. 00:30 in Berlin
    zeilen[2].occurred_at = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
    async with fabrik() as db:
        await db.execute(sa.text("SELECT set_config('audit.aufraeumen', 'on', true)"))
        await db.execute(sa.text("DELETE FROM audit_log"))
        db.add_all(zeilen)
        await db.commit()
    yield
    async with fabrik() as db:
        await db.execute(sa.text("SELECT set_config('audit.aufraeumen', 'on', true)"))
        await db.execute(sa.text("DELETE FROM audit_log"))
        await db.commit()


async def _liste(client, headers, **params):
    resp = await client.get("/admin/audit", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_neueste_zuerst_mit_bezeichnung(test_client, auth_headers, eintraege):
    daten = await _liste(test_client, auth_headers)
    assert daten["gesamt"] == 3
    assert [e["event_type"] for e in daten["eintraege"]] == [
        "login_failed", "site_text_changed", "guardrail_changed"]
    assert daten["eintraege"][0]["bezeichnung"] == "Anmeldung gescheitert"
    assert daten["eintraege"][0]["payload"] == {"grund": "anmeldedaten"}


async def test_filter(test_client, auth_headers, eintraege):
    assert (await _liste(test_client, auth_headers, kategorie="auth"))["gesamt"] == 1
    assert (await _liste(test_client, auth_headers, ereignis="guardrail_changed"))["gesamt"] == 1
    assert (await _liste(test_client, auth_headers, akteur="ansicht-akteur-%"))["gesamt"] == 2
    assert (await _liste(test_client, auth_headers, akteur="ansicht-akteurX"))["gesamt"] == 0
    # Tage in Ortszeit: 23:30 UTC am 30.10. ist schon der 31.10.
    tag = await _liste(test_client, auth_headers, von="2026-10-31", bis="2026-10-31")
    assert [e["event_type"] for e in tag["eintraege"]] == ["guardrail_changed"]
    assert (await _liste(test_client, auth_headers, von="2026-11-01"))["gesamt"] == 2


async def test_seiten(test_client, auth_headers, eintraege):
    seite2 = await _liste(test_client, auth_headers, pro_seite=2, seite=2)
    assert seite2["gesamt"] == 3
    assert [e["event_type"] for e in seite2["eintraege"]] == ["guardrail_changed"]


async def test_nicht_fuer_lehrkraefte(test_client, auth_headers_teacher2, eintraege):
    resp = await test_client.get("/admin/audit", headers=auth_headers_teacher2)
    assert resp.status_code == 403
