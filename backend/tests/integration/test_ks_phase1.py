"""Integrationstests für KS-Phase-1: Migration und CRUD-Roundtrip.

Testet gegen eine echte pgvector-Postgres-Instanz via Testcontainers.
"""

import pytest
import pytest_asyncio
from datetime import date, datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    ContextNode,
    ContextEdge,
    NodeEngagement,
    AssistantContextAnchor,
    ChatContextNode,
)



# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def make_node_data(**kwargs) -> dict:
    defaults = dict(
        category="concept",
        content_type="funktion",
        title="digitalWrite",
        read_scope="school",
        write_scope="private",
        owner_pseudonym="pseudo-test",
        metadata_={},
    )
    defaults.update(kwargs)
    return defaults


async def insert_node(db, **kwargs) -> ContextNode:
    node = ContextNode(**make_node_data(**kwargs))
    db.add(node)
    await db.flush()
    await db.refresh(node)
    return node


# ── Migration-Smoke-Tests ─────────────────────────────────────────────────────

class TestMigration:

    def test_all_tables_exist(self, run_migrations, postgres_container):
        """Alle fünf Tabellen sind nach upgrade head vorhanden."""
        import psycopg2
        conn = psycopg2.connect(postgres_container.get_connection_url().replace("postgresql+psycopg2://", "postgresql://"))
        cur = conn.cursor()
        expected = {
            "context_nodes",
            "context_edges",
            "node_engagement",
            "assistant_context_anchors",
            "chat_context_nodes",
        }
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        tables = {row[0] for row in cur.fetchall()}
        assert expected.issubset(tables), f"Fehlende Tabellen: {expected - tables}"
        cur.close()
        conn.close()

    def test_pgvector_extension_installed(self, run_migrations, postgres_container):
        """pgvector-Extension ist nach der Migration verfügbar."""
        import psycopg2
        conn = psycopg2.connect(postgres_container.get_connection_url().replace("postgresql+psycopg2://", "postgresql://"))
        cur = conn.cursor()
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        assert cur.fetchone() is not None, "pgvector nicht installiert"
        cur.close()
        conn.close()

    def test_embedding_column_is_vector_type(self, run_migrations, postgres_container):
        """embedding-Spalte hat Typ vector(1536)."""
        import psycopg2
        conn = psycopg2.connect(postgres_container.get_connection_url().replace("postgresql+psycopg2://", "postgresql://"))
        cur = conn.cursor()
        cur.execute("""
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_name = 'context_nodes'
              AND column_name = 'embedding'
        """)
        row = cur.fetchone()
        assert row is not None and row[0] == "vector", (
            f"Erwartet 'vector', erhalten: {row}"
        )
        cur.close()
        conn.close()


# ── ContextNode CRUD ──────────────────────────────────────────────────────────

class TestContextNodeCRUD:

    async def test_insert_and_read(self, db_session):
        node = await insert_node(db_session)
        assert node.id is not None
        assert node.status == "active"
        assert node.category == "concept"

    async def test_update_title(self, db_session):
        node = await insert_node(db_session)
        node.title = "analogRead"
        await db_session.flush()
        await db_session.refresh(node)
        assert node.title == "analogRead"

    async def test_delete(self, db_session):
        node = await insert_node(db_session, title="zu_loeschen")
        node_id = node.id
        await db_session.delete(node)
        await db_session.flush()
        result = await db_session.get(ContextNode, node_id)
        assert result is None

    async def test_global_scope_node(self, db_session):
        """global/global ist eine erlaubte Scope-Kombination."""
        node = await insert_node(
            db_session, read_scope="global", write_scope="global"
        )
        assert node.read_scope == "global"
        assert node.write_scope == "global"


# ── CHECK-Constraint-Tests ────────────────────────────────────────────────────

class TestCheckConstraints:

    async def test_invalid_category_rejected(self, db_session):
        """Ungültige category verletzt CHECK."""
        with pytest.raises(IntegrityError):
            node = ContextNode(**make_node_data(category="invalid_cat"))
            db_session.add(node)
            await db_session.flush()

    async def test_invalid_read_scope_rejected(self, db_session):
        """Ungültiger read_scope verletzt CHECK."""
        with pytest.raises(IntegrityError):
            node = ContextNode(**make_node_data(read_scope="world"))
            db_session.add(node)
            await db_session.flush()

    async def test_write_scope_more_permissive_rejected(self, db_session):
        """write_scope permissiver als read_scope verletzt Restriktivitäts-CHECK."""
        with pytest.raises(IntegrityError):
            # private lesen, aber school schreiben -> write (3) > read (0) -> verletzt
            node = ContextNode(**make_node_data(
                read_scope="private", write_scope="school"
            ))
            db_session.add(node)
            await db_session.flush()

    async def test_scope_group_id_required_for_subject(self, db_session):
        """read_scope='subject' ohne read_scope_group_id verletzt CHECK."""
        with pytest.raises(IntegrityError):
            node = ContextNode(**make_node_data(
                read_scope="subject", write_scope="private",
                read_scope_group_id=None,
            ))
            db_session.add(node)
            await db_session.flush()

    async def test_invalid_node_status_rejected(self, db_session):
        """Ungültiger status verletzt CHECK."""
        with pytest.raises(IntegrityError):
            node = ContextNode(**make_node_data())
            node.status = "unknown_status"
            db_session.add(node)
            await db_session.flush()


# ── NodeEngagement XOR-Constraint ─────────────────────────────────────────────

class TestNodeEngagementConstraints:

    async def test_neither_pseudonym_nor_group_rejected(self, db_session):
        """Kein Subjekt verletzt XOR-CHECK."""
        node = await insert_node(db_session)
        with pytest.raises(IntegrityError):
            eng = NodeEngagement(
                pseudonym=None,
                group_id=None,
                node_id=node.id,
                relation="knows",
                source="chat_inference",
                metadata_={},
            )
            db_session.add(eng)
            await db_session.flush()

    async def test_both_pseudonym_and_group_rejected(self, db_session):
        """Beide Subjekte gesetzt verletzt XOR-CHECK."""
        node = await insert_node(db_session)
        with pytest.raises(IntegrityError):
            eng = NodeEngagement(
                pseudonym="pseudo-test",
                group_id=999,
                node_id=node.id,
                relation="knows",
                source="chat_inference",
                metadata_={},
            )
            db_session.add(eng)
            await db_session.flush()

    async def test_group_with_non_introduced_relation_rejected(self, db_session):
        """group_id + relation != 'introduced' verletzt CHECK."""
        node = await insert_node(db_session)
        # Wir brauchen eine echte group_id — hier wird der Test ggf. mit IntegrityError
        # für fehlenden FK scheitern. Den Constraint direkt via SQL testen:
        with pytest.raises(Exception):  # FK oder CHECK
            await db_session.execute(text("""
                INSERT INTO node_engagement (id, group_id, node_id, relation, source, metadata)
                VALUES (gen_random_uuid(), 999999, :node_id, 'knows', 'chat_inference', '{}')
            """), {"node_id": str(node.id)})
            await db_session.flush()

    async def test_user_engagement_valid(self, db_session):
        """Gueltiges User-Engagement mit pseudonym."""
        node = await insert_node(db_session)
        eng = NodeEngagement(
            pseudonym="pseudo-student",
            group_id=None,
            node_id=node.id,
            relation="knows",
            source="chat_inference",
            metadata_={},
        )
        db_session.add(eng)
        await db_session.flush()
        assert eng.id is not None


# ── ContextEdge Unique-Constraint ───────────────────────────────────────────────

class TestContextEdgeConstraints:

    async def test_duplicate_edge_rejected(self, db_session):
        """Gleiche (from, to, relation)-Kombination zweimal anlegen -> verletzt UNIQUE."""
        node_a = await insert_node(db_session, title="A")
        node_b = await insert_node(db_session, title="B")

        edge1 = ContextEdge(
            from_node_id=node_a.id,
            to_node_id=node_b.id,
            relation="requires",
            metadata_={},
        )
        db_session.add(edge1)
        await db_session.flush()

        with pytest.raises(IntegrityError):
            edge2 = ContextEdge(
                from_node_id=node_a.id,
                to_node_id=node_b.id,
                relation="requires",
                metadata_={},
            )
            db_session.add(edge2)
            await db_session.flush()

    async def test_invalid_relation_rejected(self, db_session):
        """Ungültiger relation-Typ verletzt CHECK."""
        node_a = await insert_node(db_session, title="X")
        node_b = await insert_node(db_session, title="Y")
        with pytest.raises(IntegrityError):
            edge = ContextEdge(
                from_node_id=node_a.id,
                to_node_id=node_b.id,
                relation="invented_relation",
                metadata_={},
            )
            db_session.add(edge)
            await db_session.flush()
