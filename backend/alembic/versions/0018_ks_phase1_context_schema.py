"""KS-Phase-1: Kontextspeicher-Schema (pgvector, 5 Tabellen)

Revision ID: 0018
Revises: 0017
"""

from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    # 1. pgvector-Extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. context_nodes
    op.create_table(
        "context_nodes",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True, server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column(
            "metadata", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'{}'"),
        ),
        sa.Column("owner_pseudonym", sa.Text(), nullable=True),
        sa.Column(
            "read_scope", sa.Text(), nullable=False,
            server_default=sa.text("'school'"),
        ),
        sa.Column(
            "write_scope", sa.Text(), nullable=False,
            server_default=sa.text("'private'"),
        ),
        sa.Column(
            "read_scope_group_id", sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "write_scope_group_id", sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "assistant_id", sa.Integer(),
            sa.ForeignKey("assistants.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "status", sa.Text(), nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column(
            "archived_at", sa.TIMESTAMP(timezone=True), nullable=True,
        ),
        sa.Column("schuljahr", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "category IN ('document','knowledge','artifact','concept')",
            name="check_context_nodes_category",
        ),
        sa.CheckConstraint(
            "read_scope IN ('global','school','subject','group','private')",
            name="check_context_nodes_read_scope",
        ),
        sa.CheckConstraint(
            "write_scope IN ('global','school','subject','group','private')",
            name="check_context_nodes_write_scope",
        ),
        sa.CheckConstraint(
            "status IN ('active','archived','deleted')",
            name="check_context_nodes_status",
        ),
        sa.CheckConstraint(
            "read_scope NOT IN ('subject','group') OR read_scope_group_id IS NOT NULL",
            name="check_context_nodes_read_group_id",
        ),
        sa.CheckConstraint(
            "write_scope NOT IN ('subject','group') OR write_scope_group_id IS NOT NULL",
            name="check_context_nodes_write_group_id",
        ),
        sa.CheckConstraint(
            """
            CASE write_scope
              WHEN 'private' THEN 0 WHEN 'group'   THEN 1 WHEN 'subject' THEN 2
              WHEN 'school'  THEN 3 WHEN 'global'  THEN 4
            END
            <=
            CASE read_scope
              WHEN 'private' THEN 0 WHEN 'group'   THEN 1 WHEN 'subject' THEN 2
              WHEN 'school'  THEN 3 WHEN 'global'  THEN 4
            END
            """,
            name="check_context_nodes_scope_restrictivity",
        ),
    )

    # embedding-Spalte separat als vector(1536) anlegen
    # (ALTER TABLE statt Column in create_table, da Alembic den Typ nicht kennt)
    op.execute(
        "ALTER TABLE context_nodes ADD COLUMN embedding vector(1536)"
    )

    # Indizes auf context_nodes
    op.create_index("idx_context_nodes_cat_type", "context_nodes", ["category", "content_type"])
    op.create_index("idx_context_nodes_read", "context_nodes", ["read_scope", "read_scope_group_id"])
    op.create_index(
        "idx_context_nodes_owner", "context_nodes", ["owner_pseudonym"],
        postgresql_where=sa.text("owner_pseudonym IS NOT NULL"),
    )
    op.create_index(
        "idx_context_nodes_assistant", "context_nodes", ["assistant_id"],
        postgresql_where=sa.text("assistant_id IS NOT NULL"),
    )
    op.create_index("idx_context_nodes_status", "context_nodes", ["status"])
    op.create_index(
        "idx_context_nodes_valid_until", "context_nodes", ["valid_until"],
        postgresql_where=sa.text("valid_until IS NOT NULL"),
    )
    # HNSW-Vektorindex (cosine distance, m=16, ef_construction=64)
    op.execute("""
        CREATE INDEX idx_context_nodes_embedding
        ON context_nodes
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        WHERE embedding IS NOT NULL
    """)

    # 3. context_edges
    op.create_table(
        "context_edges",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True, server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "from_node_id", sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("context_nodes.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "to_node_id", sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("context_nodes.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("relation", sa.Text(), nullable=False),
        sa.Column(
            "metadata", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "relation IN ('requires','used_with','part_of','develops',"
            "             'supersedes','references','follows','reflects_on','derived_from')",
            name="check_context_edges_relation",
        ),
    )
    op.create_index("idx_context_edges_from", "context_edges", ["from_node_id"])
    op.create_index("idx_context_edges_to", "context_edges", ["to_node_id"])
    op.create_index("idx_context_edges_relation", "context_edges", ["relation"])
    op.create_index(
        "idx_context_edges_unique", "context_edges",
        ["from_node_id", "to_node_id", "relation"],
        unique=True,
    )

    # 4. node_engagement
    op.create_table(
        "node_engagement",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True, server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("pseudonym", sa.Text(), nullable=True),
        sa.Column(
            "group_id", sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "node_id", sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("context_nodes.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("relation", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("strength", sa.Numeric(3, 2), nullable=True),
        sa.Column(
            "metadata", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "relation IN ('introduced','knows','mastered','struggles_with')",
            name="check_node_engagement_relation",
        ),
        sa.CheckConstraint(
            "(pseudonym IS NOT NULL) <> (group_id IS NOT NULL)",
            name="check_node_engagement_subject_xor",
        ),
        sa.CheckConstraint(
            "group_id IS NULL OR relation = 'introduced'",
            name="check_node_engagement_group_relation",
        ),
    )
    op.create_index(
        "idx_engagement_pseudonym", "node_engagement", ["pseudonym"],
        postgresql_where=sa.text("pseudonym IS NOT NULL"),
    )
    op.create_index(
        "idx_engagement_group", "node_engagement", ["group_id"],
        postgresql_where=sa.text("group_id IS NOT NULL"),
    )
    op.create_index("idx_engagement_node", "node_engagement", ["node_id"])
    op.create_index(
        "idx_engagement_unique_user", "node_engagement",
        ["pseudonym", "node_id", "relation"],
        unique=True,
        postgresql_where=sa.text("pseudonym IS NOT NULL"),
    )
    op.create_index(
        "idx_engagement_unique_group", "node_engagement",
        ["group_id", "node_id", "relation"],
        unique=True,
        postgresql_where=sa.text("group_id IS NOT NULL"),
    )

    # 5. assistant_context_anchors
    op.create_table(
        "assistant_context_anchors",
        sa.Column(
            "assistant_id", sa.Integer(),
            sa.ForeignKey("assistants.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "node_id", sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("context_nodes.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("role", sa.Text(), primary_key=True),
        sa.CheckConstraint(
            "role IN ('always_include','retrieval_scope')",
            name="check_assistant_context_anchors_role",
        ),
    )

    # 6. chat_context_nodes
    op.create_table(
        "chat_context_nodes",
        sa.Column(
            "chat_id", sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "node_id", sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("context_nodes.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "added_at", sa.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
    )


def downgrade():
    op.drop_table("chat_context_nodes")
    op.drop_table("assistant_context_anchors")
    op.drop_table("node_engagement")
    op.drop_table("context_edges")
    op.drop_table("context_nodes")
    # Extension nicht droppen — könnte andere Objekte betreffen
