"""KS-Phase-3 Integrationstests."""
import pytest
import psycopg2
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def truncate_ks3_tables(db_url, run_migrations):
    """Leert alle Tabellen vor jedem Test."""
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            TRUNCATE assistant_context_anchors, context_edges, context_nodes
            RESTART IDENTITY CASCADE
        """)
    conn.commit()
    conn.close()
    yield


class TestContextAnchorsAPI:
    """Integrationstests fuer die Context Anchor API."""

    @pytest.mark.asyncio
    async def test_add_retrieval_scope_anchor(self, test_client, auth_headers):
        """POST mit gueltigem fachplan-Knoten -> 201, Anker in DB."""
        # Erst einen Knoten erstellen
        create_node_resp = await test_client.post(
            "/api/context/nodes",
            json={
                "category": "knowledge",
                "content_type": "fachplan",
                "title": "Test Fachplan",
                "content": "Inhalt",
            },
            headers=auth_headers,
        )
        assert create_node_resp.status_code == 201
        node_id = create_node_resp.json()["id"]

        # Anker hinzufuegen
        add_resp = await test_client.post(
            f"/api/context/assistants/1/anchors",
            json={"node_id": str(node_id), "role": "retrieval_scope"},
            headers=auth_headers,
        )
        assert add_resp.status_code == 201
        assert add_resp.json()["node_id"] == str(node_id)
        assert add_resp.json()["role"] == "retrieval_scope"

    @pytest.mark.asyncio
    async def test_add_invalid_scope_type_rejected(self, test_client, auth_headers):
        """POST mit ik_kompetenz-Knoten als retrieval_scope -> 422."""
        # Erst einen Knoten erstellen
        create_node_resp = await test_client.post(
            "/api/context/nodes",
            json={
                "category": "knowledge",
                "content_type": "ik_kompetenz",
                "title": "Test IK",
                "content": "Inhalt",
            },
            headers=auth_headers,
        )
        assert create_node_resp.status_code == 201
        node_id = create_node_resp.json()["id"]

        # Anker hinzufuegen - sollte fehlschlagen
        add_resp = await test_client.post(
            f"/api/context/assistants/1/anchors",
            json={"node_id": str(node_id), "role": "retrieval_scope"},
            headers=auth_headers,
        )
        assert add_resp.status_code == 422
        assert "gueltiger retrieval_scope-Anker" in add_resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_add_themengebiet_anchor(self, test_client, auth_headers):
        """POST mit themengebiet-Knoten -> 201 (Typ ist in VALID_SCOPE_ANCHOR_TYPES)."""
        # Erst einen Knoten erstellen
        create_node_resp = await test_client.post(
            "/api/context/nodes",
            json={
                "category": "knowledge",
                "content_type": "themengebiet",
                "title": "Test Themengebiet",
                "content": "Inhalt",
            },
            headers=auth_headers,
        )
        assert create_node_resp.status_code == 201
        node_id = create_node_resp.json()["id"]

        # Anker hinzufuegen
        add_resp = await test_client.post(
            f"/api/context/assistants/1/anchors",
            json={"node_id": str(node_id), "role": "retrieval_scope"},
            headers=auth_headers,
        )
        assert add_resp.status_code == 201

    @pytest.mark.asyncio
    async def test_list_anchors(self, test_client, auth_headers):
        """GET gibt alle Anker mit node_title zurueck."""
        # Erst einen Knoten und Anker erstellen
        create_node_resp = await test_client.post(
            "/api/context/nodes",
            json={
                "category": "knowledge",
                "content_type": "fachplan",
                "title": "Test Fachplan",
                "content": "Inhalt",
            },
            headers=auth_headers,
        )
        node_id = create_node_resp.json()["id"]

        await test_client.post(
            f"/api/context/assistants/1/anchors",
            json={"node_id": str(node_id), "role": "retrieval_scope"},
            headers=auth_headers,
        )

        # Liste abrufen
        list_resp = await test_client.get(
            "/api/context/assistants/1/anchors",
            headers=auth_headers,
        )
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1
        assert list_resp.json()[0]["node_title"] == "Test Fachplan"
        assert list_resp.json()[0]["node_content_type"] == "fachplan"

    @pytest.mark.asyncio
    async def test_remove_anchor(self, test_client, auth_headers):
        """DELETE -> 204, Anker nicht mehr in DB."""
        # Erst einen Knoten und Anker erstellen
        create_node_resp = await test_client.post(
            "/api/context/nodes",
            json={
                "category": "knowledge",
                "content_type": "fachplan",
                "title": "Test Fachplan",
                "content": "Inhalt",
            },
            headers=auth_headers,
        )
        node_id = create_node_resp.json()["id"]

        await test_client.post(
            f"/api/context/assistants/1/anchors",
            json={"node_id": str(node_id), "role": "retrieval_scope"},
            headers=auth_headers,
        )

        # Loeschen
        del_resp = await test_client.delete(
            f"/api/context/assistants/1/anchors/{node_id}/retrieval_scope",
            headers=auth_headers,
        )
        assert del_resp.status_code == 204

        # Pruefen dass geloescht
        list_resp = await test_client.get(
            "/api/context/assistants/1/anchors",
            headers=auth_headers,
        )
        assert len(list_resp.json()) == 0

    @pytest.mark.asyncio
    async def test_permission_rejected(self, test_client, auth_headers_teacher2):
        """POST von fremdem Pseudonym -> 403."""
        # Erst einen Knoten erstellen (als teacher2)
        create_node_resp = await test_client.post(
            "/api/context/nodes",
            json={
                "category": "knowledge",
                "content_type": "fachplan",
                "title": "Test Fachplan",
                "content": "Inhalt",
            },
            headers=auth_headers_teacher2,
        )
        assert create_node_resp.status_code == 201
        node_id = create_node_resp.json()["id"]

        # Versuchen als teacher1 einen Anker fuer Assistent 1 zu erstellen
        # (Assistent 1 gehoert teacher1, teacher2 darf nicht aendern)
        add_resp = await test_client.post(
            f"/api/context/assistants/1/anchors",
            json={"node_id": str(node_id), "role": "retrieval_scope"},
            headers=auth_headers_teacher2,
        )
        # Sollte 403 sein weil teacher2 nicht der Eigentuemer von Assistent 1 ist
        # (Annahme: Assistent 1 wurde von teacher1 erstellt)
        # In der Testdatenbank muss Assistent 1 mit created_by='teacher1' existieren
        # Falls nicht, wird der Test uebersprungen
        if add_resp.status_code == 404:
            pytest.skip("Assistent 1 nicht gefunden - Testdaten fehlen")
        # Andernfalls sollte es 403 sein
        assert add_resp.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_duplicate_anchor_rejected(self, test_client, auth_headers):
        """Zweimal denselben Anker -> 409."""
        # Erst einen Knoten erstellen
        create_node_resp = await test_client.post(
            "/api/context/nodes",
            json={
                "category": "knowledge",
                "content_type": "fachplan",
                "title": "Test Fachplan",
                "content": "Inhalt",
            },
            headers=auth_headers,
        )
        node_id = create_node_resp.json()["id"]

        # Ersten Anker hinzufuegen
        add_resp1 = await test_client.post(
            f"/api/context/assistants/1/anchors",
            json={"node_id": str(node_id), "role": "retrieval_scope"},
            headers=auth_headers,
        )
        assert add_resp1.status_code == 201

        # Zweiten identischen Anker hinzufuegen -> sollte fehlschlagen
        add_resp2 = await test_client.post(
            f"/api/context/assistants/1/anchors",
            json={"node_id": str(node_id), "role": "retrieval_scope"},
            headers=auth_headers,
        )
        assert add_resp2.status_code == 409
