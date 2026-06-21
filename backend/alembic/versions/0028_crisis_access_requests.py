"""Krisen-Einsicht Phase 12: conversation_access_requests + conversation_access_audit

ADR-008 Teil 6 (4-Augen-Einsichtnahme) + Teil 7 (Protokoll/Aufbewahrung).
Antrags-Workflow auf Einsicht in geflaggte Konversationen mit Zweitfreigabe durch
eine review-Person; jeder Zugriff wird append-only protokolliert.

Revision ID: 0028
Revises: 0027
"""

from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversation_access_requests",
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
            "flag_id",
            sa.UUID(),
            sa.ForeignKey("conversation_flags.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requested_by", sa.Text(), nullable=False),
        sa.Column(
            "requested_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "required_coreviewer_role",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'review'"),
        ),
        sa.Column("coreviewer", sa.Text(), nullable=True),
        sa.Column(
            "coreviewer_approved_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "access_granted_until", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','approved','denied','expired','revoked')",
            name="check_access_request_status",
        ),
        sa.CheckConstraint(
            "coreviewer IS NULL OR coreviewer <> requested_by",
            name="check_access_request_distinct_coreviewer",
        ),
    )
    op.create_index(
        "idx_access_requests_conversation",
        "conversation_access_requests",
        ["conversation_id"],
    )
    op.create_index(
        "idx_access_requests_flag", "conversation_access_requests", ["flag_id"]
    )
    op.create_index(
        "idx_access_requests_status", "conversation_access_requests", ["status"]
    )

    op.create_table(
        "conversation_access_audit",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "access_request_id",
            sa.UUID(),
            sa.ForeignKey("conversation_access_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("viewer", sa.Text(), nullable=False),
        sa.Column(
            "viewed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "action IN ('view','export','annotate','share')",
            name="check_access_audit_action",
        ),
    )
    op.create_index(
        "idx_access_audit_request",
        "conversation_access_audit",
        ["access_request_id"],
    )


def downgrade():
    op.drop_index("idx_access_audit_request", table_name="conversation_access_audit")
    op.drop_table("conversation_access_audit")
    op.drop_index(
        "idx_access_requests_status", table_name="conversation_access_requests"
    )
    op.drop_index(
        "idx_access_requests_flag", table_name="conversation_access_requests"
    )
    op.drop_index(
        "idx_access_requests_conversation", table_name="conversation_access_requests"
    )
    op.drop_table("conversation_access_requests")
