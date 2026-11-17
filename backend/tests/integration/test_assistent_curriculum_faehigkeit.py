"""Fähigkeit „Curriculum-Entwurf“ nur durch Admins und nur für Lehrkräfte (0.46, Teil B, Schritt 6).

Den Curriculum-Assistenten braucht die Fachschaft — geseedet oder von einem Admin angelegt.
Eine Lehrkraft gibt die Fähigkeit (und die Marke „erstellt Curricula“) keinem eigenen Assistenten:
Der Server übergeht sie wie die Admin-Felder. Und auch ein Admin gibt sie nur einem Assistenten
mit Zielgruppe Lehrkräfte — sonst reichte er ihn an Schüler:innen weiter. Erfordert
TEST_DATABASE_URL.
"""
import pytest
import pytest_asyncio
import sqlalchemy as sa
import yaml
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Assistant

pytestmark = pytest.mark.asyncio

PRAEFIX = "CURF "
F = "curriculum_planning"


@pytest_asyncio.fixture(autouse=True)
async def aufraeumen(async_engine):
    yield
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.name.like(f"{PRAEFIX}%")))
        await db.commit()


async def _anlegen(client, headers, name, audience="teacher", **kw):
    return await client.post("/assistants", headers=headers, json={
        "name": PRAEFIX + name, "system_prompt": "P", "audience": audience,
        "tool_groups": [F, "planning"], "produces": ["curriculum", "document"], **kw})


async def test_lehrkraft_bekommt_die_faehigkeit_nicht(test_client, auth_headers_teacher2):
    resp = await _anlegen(test_client, auth_headers_teacher2, "L")
    assert resp.status_code == 201, resp.text
    a = resp.json()
    assert a["tool_groups"] == ["planning"] and a["produces"] == ["document"]

    resp = await test_client.patch(f"/assistants/{a['id']}", headers=auth_headers_teacher2,
                                   json={"tool_groups": [F], "produces": ["curriculum"], "description": "x"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["tool_groups"] in (None, []) and resp.json()["produces"] == []
    assert resp.json()["description"] == "x"


async def test_admin_nur_mit_zielgruppe_lehrkraefte(test_client, auth_headers):
    for audience in ("student", "all"):
        resp = await _anlegen(test_client, auth_headers, f"S{audience}", audience=audience)
        assert resp.status_code == 422 and "Lehrkräfte" in resp.json()["detail"]

    resp = await _anlegen(test_client, auth_headers, "A")
    assert resp.status_code == 201, resp.text
    a = resp.json()
    assert F in a["tool_groups"] and "curriculum" in a["produces"]

    # Später die Zielgruppe wechseln geht ebenso wenig.
    resp = await test_client.patch(f"/assistants/{a['id']}", headers=auth_headers, json={"audience": "all"})
    assert resp.status_code == 422


async def test_import_einer_lehrkraft_uebergeht_sie(test_client, auth_headers_teacher2, auth_headers):
    datei = yaml.safe_dump({"metadata": {"name": PRAEFIX + "Imp", "audience": "teacher"},
                            "config": {"system_prompt": "P", "tool_groups": [F]}}, allow_unicode=True)
    resp = await test_client.post("/assistants/import", headers=auth_headers_teacher2,
                                  files={"file": ("a.yaml", datei.encode(), "application/x-yaml")})
    assert resp.status_code in (200, 201), resp.text
    assert F not in (resp.json()["tool_groups"] or [])
    assert any("Curriculum-Entwurf" in h for h in resp.json()["hinweise"])

    schueler = yaml.safe_dump({"metadata": {"name": PRAEFIX + "ImpS", "audience": "student"},
                               "config": {"system_prompt": "P", "tool_groups": [F]}}, allow_unicode=True)
    resp = await test_client.post("/assistants/import", headers=auth_headers,
                                  files={"file": ("a.yaml", schueler.encode(), "application/x-yaml")})
    assert resp.status_code == 422


async def test_pruefen_gehoert_zur_faehigkeit_und_schreibt_nicht():
    """Der Prüflauf (Arbeitsanweisung 16.11.) ist Teil der Fähigkeit und keine wirkende Funktion."""
    import app.context.curriculum_tools  # noqa: F401 — registriert
    from app.chat.tools import TOOL_REGISTRY

    pruefen = TOOL_REGISTRY["preview_curriculum_operations"]
    assert F in pruefen.groups and pruefen.writes is False
    assert TOOL_REGISTRY["apply_curriculum_operations"].writes is True
    assert (pruefen.definition["function"]["parameters"]["properties"]["operations"]
            is TOOL_REGISTRY["apply_curriculum_operations"].definition["function"]["parameters"]["properties"]["operations"])
