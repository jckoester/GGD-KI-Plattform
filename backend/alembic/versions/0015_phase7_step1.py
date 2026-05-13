"""Phase 7 Schritt 1: creator_role, reject_reason, pending_review-Status, AssistantDocument

Revision ID: 0015
Revises: 0014
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    # 1-1: creator_role — wer hat diesen Assistenten erstellt?
    op.add_column(
        "assistants",
        sa.Column(
            "creator_role",
            sa.Text(),
            nullable=False,
            server_default="'admin'",   # alle bestehenden Assistenten gelten als Admin-Assistenten
        ),
    )
    op.create_check_constraint(
        "check_assistant_creator_role",
        "assistants",
        "creator_role IN ('admin', 'teacher')",
    )

    # 1-2: reject_reason — Admin-Begründung bei Ablehnung (nullable)
    op.add_column(
        "assistants",
        sa.Column("reject_reason", sa.Text(), nullable=True),
    )

    # 1-3: status-CHECK-Constraint um 'pending_review' erweitern
    #       PostgreSQL: DROP + CREATE, da ALTER CONSTRAINT nicht möglich
    op.drop_constraint("check_assistant_status", "assistants")
    op.create_check_constraint(
        "check_assistant_status",
        "assistants",
        "status IN ('draft', 'pending_review', 'active', 'disabled', 'archived')",
    )

    # 1-4: created_by_pseudonym → created_by umbenennen
    op.alter_column("assistants", "created_by_pseudonym", new_column_name="created_by")

    # 1-5: Tabelle assistant_documents anlegen
    op.create_table(
        "assistant_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "assistant_id",
            sa.Integer(),
            sa.ForeignKey("assistants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),  # extrahierter Klartext
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_assistant_documents_assistant_id",
        "assistant_documents",
        ["assistant_id"],
    )


def downgrade():
    op.drop_index("idx_assistant_documents_assistant_id", "assistant_documents")
    op.drop_table("assistant_documents")

    op.alter_column("assistants", "created_by", new_column_name="created_by_pseudonym")

    op.drop_constraint("check_assistant_status", "assistants")
    op.create_check_constraint(
        "check_assistant_status",
        "assistants",
        "status IN ('draft', 'active', 'disabled', 'archived')",
    )

    op.drop_column("assistants", "reject_reason")

    op.drop_constraint("check_assistant_creator_role", "assistants")
    op.drop_column("assistants", "creator_role")
