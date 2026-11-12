"""Die Suche der Bibliothek blendet die Unterrichtsplanung aus — der Chat nicht (0.40, Päckchen AM).

`exclude_planning` setzt nur die Suchseite (`knowledge/search`). Ohne den Schalter — so suchen
der Suchknopf und das `@` im Chat — kommt die Stunde weiter. Die Werkzeug-Suche des Assistenten
(`context_search`) baut ihr Profil selbst und kennt den Schalter nicht (Wächter in
`tests/unit/test_planung_bibliothek.py`). Erfordert TEST_DATABASE_URL.
"""
from unittest.mock import AsyncMock, patch

import psycopg2
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

FACH = 9504
TITEL = "Hebelgesetz im Planungstest"


@pytest_asyncio.fixture
async def knoten(test_client, auth_headers, db_url, run_migrations):
    """Ein Baustein und eine Stunde gleichen Titels im selben Fach."""
    ids = {}
    for art in ("baustein", "stunde"):
        resp = await test_client.post("/context/nodes", json={
            "category": "concept", "content_type": "funktion", "title": TITEL,
            "read_scope": "school", "write_scope": "private",
        }, headers=auth_headers)
        assert resp.status_code == 201, resp.text
        ids[art] = resp.json()["id"]

    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name) VALUES (%s, 'planungstest', 'Planungstest')"
                    " ON CONFLICT (id) DO NOTHING", (FACH,))
        cur.execute("UPDATE context_nodes SET subject_id = %s WHERE id = ANY(%s::uuid[])",
                    (FACH, list(ids.values())))
        # Eine Stunde legt der Planer an, nicht das Formular — hier genügt der Typ.
        cur.execute("UPDATE context_nodes SET category = 'artifact', content_type = 'unterrichtsstunde'"
                    " WHERE id = %s", (ids["stunde"],))
    conn.commit()
    yield ids
    with conn.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE id = ANY(%s::uuid[])", (list(ids.values()),))
        cur.execute("DELETE FROM subjects WHERE id = %s", (FACH,))
    conn.commit()
    conn.close()


async def _suche(client, headers, **extra):
    with patch("app.context.search.generate_embedding",
               new=AsyncMock(side_effect=RuntimeError("kein Embedding-Dienst"))):
        resp = await client.post("/context/search", json={"query": TITEL, **extra}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ids(umschlag) -> set[str]:
    return {
        t["node_id"]
        for abschnitt in ("identifikation", "thematisch", "aufzaehlung")
        for t in (umschlag.get(abschnitt) or {}).get("treffer", [])
    }


async def test_suchseite_findet_keine_stunde(test_client, auth_headers, knoten):
    gefunden = _ids(await _suche(test_client, auth_headers, exclude_planning=True))
    assert knoten["baustein"] in gefunden
    assert knoten["stunde"] not in gefunden


async def test_ohne_schalter_kommt_die_stunde(test_client, auth_headers, knoten):
    """So sucht der Chat (Suchknopf, `@`) — die Stunde bleibt auffindbar."""
    gefunden = _ids(await _suche(test_client, auth_headers))
    assert {knoten["baustein"], knoten["stunde"]} <= gefunden


async def test_aufzaehlung_zaehlt_ohne_planung(test_client, auth_headers, knoten):
    """Die Zahl ist der Grund für die Aufzählung — sie darf die Stunde nicht mitzählen."""
    mit = await _suche(test_client, auth_headers, subject_id=FACH)
    ohne = await _suche(test_client, auth_headers, subject_id=FACH, exclude_planning=True)
    assert mit["aufzaehlung"]["gesamt"] == 2
    assert ohne["aufzaehlung"]["gesamt"] == 1
