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
