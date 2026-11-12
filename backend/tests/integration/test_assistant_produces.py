"""Angabe „stellt her“ am Assistenten (0.40, Päckchen AM; Alembic 0102).

Vorbelegung aus den Fähigkeiten, Liste der Arten, Anlegen und Ändern über die API, und die
Kopie des Stundenassistenten. Export und Import: `tests/unit/test_assistant_admin_api.py`;
Seed: `test_seed_assistants.py`. Erfordert TEST_DATABASE_URL.
"""
import importlib.util
import json
from pathlib import Path

import psycopg2
import pytest

pytestmark = pytest.mark.asyncio

PRAEFIX = "PRODUCES "
_MIGRATION = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0102_assistant_produces.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("migration_0102", _MIGRATION)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture
def conn(db_url, run_migrations):
    verbindung = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield verbindung
    verbindung.rollback()
    with verbindung.cursor() as cur:
        cur.execute("DELETE FROM assistants WHERE name LIKE %s", (f"{PRAEFIX}%",))
    verbindung.commit()
    verbindung.close()


def _einfuegen(cur, name, tool_groups, produces="[]"):
    cur.execute(
        "INSERT INTO assistants (name, system_prompt, model, scope, status, audience,"
        " tool_groups, produces, created_by, creator_role)"
        " VALUES (%s, 'P', '', 'teachers', 'active', 'teacher', %s::jsonb, %s::jsonb,"
        " 'admin-produces', 'admin') RETURNING id",
        (name, json.dumps(tool_groups), produces),
    )
    return cur.fetchone()[0]


def test_vorbelegung_aus_den_faehigkeiten(conn):
    """Bild → image, Stunde → lesson_plan, Jahr → year_plan; Reihenfolge der Liste, nicht der Fähigkeiten."""
    with conn.cursor() as cur:
        ids = {
            "alles": _einfuegen(cur, f"{PRAEFIX}alles", ["planning", "context_search", "image_generation"]),
            "stunde": _einfuegen(cur, f"{PRAEFIX}stunde", ["lesson_planning"]),
            "schueler": _einfuegen(cur, f"{PRAEFIX}schueler", ["student_planning"]),
            "nichts": _einfuegen(cur, f"{PRAEFIX}nichts", []),
        }
        # In derselben Transaktion, die die Fixture zurückrollt: Das UPDATE trifft alle Zeilen.
        cur.execute(_migration().vorbelegung_sql())
        cur.execute("SELECT id, produces FROM assistants WHERE id = ANY(%s)", (list(ids.values()),))
        stand = dict(cur.fetchall())
    conn.rollback()

    assert stand[ids["alles"]] == ["image", "year_plan"]
    assert stand[ids["stunde"]] == ["lesson_plan"]
    assert stand[ids["schueler"]] == []
    assert stand[ids["nichts"]] == []


async def test_liste_der_arten(test_client, auth_headers_teacher2):
    resp = await test_client.get("/assistants/produktarten", headers=auth_headers_teacher2)
    assert resp.status_code == 200, resp.text
    arten = resp.json()
    assert [a["id"] for a in arten] == ["image", "diagram", "document", "lesson_plan", "year_plan"]
    assert arten[0] == {"id": "image", "marke": "erstellt Bilder", "filter": "Bilder",
                        "faehigkeit": "image_generation"}


async def test_anlegen_und_aendern(test_client, auth_headers_teacher2, conn):
    """Auch eine Lehrkraft setzt die Angabe — sie ist eine Beschriftung, keine Fähigkeit."""
    resp = await test_client.post("/assistants", headers=auth_headers_teacher2, json={
        "name": f"{PRAEFIX}Arbeitsblätter", "system_prompt": "P",
        "produces": ["document", "diagram", "document"],
    })
    assert resp.status_code == 201, resp.text
    a = resp.json()
    assert a["produces"] == ["diagram", "document"]

    resp = await test_client.patch(f"/assistants/{a['id']}", headers=auth_headers_teacher2,
                                   json={"produces": []})
    assert resp.status_code == 200, resp.text
    assert resp.json()["produces"] == []

    liste = (await test_client.get("/assistants", headers=auth_headers_teacher2)).json()["items"]
    assert next(x for x in liste if x["id"] == a["id"])["produces"] == []


async def test_unbekannte_angabe_wird_abgewiesen(test_client, auth_headers_teacher2, conn):
    resp = await test_client.post("/assistants", headers=auth_headers_teacher2, json={
        "name": f"{PRAEFIX}Falsch", "system_prompt": "P", "produces": ["zeitreise"],
    })
    assert resp.status_code == 422
    assert "zeitreise" in resp.json()["detail"]


async def test_eigener_stundenassistent_folgt_der_vorlage(test_client, auth_headers_teacher2, conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM assistants WHERE created_by = 'teacher2-pseudo'"
                    " AND name LIKE 'Mein Stundenassistent%%'")
        _einfuegen(cur, f"{PRAEFIX}Stundenentwurf", ["lesson_planning"], '["lesson_plan"]')
    conn.commit()

    resp = await test_client.post("/assistants/eigener-stundenassistent", headers=auth_headers_teacher2)
    assert resp.status_code == 201, resp.text
    try:
        assert resp.json()["produces"] == ["lesson_plan"]
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM assistants WHERE id = %s", (resp.json()["id"],))
        conn.commit()
