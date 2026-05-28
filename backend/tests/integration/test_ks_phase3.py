"""KS-Phase-3 Integrationstests."""
import json
import uuid as _uuid

import pytest
import psycopg2
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def unit_vec(pos: int, dim: int = 1536) -> list[float]:
    """Erzeugt einen Einheitsvektor an Position pos (1536 Dimensionen)."""
    v = [0.0] * dim
    v[pos] = 1.0
    return v


def insert_node_sync(db_url: str, *, content_type: str, title: str, content: str,
                      metadata: dict, embedding: list[float] | None = None) -> str:
    """Legt einen aktiven Knoten an, gibt seine UUID als String zurueck."""
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    node_id = str(_uuid.uuid4())
    emb_str = "[" + ",".join(str(v) for v in embedding) + "]" if embedding else None
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO context_nodes
              (id, category, content_type, title, content, metadata,
               read_scope, write_scope, status)
            VALUES (%s, 'knowledge', %s, %s, %s, %s, 'global', 'global', 'active')
        """, (node_id, content_type, title, content, json.dumps(metadata)))
        if emb_str:
            cur.execute(
                f"UPDATE context_nodes SET embedding = '{emb_str}'::vector WHERE id = %s",
                (node_id,)
            )
    conn.commit()
    conn.close()
    return node_id


def insert_edge_sync(db_url: str, from_id: str, to_id: str, relation: str) -> None:
    """Legt eine Kante an."""
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO context_edges (from_node_id, to_node_id, relation)
            VALUES (%s, %s, %s)
            ON CONFLICT (from_node_id, to_node_id, relation) DO NOTHING
        """, (from_id, to_id, relation))
    conn.commit()
    conn.close()


def insert_engagement_sync(db_url: str, *, node_id: str, pseudonym: str,
                            relation: str = "knows", source: str = "chat_inference") -> None:
    """Legt ein Nutzer-Engagement an."""
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO node_engagement (id, pseudonym, node_id, relation, source, metadata)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, '{}')
            ON CONFLICT DO NOTHING
        """, (pseudonym, node_id, relation, source))
    conn.commit()
    conn.close()


def insert_group_engagement_sync(db_url: str, *, node_id: str, group_id: int,
                                  relation: str = "introduced") -> None:
    """Legt ein Gruppen-Engagement an."""
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO node_engagement (id, group_id, node_id, relation, source, metadata)
            VALUES (gen_random_uuid(), %s, %s, %s, 'lesson_plan', '{}')
            ON CONFLICT DO NOTHING
        """, (group_id, node_id, relation))
    conn.commit()
    conn.close()


def insert_group_membership_sync(db_url: str, *, group_id: int, pseudonym: str,
                                   role_in_group: str = "student") -> None:
    """Legt eine Gruppen-Mitgliedschaft an."""
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO group_memberships (group_id, pseudonym, role_in_group)
            VALUES (%s, %s, %s)
            ON CONFLICT (group_id, pseudonym) DO NOTHING
        """, (group_id, pseudonym, role_in_group))
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def truncate_ks3_tables(db_url, run_migrations, seed_test_group):
    """Leert alle Tabellen vor jedem Test."""
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("""
            TRUNCATE group_memberships, assistant_context_anchors, context_edges, context_nodes
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


# -----------------------------------------------------------------------------

class TestSemanticSearch:
    """Integrationstests fuer die semantische Suche in retrieval.py."""

    @pytest.mark.asyncio
    async def test_semantic_search_finds_relevant_node(self, db_session, db_url):
        """Anlegen von 3 Knoten mit verschiedenen Embeddings; Query-Embedding ahnlich zu Knoten 1 -> Knoten 1 ist erstes Ergebnis."""
        from app.context.retrieval import get_semantic_context

        # 3 Knoten mit unterschiedlichen Embeddings anlegen
        node1 = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Knoten 1",
            content="Inhalt 1",
            metadata={},
            embedding=unit_vec(0),
        )
        node2 = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Knoten 2",
            content="Inhalt 2",
            metadata={},
            embedding=unit_vec(100),
        )
        node3 = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Knoten 3",
            content="Inhalt 3",
            metadata={},
            embedding=unit_vec(200),
        )

        # Query-Embedding nah an node1 (pos 0 mit hohem Wert)
        # Mock von generate_embedding
        from unittest.mock import patch, AsyncMock
        query_embedding = [0.9] + [0.01] * 1535
        with patch(
            'app.context.retrieval.generate_embedding',
            new_callable=AsyncMock,
            return_value=query_embedding,
        ):
            results = await get_semantic_context(
                anchor_ids=[node1, node2, node3],
                query_text="irgendwas",
                pseudonym="test",
                db=db_session,
                top_k=10,
            )

        # node1 sollte erstes Ergebnis sein (kleinstes Cosinus-Distance)
        assert len(results) == 3
        assert str(results[0].id) == node1

    @pytest.mark.asyncio
    async def test_no_anchors_returns_empty(self, db_session):
        """anchor_ids=[] -> leere Liste, kein Fehler."""
        from app.context.retrieval import get_semantic_context

        results = await get_semantic_context(
            anchor_ids=[],
            query_text="irgendwas",
            pseudonym="test",
            db=db_session,
            top_k=10,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_archived_nodes_excluded(self, db_session, db_url):
        """Archivierter Knoten im Scope -> nicht im Ergebnis."""
        from app.context.retrieval import get_semantic_context

        node1 = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Aktiv",
            content="Inhalt",
            metadata={},
            embedding=unit_vec(0),
        )
        node2 = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Archiviert",
            content="Inhalt",
            metadata={},
            embedding=unit_vec(100),
        )

        # node2 archivieren
        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            cur.execute("UPDATE context_nodes SET status = 'archived' WHERE id = %s", (node2,))
        conn.commit()
        conn.close()

        from unittest.mock import patch, AsyncMock
        with patch(
            'app.context.retrieval.generate_embedding',
            new_callable=AsyncMock,
            return_value=unit_vec(0),
        ):
            results = await get_semantic_context(
                anchor_ids=[node1, node2],
                query_text="test",
                pseudonym="test",
                db=db_session,
                top_k=10,
            )

        # Nur node1 sollte zurueckgegeben werden
        assert len(results) == 1
        assert str(results[0].id) == node1

    @pytest.mark.asyncio
    async def test_node_without_embedding_excluded(self, db_session, db_url):
        """Knoten ohne Embedding im Scope -> nicht im Ergebnis."""
        from app.context.retrieval import get_semantic_context

        node1 = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Mit Embedding",
            content="Inhalt",
            metadata={},
            embedding=unit_vec(0),
        )
        node2 = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Ohne Embedding",
            content="Inhalt",
            metadata={},
            embedding=None,
        )

        from unittest.mock import patch, AsyncMock
        with patch(
            'app.context.retrieval.generate_embedding',
            new_callable=AsyncMock,
            return_value=unit_vec(0),
        ):
            results = await get_semantic_context(
                anchor_ids=[node1, node2],
                query_text="test",
                pseudonym="test",
                db=db_session,
                top_k=10,
            )

        assert len(results) == 1
        assert str(results[0].id) == node1

    @pytest.mark.asyncio
    async def test_scope_cte_follows_part_of(self, db_session, db_url):
        """Anker = Leitidee-Knoten; ik_kompetenz-Knoten mit part_of-Kante -> im Ergebnis."""
        from app.context.retrieval import get_semantic_context

        leitidee = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Leitidee",
            content="Inhalt",
            metadata={},
            embedding=unit_vec(0),
        )
        ik = insert_node_sync(
            db_url,
            content_type="ik_kompetenz",
            title="IK",
            content="Inhalt",
            metadata={},
            embedding=unit_vec(100),
        )

        # ik ist part_of leitidee
        insert_edge_sync(db_url, from_id=ik, to_id=leitidee, relation="part_of")

        from unittest.mock import patch, AsyncMock
        with patch(
            'app.context.retrieval.generate_embedding',
            new_callable=AsyncMock,
            return_value=unit_vec(100),
        ):
            results = await get_semantic_context(
                anchor_ids=[leitidee],
                query_text="test",
                pseudonym="test",
                db=db_session,
                top_k=10,
            )

        # Beide Knoten sollten im Ergebnis sein
        result_ids = {str(r.id) for r in results}
        assert leitidee in result_ids
        assert ik in result_ids

    @pytest.mark.asyncio
    async def test_scope_cte_follows_references(self, db_session, db_url):
        """Anker = UE-Knoten; ik_kompetenz mit references-Kante vom Anker -> im Ergebnis."""
        from app.context.retrieval import get_semantic_context

        ue = insert_node_sync(
            db_url,
            content_type="unterrichtseinheit",
            title="UE",
            content="Inhalt",
            metadata={},
            embedding=unit_vec(0),
        )
        ik = insert_node_sync(
            db_url,
            content_type="ik_kompetenz",
            title="IK",
            content="Inhalt",
            metadata={},
            embedding=unit_vec(100),
        )

        # ue referenziert ik
        insert_edge_sync(db_url, from_id=ue, to_id=ik, relation="references")

        from unittest.mock import patch, AsyncMock
        with patch(
            'app.context.retrieval.generate_embedding',
            new_callable=AsyncMock,
            return_value=unit_vec(100),
        ):
            results = await get_semantic_context(
                anchor_ids=[ue],
                query_text="test",
                pseudonym="test",
                db=db_session,
                top_k=10,
            )

        result_ids = {str(r.id) for r in results}
        assert ue in result_ids
        assert ik in result_ids

    @pytest.mark.asyncio
    async def test_read_scope_private_excluded_for_other_user(self, db_session, db_url):
        """Knoten mit read_scope='private', owner='anderes-pseudonym' -> nicht im Ergebnis fuer aktuelles Pseudonym."""
        from app.context.retrieval import get_semantic_context

        node1 = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Privat fuer other",
            content="Inhalt",
            metadata={},
            embedding=unit_vec(0),
        )

        # node1 als privat fuer anderes Pseudonym markieren
        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE context_nodes SET read_scope = 'private', write_scope = 'private', owner_pseudonym = 'other' WHERE id = %s",
                (node1,)
            )
        conn.commit()
        conn.close()

        from unittest.mock import patch, AsyncMock
        with patch(
            'app.context.retrieval.generate_embedding',
            new_callable=AsyncMock,
            return_value=unit_vec(0),
        ):
            results = await get_semantic_context(
                anchor_ids=[node1],
                query_text="test",
                pseudonym="current_user",
                db=db_session,
                top_k=10,
            )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_scope_filter_excludes_out_of_scope(self, db_session, db_url):
        """Zwei Anker-Subgraphen; Knoten ausserhalb des Scope werden nicht zurueckgegeben."""
        from app.context.retrieval import get_semantic_context

        # Anker 1 mit seinem Subgraphen
        anchor1 = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Anker 1",
            content="Inhalt",
            metadata={},
            embedding=unit_vec(0),
        )
        node1 = insert_node_sync(
            db_url,
            content_type="ik_kompetenz",
            title="IK 1",
            content="Inhalt",
            metadata={},
            embedding=unit_vec(1),
        )
        insert_edge_sync(db_url, from_id=node1, to_id=anchor1, relation="part_of")

        # Anker 2 mit seinem Subgraphen
        anchor2 = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Anker 2",
            content="Inhalt",
            metadata={},
            embedding=unit_vec(100),
        )
        node2 = insert_node_sync(
            db_url,
            content_type="ik_kompetenz",
            title="IK 2",
            content="Inhalt",
            metadata={},
            embedding=unit_vec(101),
        )
        insert_edge_sync(db_url, from_id=node2, to_id=anchor2, relation="part_of")

        from unittest.mock import patch, AsyncMock
        with patch(
            'app.context.retrieval.generate_embedding',
            new_callable=AsyncMock,
            return_value=unit_vec(1),
        ):
            # Suche nur im Scope von anchor1
            results = await get_semantic_context(
                anchor_ids=[anchor1],
                query_text="test",
                pseudonym="test",
                db=db_session,
                top_k=10,
            )

        result_ids = {str(r.id) for r in results}
        assert anchor1 in result_ids
        assert node1 in result_ids
        assert anchor2 not in result_ids
        assert node2 not in result_ids


# -----------------------------------------------------------------------------

class TestEngagementRetrieval:
    """Integrationstests fuer Engagement-Retrieval mit Scope-Filter."""

    @pytest.mark.asyncio
    async def test_personal_engagement_in_scope_returned(self, db_session, db_url):
        """Schueler hat Engagement fuer Knoten im Scope -> Entry in Ergebnis."""
        from app.context.retrieval import get_engagement_context

        anchor = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Anker",
            content="Inhalt",
            metadata={},
            embedding=unit_vec(0),
        )
        node = insert_node_sync(
            db_url,
            content_type="ik_kompetenz",
            title="IK",
            content="Inhalt",
            metadata={},
            embedding=unit_vec(1),
        )
        insert_edge_sync(db_url, from_id=node, to_id=anchor, relation="part_of")

        # Engagement fuer node anlegen
        insert_engagement_sync(db_url, node_id=node, pseudonym="test_user", relation="knows")

        results = await get_engagement_context(
            anchor_ids=[anchor],
            pseudonym="test_user",
            db=db_session,
        )

        assert len(results) == 1
        assert str(results[0].node.id) == node
        assert "knows" in results[0].relations
        assert "user" in results[0].origins
        assert isinstance(results[0].node.metadata_, dict)

    @pytest.mark.asyncio
    async def test_engagement_outside_scope_excluded(self, db_session, db_url):
        """Schueler hat Engagement fuer Knoten ausserhalb des Anker-Subgraphen -> nicht im Ergebnis."""
        from app.context.retrieval import get_engagement_context

        anchor = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Anker",
            content="Inhalt",
            metadata={},
        )
        other_node = insert_node_sync(
            db_url,
            content_type="ik_kompetenz",
            title="Anderer Knoten",
            content="Inhalt",
            metadata={},
        )

        # Engagement fuer other_node anlegen (nicht im Scope von anchor)
        insert_engagement_sync(db_url, node_id=other_node, pseudonym="test_user", relation="knows")

        results = await get_engagement_context(
            anchor_ids=[anchor],
            pseudonym="test_user",
            db=db_session,
        )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_group_engagement_included(self, db_session, db_url):
        """Gruppe hat introduced-Engagement fuer Knoten im Scope; Schueler ist Gruppenmitglied -> Entry mit origin=['group']."""
        from app.context.retrieval import get_engagement_context

        # Gruppe und Mitgliedschaft anlegen
        group_id = 1
        insert_group_membership_sync(db_url, group_id=group_id, pseudonym="test_user")

        anchor = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Anker",
            content="Inhalt",
            metadata={},
        )
        node = insert_node_sync(
            db_url,
            content_type="ik_kompetenz",
            title="IK",
            content="Inhalt",
            metadata={},
        )
        insert_edge_sync(db_url, from_id=node, to_id=anchor, relation="part_of")

        # Gruppen-Engagement anlegen
        insert_group_engagement_sync(db_url, node_id=node, group_id=group_id, relation="introduced")

        results = await get_engagement_context(
            anchor_ids=[anchor],
            pseudonym="test_user",
            db=db_session,
        )

        assert len(results) == 1
        assert str(results[0].node.id) == node
        assert "introduced" in results[0].relations
        assert "group" in results[0].origins

    @pytest.mark.asyncio
    async def test_user_and_group_engagement_combined(self, db_session, db_url):
        """Schueler hat eigenes UND Gruppen-Engagement fuer denselben Knoten -> ein Entry mit beiden origins."""
        from app.context.retrieval import get_engagement_context

        # Gruppe und Mitgliedschaft anlegen
        group_id = 1
        insert_group_membership_sync(db_url, group_id=group_id, pseudonym="test_user")

        anchor = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Anker",
            content="Inhalt",
            metadata={},
        )
        node = insert_node_sync(
            db_url,
            content_type="ik_kompetenz",
            title="IK",
            content="Inhalt",
            metadata={},
        )
        insert_edge_sync(db_url, from_id=node, to_id=anchor, relation="part_of")

        # Eigenes Engagement
        insert_engagement_sync(db_url, node_id=node, pseudonym="test_user", relation="knows")
        # Gruppen-Engagement
        insert_group_engagement_sync(db_url, node_id=node, group_id=group_id, relation="introduced")

        results = await get_engagement_context(
            anchor_ids=[anchor],
            pseudonym="test_user",
            db=db_session,
        )

        assert len(results) == 1
        assert str(results[0].node.id) == node
        assert "knows" in results[0].relations
        assert "introduced" in results[0].relations
        assert "user" in results[0].origins
        assert "group" in results[0].origins

    @pytest.mark.asyncio
    async def test_no_anchors_returns_empty(self, db_session):
        """anchor_ids=[] -> leere Liste, kein Fehler."""
        from app.context.retrieval import get_engagement_context

        results = await get_engagement_context(
            anchor_ids=[],
            pseudonym="test_user",
            db=db_session,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_archived_node_excluded(self, db_session, db_url):
        """Engagement auf archivierten Knoten -> nicht im Ergebnis."""
        from app.context.retrieval import get_engagement_context

        anchor = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Anker",
            content="Inhalt",
            metadata={},
        )
        node = insert_node_sync(
            db_url,
            content_type="ik_kompetenz",
            title="IK",
            content="Inhalt",
            metadata={},
        )
        insert_edge_sync(db_url, from_id=node, to_id=anchor, relation="part_of")

        # Engagement anlegen
        insert_engagement_sync(db_url, node_id=node, pseudonym="test_user", relation="knows")

        # node archivieren
        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            cur.execute("UPDATE context_nodes SET status = 'archived' WHERE id = %s", (node,))
        conn.commit()
        conn.close()

        results = await get_engagement_context(
            anchor_ids=[anchor],
            pseudonym="test_user",
            db=db_session,
        )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_scope_via_part_of_chain(self, db_session, db_url):
        """Anker = fachplan; ik_kompetenz im Subgraphen mit Engagement -> im Ergebnis."""
        from app.context.retrieval import get_engagement_context

        anchor = insert_node_sync(
            db_url,
            content_type="fachplan",
            title="Fachplan",
            content="Inhalt",
            metadata={},
        )
        leitidee = insert_node_sync(
            db_url,
            content_type="leitidee",
            title="Leitidee",
            content="Inhalt",
            metadata={},
        )
        ik = insert_node_sync(
            db_url,
            content_type="ik_kompetenz",
            title="IK",
            content="Inhalt",
            metadata={},
        )

        # Kette: ik -> part_of -> leitidee -> part_of -> anchor
        insert_edge_sync(db_url, from_id=ik, to_id=leitidee, relation="part_of")
        insert_edge_sync(db_url, from_id=leitidee, to_id=anchor, relation="part_of")

        # Engagement anlegen
        insert_engagement_sync(db_url, node_id=ik, pseudonym="test_user", relation="mastered")

        results = await get_engagement_context(
            anchor_ids=[anchor],
            pseudonym="test_user",
            db=db_session,
        )

        result_ids = {str(r.node.id) for r in results}
        assert ik in result_ids

    @pytest.mark.asyncio
    async def test_scope_via_references_edge(self, db_session, db_url):
        """Anker = UE; ik_kompetenz via references-Edge mit Engagement -> im Ergebnis."""
        from app.context.retrieval import get_engagement_context

        anchor = insert_node_sync(
            db_url,
            content_type="unterrichtseinheit",
            title="UE",
            content="Inhalt",
            metadata={},
        )
        ik = insert_node_sync(
            db_url,
            content_type="ik_kompetenz",
            title="IK",
            content="Inhalt",
            metadata={},
        )

        # UE referenziert IK
        insert_edge_sync(db_url, from_id=anchor, to_id=ik, relation="references")

        # Engagement anlegen
        insert_engagement_sync(db_url, node_id=ik, pseudonym="test_user", relation="knows")

        results = await get_engagement_context(
            anchor_ids=[anchor],
            pseudonym="test_user",
            db=db_session,
        )

        result_ids = {str(r.node.id) for r in results}
        assert ik in result_ids
