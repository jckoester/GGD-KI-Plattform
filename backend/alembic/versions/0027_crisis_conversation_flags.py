"""Krisenerkennung Phase 11: conversation_flags + conversations.hidden_by_user

ADR-008 Teil 5 (Flagging-Datenmodell) + Teil 7 (Soft-Delete geflaggter Konversationen).
In dieser Phase wird conversation_flags nur mit flag_source='auto_crisis' befüllt.

Revision ID: 0027
Revises: 0026
"""

from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    # Soft-Delete-Marker (ADR-008 Teil 7), genutzt ab Schritt 7.
    op.add_column(
        "conversations",
        sa.Column(
            "hidden_by_user",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "conversation_flags",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "conversation_id",
            sa.UUID(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            sa.UUID(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("flag_source", sa.Text(), nullable=False),
        sa.Column("flag_category", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("trigger_rule", sa.Text(), nullable=True),
        sa.Column("coreviewer_role", sa.Text(), nullable=True),
        sa.Column(
            "flagged_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.CheckConstraint(
            "flag_source IN ('auto_crisis','auto_guardrail','manual_admin')",
            name="check_flag_source",
        ),
        sa.CheckConstraint(
            "severity IN ('info','warning','alert')",
            name="check_flag_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open','under_review','resolved','dismissed')",
            name="check_flag_status",
        ),
    )
    op.create_index("idx_flags_conversation", "conversation_flags", ["conversation_id"])
    op.create_index(
        "idx_flags_status_severity", "conversation_flags", ["status", "severity"]
    )


def downgrade():
    op.drop_index("idx_flags_status_severity", table_name="conversation_flags")
    op.drop_index("idx_flags_conversation", table_name="conversation_flags")
    op.drop_table("conversation_flags")
    op.drop_column("conversations", "hidden_by_user")
