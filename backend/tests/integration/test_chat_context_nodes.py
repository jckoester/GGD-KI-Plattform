"""Integrationstests für KS-Phase-5 Schritt 1: chat_context_nodes API."""

import pytest
import pytest_asyncio
import psycopg2
from uuid import uuid4

# ── Fixtures ──────────────────────────────────────────────────────────────────

TEACHER1_PSEUDO = "teacher1-pseudo"
TEACHER2_PSEUDO = "teacher2-pseudo"


@pytest_asyncio.fixture
async def node(test_client, auth_headers):
    """Erstellt einen aktiven ContextNode über die API und gibt ihn zurück."""
    resp = await test_client.post(
        "/context/nodes",
        json={
            "category": "concept",
            "content_type": "funktion",
            "title": "Test-Knoten",
            "read_scope": "school",
            "write_scope": "private",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def archived_node(test_client, auth_headers):
    """Erstellt einen Knoten und archiviert ihn danach."""
    resp = await test_client.post(
        "/context/nodes",
        json={
            "category": "concept",
            "content_type": "funktion",
            "title": "Archivierter Knoten",
            "read_scope": "school",
            "write_scope": "private",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]
    patch = await test_client.patch(
        f"/context/nodes/{node_id}",
        json={"status": "archived"},
        headers=auth_headers,
    )
    assert patch.status_code == 200
    return resp.json()


@pytest_asyncio.fixture
async def private_node_other_user(test_client, auth_headers_teacher2):
    """Erstellt einen privaten Knoten als teacher2."""
    resp = await test_client.post(
        "/context/nodes",
        json={
            "category": "concept",
            "content_type": "funktion",
            "title": "Fremder privater Knoten",
            "read_scope": "private",
            "write_scope": "private",
        },
        headers=auth_headers_teacher2,
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def conversation(db_url, run_migrations):
    """Erstellt eine Konversation für teacher1 via psycopg2 (committed)
    und räumt nach dem Test auf."""
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conv_id = str(uuid4())
    conn = psycopg2.connect(sync_url)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO conversations (id, pseudonym, model_used, title)
            VALUES (%s, %s, 'gpt-4o', 'Test-Konversation')
            """,
            (conv_id, TEACHER1_PSEUDO),
        )
    conn.commit()
    conn.close()

    yield conv_id

    # Cleanup
    conn = psycopg2.connect(sync_url)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE id = %s", (conv_id,))
    conn.commit()
    conn.close()


# ── Tests ────────────────────────────────────────────────────────────────────


class TestChatContextNodes:
    """Testsuite für /api/context/conversations/{id}/nodes Endpunkte."""

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # GET /api/context/conversations/{id}/nodes
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def test_get_empty_conversation(self, test_client, auth_headers, conversation):
        """Test 1: GET leere Konversation → leere Liste."""
        response = await test_client.get(
            f"/context/conversations/{conversation}/nodes",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_after_post(self, test_client, auth_headers, conversation, node):
        """Test 4: GET nach POST enthält den Knoten."""
        await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": node["id"]},
            headers=auth_headers,
        )
        response = await test_client.get(
            f"/context/conversations/{conversation}/nodes",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["node_id"] == node["id"]
        assert data[0]["title"] == node["title"]

    async def test_get_other_users_conversation(
        self, test_client, auth_headers_teacher2, conversation
    ):
        """Test 8: GET fremde Konversation → 403."""
        response = await test_client.get(
            f"/context/conversations/{conversation}/nodes",
            headers=auth_headers_teacher2,
        )
        assert response.status_code == 403

    async def test_get_nonexistent_conversation(self, test_client, auth_headers):
        """GET nicht existierende Konversation → 404."""
        response = await test_client.get(
            f"/context/conversations/{uuid4()}/nodes",
            headers=auth_headers,
        )
        assert response.status_code == 404

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # POST /api/context/conversations/{id}/nodes
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def test_post_valid_node(self, test_client, auth_headers, conversation, node):
        """Test 2: POST gültiger Knoten → 201 mit ChatContextNodeRead."""
        response = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": node["id"]},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["node_id"] == node["id"]
        assert data["title"] == node["title"]
        assert data["content_type"] == node["content_type"]
        assert "added_at" in data

    async def test_post_idempotent(self, test_client, auth_headers, conversation, node):
        """Test 3: POST nochmals (idempotent) → 201, selbes added_at."""
        r1 = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": node["id"]},
            headers=auth_headers,
        )
        assert r1.status_code == 201

        r2 = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": node["id"]},
            headers=auth_headers,
        )
        assert r2.status_code == 201
        assert r1.json()["added_at"] == r2.json()["added_at"]

    async def test_post_nonexistent_node(self, test_client, auth_headers, conversation):
        """Test 6: POST nicht-existenter Knoten → 404."""
        response = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": str(uuid4())},
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_post_archived_node(
        self, test_client, auth_headers, conversation, archived_node
    ):
        """Test 7: POST archivierter Knoten → 404."""
        response = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": archived_node["id"]},
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_post_other_users_conversation(
        self, test_client, auth_headers_teacher2, conversation, node
    ):
        """Test 9: POST fremde Konversation → 403."""
        response = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": node["id"]},
            headers=auth_headers_teacher2,
        )
        assert response.status_code == 403

    async def test_post_private_node_other_user(
        self, test_client, auth_headers, conversation, private_node_other_user
    ):
        """POST fremder privater Knoten → 403."""
        response = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": private_node_other_user["id"]},
            headers=auth_headers,
        )
        assert response.status_code == 403

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DELETE /api/context/conversations/{id}/nodes/{node_id}
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def test_delete_node(self, test_client, auth_headers, conversation, node):
        """Test 5: DELETE → 204, Knoten danach nicht mehr in GET."""
        await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": node["id"]},
            headers=auth_headers,
        )
        response = await test_client.delete(
            f"/context/conversations/{conversation}/nodes/{node['id']}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        get_resp = await test_client.get(
            f"/context/conversations/{conversation}/nodes",
            headers=auth_headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.json() == []

    async def test_delete_nonexistent_entry(
        self, test_client, auth_headers, conversation, node
    ):
        """DELETE nicht existierender Eintrag → 404."""
        response = await test_client.delete(
            f"/context/conversations/{conversation}/nodes/{node['id']}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_delete_other_users_conversation(
        self, test_client, auth_headers_teacher2, conversation, node
    ):
        """Test 10: DELETE fremde Konversation → 403."""
        response = await test_client.delete(
            f"/context/conversations/{conversation}/nodes/{node['id']}",
            headers=auth_headers_teacher2,
        )
        assert response.status_code == 403

    async def test_delete_nonexistent_conversation(
        self, test_client, auth_headers, node
    ):
        """DELETE mit nicht existierender Konversation → 404."""
        response = await test_client.delete(
            f"/context/conversations/{uuid4()}/nodes/{node['id']}",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestEinordnendeFelder:
    """Fach, Fassung und Nummer reisen mit — sonst kann die Oberflaeche nicht einordnen.

    Ohne Fach ist eine BP-Kompetenz in einer Liste nicht zu bestimmen: `2.1.1`
    gibt es in 24 Faechern, und der Knotentyp steht ohnehin schon in der Nummer.
    """

    @pytest_asyncio.fixture
    async def bp_knoten(self, test_client, auth_headers, db_url):
        """IK-Kompetenz mit Fach, Fassung und Nummer — wie sie der Import anlegt."""
        resp = await test_client.post(
            "/context/nodes",
            json={
                "category": "knowledge",
                "content_type": "ik_kompetenz",
                "title": "Zahlen und Operationen",
                "read_scope": "school",
                "write_scope": "private",
                "metadata": {"kompetenz_nr": "3.1.1(1)", "bp_version": "2016.V3"},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        node = resp.json()

        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            cur.execute(
                # fach_code bleibt NULL: Die Spalte ist schulweit eindeutig,
                # und diese Fixture committet — ein Kuerzel wuerde andere Tests brechen.
                "INSERT INTO subjects (id, slug, name) VALUES "
                "(9501, 'mathe-anzeige', 'Mathematik') ON CONFLICT (id) DO NOTHING"
            )
            cur.execute(
                "UPDATE context_nodes SET subject_id = 9501, bp_version = '2016.V3' "
                "WHERE id = %s",
                (node["id"],),
            )
        conn.commit()
        conn.close()
        return node

    async def test_post_liefert_fach_fassung_und_nummer(
        self, test_client, auth_headers, conversation, bp_knoten
    ):
        response = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": bp_knoten["id"]},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["subject_id"] == 9501
        assert data["bp_version"] == "2016.V3"
        assert data["nr"] == "3.1.1(1)"

    async def test_get_liefert_dieselben_felder(
        self, test_client, auth_headers, conversation, bp_knoten
    ):
        await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": bp_knoten["id"]},
            headers=auth_headers,
        )
        response = await test_client.get(
            f"/context/conversations/{conversation}/nodes",
            headers=auth_headers,
        )
        assert response.status_code == 200
        eintrag = response.json()[0]
        assert eintrag["subject_id"] == 9501
        assert eintrag["bp_version"] == "2016.V3"
        assert eintrag["nr"] == "3.1.1(1)"

    async def test_erneutes_anheften_liefert_die_felder_ebenfalls(
        self, test_client, auth_headers, conversation, bp_knoten
    ):
        """Der Zweig fuer den bereits angehefteten Knoten baut die Antwort selbst."""
        for _ in range(2):
            response = await test_client.post(
                f"/context/conversations/{conversation}/nodes",
                json={"node_id": bp_knoten["id"]},
                headers=auth_headers,
            )
        assert response.json()["subject_id"] == 9501
        assert response.json()["nr"] == "3.1.1(1)"

    async def test_knoten_ohne_bildungsplanbezug_bleibt_leer(
        self, test_client, auth_headers, conversation, node
    ):
        """Nutzerknoten haben kein Fach und keine Nummer — dann eben `null`."""
        response = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": node["id"]},
            headers=auth_headers,
        )
        data = response.json()
        assert data["subject_id"] is None
        assert data["bp_version"] is None
        assert data["nr"] is None
        # Der Knotentyp bleibt die Einordnung, wo es kein Fach gibt.
        assert data["content_type"] == "funktion"


class TestSuchergebnisFelder:
    """`/context/search` speist die Vorschlagsliste und den SSE-Kanal im Chat.

    Der Endpunkt hat **zwei** Pfade: die Embedding-Suche liefert Row-Mappings aus
    rohem SQL, der ILIKE-Fallback ORM-Objekte. Am ORM-Objekt heisst die JSON-Spalte
    `metadata_` — `metadata` waere dort die SQLAlchemy-MetaData. Beide Pfade muessen
    dieselben einordnenden Felder tragen, deshalb wird jeder einzeln geprueft.
    """

    @pytest_asyncio.fixture
    async def bp_knoten(self, test_client, auth_headers, db_url):
        resp = await test_client.post(
            "/context/nodes",
            json={
                "category": "knowledge",
                "content_type": "ik_kompetenz",
                "title": "Bruchrechnung im Suchtest",
                "read_scope": "school",
                "write_scope": "school",
                "metadata": {"kompetenz_nr": "3.1.2(4)", "bp_version": "2016.V2"},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        node = resp.json()

        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO subjects (id, slug, name) VALUES "
                "(9502, 'mathe-suche', 'Mathematik') ON CONFLICT (id) DO NOTHING"
            )
            cur.execute(
                "UPDATE context_nodes SET subject_id = 9502, bp_version = '2016.V2' "
                "WHERE id = %s",
                (node["id"],),
            )
        conn.commit()
        conn.close()
        return node

    def _treffer(self, daten, node):
        return next(t for t in daten if t["node_id"] == node["id"])

    async def test_ilike_fallback_traegt_die_felder(
        self, test_client, auth_headers, bp_knoten
    ):
        """Ohne erreichbaren Embedding-Dienst faellt die Suche auf ILIKE zurueck."""
        from unittest.mock import AsyncMock, patch

        with patch(
            "app.chat.router.generate_embedding",
            new=AsyncMock(side_effect=RuntimeError("kein Embedding-Dienst")),
        ):
            response = await test_client.post(
                "/context/search",
                json={"query": "Bruchrechnung im Suchtest"},
                headers=auth_headers,
            )
        assert response.status_code == 200, response.text
        treffer = self._treffer(response.json(), bp_knoten)
        assert treffer["subject_id"] == 9502
        assert treffer["bp_version"] == "2016.V2"
        assert treffer["nr"] == "3.1.2(4)"

    async def test_embedding_pfad_traegt_dieselben_felder(
        self, test_client, auth_headers, db_url, bp_knoten
    ):
        from unittest.mock import AsyncMock, patch

        from app.config import settings

        vec = [0.0] * settings.embedding_dimensions
        vec[0] = 1.0
        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE context_nodes SET embedding = %s::vector WHERE id = %s",
                ("[" + ",".join(str(v) for v in vec) + "]", bp_knoten["id"]),
            )
        conn.commit()
        conn.close()

        with patch("app.chat.router.generate_embedding",
                   new=AsyncMock(return_value=vec)):
            response = await test_client.post(
                "/context/search",
                # Absichtlich ohne Titeltreffer: Findet die Suche den Knoten
                # trotzdem, kann das nur der Embedding-Pfad gewesen sein.
                json={"query": "zzz-kein-titeltreffer-zzz"},
                headers=auth_headers,
            )
        assert response.status_code == 200, response.text
        treffer = self._treffer(response.json(), bp_knoten)
        assert treffer["subject_id"] == 9502
        assert treffer["bp_version"] == "2016.V2"
        assert treffer["nr"] == "3.1.2(4)"
